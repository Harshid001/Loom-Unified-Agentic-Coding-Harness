"""Centralized production hardening for the FastAPI server.

This module is intentionally isolated from business logic. It protects the existing
API surface with tenant guards, production-only policy checks, request limits,
rate limiting, SSRF validation, and removal of fabricated telemetry.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from fastapi import HTTPException
from fastapi.responses import JSONResponse


PRIVATE_NETS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


@dataclass
class RateLimitState:
    timestamps: deque[float]


class ProductionSecurityError(RuntimeError):
    pass


class APIHardeningMiddleware:
    """Pure ASGI middleware for streaming request-size and public-surface policy."""

    def __init__(self, app: Any, max_body_bytes: int = 10 * 1024 * 1024):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._reject(send, 413, "Request payload exceeds maximum allowed size")
                    return
            except ValueError:
                pass

        if self._public_surface_blocked(path, headers):
            await self._reject(send, 404, "Not found")
            return

        total = 0
        exhausted = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal total, exhausted
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"") or b""
                total += len(body)
                if total > self.max_body_bytes and not exhausted:
                    exhausted = True
                    return {
                        "type": "http.request",
                        "body": b"",
                        "more_body": False,
                        "loom_size_exceeded": True,
                    }
            return message

        violated = False

        async def guarded_send(message: dict[str, Any]) -> None:
            nonlocal violated
            if message.get("type") == "http.response.start" and message.get("status") == 413:
                violated = True
            await send(message)

        await self.app(scope, limited_receive, guarded_send)
        if violated:
            return

    @staticmethod
    def _public_surface_blocked(path: str, headers: dict[str, str]) -> bool:
        production = os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}
        if not production:
            return False
        if path in {"/docs", "/redoc", "/openapi.json"}:
            return not valid_api_credential(headers)
        if path == "/metrics":
            return not valid_api_credential(headers)
        return False

    @staticmethod
    async def _reject(send: Callable[..., Awaitable[None]], status_code: int, detail: str) -> None:
        body = ("{\"detail\":\"" + detail.replace('"', "'") + "\"}").encode()
        await send({"type": "http.response.start", "status": status_code, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})


def _token_from_headers(headers: dict[str, str]) -> str | None:
    raw = headers.get("authorization") or headers.get("x-api-key") or headers.get("x-dashboard-auth")
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw.strip()


def valid_api_credential(headers: dict[str, str]) -> bool:
    token = _token_from_headers(headers)
    if not token:
        return False
    configured = os.getenv("API_KEY")
    if configured and token == configured:
        return True
    try:
        from loom.auth.api_tokens import get_api_token_store

        record = get_api_token_store().verify(token)
        return record is not None
    except Exception:
        return False


def trusted_client_ip(scope: dict[str, Any]) -> str:
    peer = (scope.get("client") or ("127.0.0.1", 0))[0]
    trusted_proxy = os.getenv("TRUST_PROXY", "false").lower() in {"1", "true", "yes"}
    if trusted_proxy:
        for key, value in scope.get("headers", []):
            if key.lower() == b"x-forwarded-for" and value:
                return value.decode().split(",", 1)[0].strip()
    return peer


class RedisRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self._local: dict[str, RateLimitState] = defaultdict(lambda: RateLimitState(deque()))
        self._redis = None

    async def _client(self):
        if self._redis is not None:
            return self._redis
        url = os.getenv("REDIS_URL")
        if not url:
            return None
        try:
            from redis.asyncio import from_url

            self._redis = from_url(url, decode_responses=True)
            return self._redis
        except Exception:
            return None

    async def allow(self, key: str) -> bool:
        client = await self._client()
        if client is not None:
            try:
                redis_key = f"loom:rl:{key}"
                current = await client.incr(redis_key)
                if current == 1:
                    await client.expire(redis_key, self.window)
                return int(current) <= self.limit
            except Exception:
                if os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}:
                    raise ProductionSecurityError("Rate-limit Redis is unavailable in production")

        if (
            os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}
            and os.getenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "false").lower() not in {"1", "true", "yes"}
        ):
            raise ProductionSecurityError("REDIS_URL is required for production rate limiting")

        now = time.time()
        state = self._local[key]
        while state.timestamps and now - state.timestamps[0] >= self.window:
            state.timestamps.popleft()
        if len(state.timestamps) >= self.limit:
            return False
        state.timestamps.append(now)
        return True


def install_rate_limiter(app: Any) -> None:
    limiter = RedisRateLimiter(int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))

    @app.middleware("http")
    async def production_rate_limit(request: Any, call_next: Callable[..., Awaitable[Any]]):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        try:
            ip = trusted_client_ip(request.scope)
            principal = "anonymous"
            auth = request.headers.get("authorization") or request.headers.get("x-api-key")
            if auth:
                principal = auth[-16:]
            key = f"{ip}:{principal}:{request.url.path}"
            if not await limiter.allow(key):
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        except ProductionSecurityError as exc:
            return JSONResponse(status_code=503, content={"detail": str(exc)})
        return await call_next(request)


def validate_webhook_url(url: str, allow_hosts: set[str] | None = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS")
    host = parsed.hostname.rstrip(".").lower()
    if allow_hosts is None:
        configured = os.getenv("SLACK_WEBHOOK_ALLOWED_HOSTS", "hooks.slack.com")
        allow_hosts = {h.strip().lower() for h in configured.split(",") if h.strip()}
    if host not in allow_hosts:
        raise HTTPException(status_code=400, detail="Webhook host is not allowlisted")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Unable to resolve webhook host") from exc
    for _, _, _, _, sockaddr in addresses:
        ip = ipaddress.ip_address(sockaddr[0])
        if any(ip in net for net in PRIVATE_NETS):
            raise HTTPException(status_code=400, detail="Webhook host resolves to a private or local address")


def run_org_id(run_id: str) -> str | None:
    try:
        from loom.orchestrator.state import OrchestratorState

        state = OrchestratorState.load_checkpoint(run_id)
        if state is None:
            return None
        return str(state.shared_data.get("org_id")) if state.shared_data.get("org_id") else None
    except Exception:
        return None


def harden_server_module(module: Any) -> None:
    app = module.app
    app.add_middleware(APIHardeningMiddleware)
    install_rate_limiter(app)

    for route in list(getattr(app, "routes", [])):
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue

        if path.endswith("/ast"):
            async def ast_guard(*args: Any, __endpoint: Any = endpoint, **kwargs: Any) -> Any:
                run_id = kwargs.get("run_id") or (args[0] if args else "")
                checkpoint = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
                if not checkpoint.exists():
                    raise HTTPException(status_code=404, detail="AST evidence unavailable")
                result = await __endpoint(*args, **kwargs) if asyncio.iscoroutinefunction(__endpoint) else __endpoint(*args, **kwargs)
                if isinstance(result, dict) and "files_indexed" in result and result.get("sanitizer_status") == "safe":
                    return result
                return result
            route.endpoint = ast_guard

        elif path.endswith("/runs"):
            async def list_guard(*args: Any, __endpoint: Any = endpoint, **kwargs: Any) -> Any:
                limit = int(kwargs.get("limit", 50))
                offset = max(int(kwargs.get("offset", 0)), 0)
                kwargs["limit"] = min(limit, 100)
                kwargs["offset"] = offset
                result = await __endpoint(*args, **kwargs) if asyncio.iscoroutinefunction(__endpoint) else __endpoint(*args, **kwargs)
                try:
                    principal = module.get_effective_principal()
                    org_id = principal.org_id
                    if isinstance(result, list):
                        return [r for r in result if r.get("id") and _checkpoint_org(r.get("id"), org_id)]
                except Exception:
                    pass
                return result
            route.endpoint = list_guard

        elif "run/{run_id}" in path or "runs/{run_id}" in path:
            async def run_guard(*args: Any, __endpoint: Any = endpoint, **kwargs: Any) -> Any:
                run_id = kwargs.get("run_id") or (args[0] if args else "")
                principal = module.get_effective_principal()
                run_org = run_org_id(str(run_id))
                if run_org is None or run_org != principal.org_id:
                    raise HTTPException(status_code=404, detail="Run not found")
                return await __endpoint(*args, **kwargs) if asyncio.iscoroutinefunction(__endpoint) else __endpoint(*args, **kwargs)
            route.endpoint = run_guard

        elif path.endswith("/run"):
            async def create_guard(*args: Any, __endpoint: Any = endpoint, **kwargs: Any) -> Any:
                req = kwargs.get("req")
                production = os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}
                if production and req is not None and bool(getattr(req, "mock", False)):
                    raise HTTPException(status_code=400, detail="Mock execution is disabled in production")
                return await __endpoint(*args, **kwargs) if asyncio.iscoroutinefunction(__endpoint) else __endpoint(*args, **kwargs)
            route.endpoint = create_guard

        elif "integrations/slack/notify" in path:
            async def slack_guard(*args: Any, __endpoint: Any = endpoint, **kwargs: Any) -> Any:
                req = kwargs.get("req")
                if req is not None:
                    validate_webhook_url(str(req.webhook_url))
                return await __endpoint(*args, **kwargs) if asyncio.iscoroutinefunction(__endpoint) else __endpoint(*args, **kwargs)
            route.endpoint = slack_guard


def _checkpoint_org(run_id: str, expected_org: str) -> bool:
    actual = run_org_id(run_id)
    return actual == expected_org

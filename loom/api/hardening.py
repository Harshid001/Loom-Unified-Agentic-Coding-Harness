"""Centralized production hardening for the FastAPI server.

This module is intentionally isolated from business logic. It protects the existing
API surface with tenant guards, production-only policy checks, request limits,
rate limiting, SSRF validation, webhook signature validation, and removal of fabricated telemetry.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import hmac
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
    ) -> None:
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
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(b"content-type", b"application/json")],
            }
        )
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
    if configured and hmac.compare_digest(token, configured):
        return True
    try:
        from loom.auth.api_tokens import get_api_token_store

        record = get_api_token_store().verify(token)
        return record is not None
    except Exception:
        return False


def verify_webhook_signature(path: str, headers: dict[str, str], body: bytes) -> bool:
    """Verify an inbound GitHub or GitLab webhook signature using constant-time comparison."""
    normalized_path = path.lower()
    normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}

    if "/github/" in normalized_path and normalized_path.endswith("/webhook"):
        secret = os.getenv("GITHUB_WEBHOOK_SECRET")
        signature = normalized_headers.get("x-hub-signature-256", "")
        if not secret or not signature.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    if "/gitlab/" in normalized_path and normalized_path.endswith("/webhook"):
        secret = os.getenv("GITLAB_WEBHOOK_SECRET")
        token = normalized_headers.get("x-gitlab-token", "")
        if not secret:
            return False
        return hmac.compare_digest(token, secret)

    return False


def trusted_client_ip(scope: dict[str, Any]) -> str:
    client = scope.get("client")
    peer = str(client[0]) if isinstance(client, (tuple, list)) and client else "127.0.0.1"
    trusted_proxy = os.getenv("TRUST_PROXY", "false").lower() in {"1", "true", "yes"}
    if trusted_proxy:
        for key, value in scope.get("headers", []):
            if key.lower() == b"x-forwarded-for" and value:
                decoded = value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
                return decoded.split(",", 1)[0].strip()
    return peer


class RedisRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self._local: dict[str, RateLimitState] = defaultdict(lambda: RateLimitState(deque()))
        self._redis: Any | None = None

    async def _client(self) -> Any:
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



def _checkpoint_org(run_id: str, expected_org: str) -> bool:
    actual = run_org_id(run_id)
    return actual == expected_org


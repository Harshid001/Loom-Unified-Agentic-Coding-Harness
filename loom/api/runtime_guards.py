"""Authoritative request guards applied before FastAPI route dispatch.

This layer intentionally lives below FastAPI dependencies so production policy cannot
be bypassed by stale/cached route callables or legacy aliases.
"""

from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

MAX_BODY_BYTES = 10 * 1024 * 1024


def _production() -> bool:
    return os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}


def _token_from_headers(headers: dict[str, str]) -> str | None:
    raw = headers.get("authorization") or headers.get("x-api-key") or headers.get("x-dashboard-auth")
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw.strip()


def _principal_from_headers(headers: dict[str, str]) -> Any | None:
    token = _token_from_headers(headers)
    if not token:
        return None
    configured = os.getenv("API_KEY")
    try:
        from loom.auth.api_tokens import get_api_token_store
        from loom.auth.context import get_effective_principal, get_service_principal

        if configured and token == configured:
            return get_service_principal()
        record = get_api_token_store().verify(token)
        if record is not None:
            return get_effective_principal()
    except Exception:
        return None
    return None


def _load_checkpoint(run_id: str) -> dict[str, Any] | None:
    from pathlib import Path

    path = Path(os.getenv("LOOM_CHECKPOINT_DIR", str(Path.home() / ".loom" / "checkpoints"))) / f"checkpoint_{run_id}.json"
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _owns_run(run_id: str, principal: Any) -> bool:
    if principal is None:
        return False
    checkpoint = _load_checkpoint(run_id)
    if checkpoint is None:
        return False
    shared = checkpoint.get("shared_data") or {}
    owner_org = checkpoint.get("org_id") or shared.get("org_id")
    return owner_org is not None and str(owner_org) == str(principal.org_id)


async def _read_body(receive: Callable[..., Awaitable[dict[str, Any]]]) -> tuple[bytes, Callable[..., Awaitable[dict[str, Any]]]]:
    chunks: list[bytes] = []
    total = 0
    more = True
    while more:
        message = await receive()
        if message.get("type") != "http.request":
            body = b"".join(chunks)
            return body, _replay_receive(body, message)
        chunk = message.get("body", b"") or b""
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request payload exceeds maximum allowed size")
        chunks.append(chunk)
        more = bool(message.get("more_body"))
    body = b"".join(chunks)
    return body, _replay_receive(body)


def _replay_receive(body: bytes, terminal: dict[str, Any] | None = None) -> Callable[..., Awaitable[dict[str, Any]]]:
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return terminal or {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


class RuntimeGuardMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        principal = _principal_from_headers(headers) if _production() else None

        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    await self._reject(send, 413, "Request payload exceeds maximum allowed size")
                    return
            except ValueError:
                pass

        if method in {"POST", "PUT", "PATCH"} and "http.request" in {"http.request"}:
            try:
                body, receive = await _read_body(receive)
            except HTTPException as exc:
                await self._reject(send, exc.status_code, str(exc.detail))
                return
        else:
            body = b""

        if _production() and "/runs/" in path:
            pieces = path.split("/")
            try:
                idx = pieces.index("runs")
                run_id = pieces[idx + 1]
            except (ValueError, IndexError):
                run_id = ""
            if run_id and run_id not in {"control", ""} and not _owns_run(run_id, principal):
                await self._reject(send, 404, "Run not found")
                return

        if _production() and path.endswith("/ast"):
            run_id = path.rstrip("/").split("/")[-2]
            checkpoint = _load_checkpoint(run_id)
            ast_summary = (checkpoint or {}).get("shared_data", {}).get("ast_summary")
            if not checkpoint or not isinstance(ast_summary, dict):
                await self._reject(send, 404, "AST evidence unavailable")
                return

        if _production() and method in {"POST", "PUT", "PATCH"} and path.rstrip("/").endswith("/run"):
            try:
                payload = json.loads(body or b"{}")
            except json.JSONDecodeError:
                payload = {}
            if bool(payload.get("mock")):
                await self._reject(send, 400, "Mock execution is disabled in production")
                return

        if _production() and method == "POST" and "integrations/slack/notify" in path:
            try:
                payload = json.loads(body or b"{}")
            except json.JSONDecodeError:
                payload = {}
            webhook_url = payload.get("webhook_url")
            if webhook_url:
                from loom.api.hardening import validate_webhook_url
                try:
                    validate_webhook_url(str(webhook_url))
                except HTTPException as exc:
                    await self._reject(send, exc.status_code, str(exc.detail))
                    return

        if _production() and method == "GET" and path.rstrip("/") in {"/api/runs", "/api/v1/runs"}:
            messages: list[dict[str, Any]] = []
            body_chunks: list[bytes] = []

            async def capture(message: dict[str, Any]) -> None:
                messages.append(message)
                if message.get("type") == "http.response.body":
                    body_chunks.append(message.get("body", b"") or b"")

            await self.app(scope, receive, capture)
            raw = b"".join(body_chunks)
            try:
                data = json.loads(raw or b"[]")
                if isinstance(data, list) and principal is not None:
                    data = [item for item in data if isinstance(item, dict) and _owns_run(str(item.get("id", "")), principal)]
                new_body = json.dumps(data).encode()
                start = next((m for m in messages if m.get("type") == "http.response.start"), None)
                if start:
                    headers_out = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"content-length"]
                    headers_out.append((b"content-length", str(len(new_body)).encode()))
                    await send({**start, "headers": headers_out})
                    await send({"type": "http.response.body", "body": new_body, "more_body": False})
                    return
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
            for message in messages:
                await send(message)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Callable[..., Awaitable[None]], status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        await send({"type": "http.response.start", "status": status_code, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def install_runtime_guards(app: Any) -> None:
    app.add_middleware(RuntimeGuardMiddleware)

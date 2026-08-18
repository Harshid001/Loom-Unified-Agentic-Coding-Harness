"""Authoritative request guards applied before FastAPI route dispatch."""

from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs

from fastapi import HTTPException

from loom.auth.runtime_principal import principal_from_headers

MAX_BODY_BYTES = 10 * 1024 * 1024


def _production() -> bool:
    if os.getenv("DEV_MODE", "false").lower() == "true":
        return False
    if os.getenv("ALLOW_MOCK_EXECUTION", "false").lower() == "true":
        return False
    return os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}


def _token_from_headers(headers: dict[str, str]) -> str | None:
    raw = headers.get("authorization") or headers.get("x-api-key") or headers.get("x-dashboard-auth")
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw.strip()


def _principal_from_headers(headers: dict[str, str]) -> Any | None:
    return principal_from_headers(headers)


def _load_checkpoint(run_id: str) -> dict[str, Any] | None:
    from pathlib import Path
    path = Path(os.getenv("LOOM_CHECKPOINT_DIR", str(Path.home() / ".loom" / "checkpoints"))) / f"checkpoint_{run_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


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

        if method in {"POST", "PUT", "PATCH"}:
            try:
                body, receive = await _read_body(receive)
            except HTTPException as exc:
                await self._reject(send, exc.status_code, str(exc.detail))
                return
        else:
            body = b""

        if _production() and method == "GET" and path.rstrip("/") in {"/api/runs", "/api/v1/runs"}:
            if principal is None:
                detail = "API_KEY environment variable is not configured" if not os.getenv("API_KEY") else "Authentication required"
                await self._reject(send, 401, detail)
                return
            query = parse_qs((scope.get("query_string") or b"").decode("utf-8", errors="replace"))
            try:
                offset = max(0, int(query.get("offset", ["0"])[0]))
                limit = min(100, max(1, int(query.get("limit", ["50"])[0])))
            except ValueError:
                await self._reject(send, 400, "Invalid pagination parameters")
                return
            from loom.db.records_store import get_run_record_store
            try:
                records = get_run_record_store().list_runs(org_id=principal.org_id, limit=limit, offset=offset)
            except Exception:
                await self._reject(send, 503, "Run store unavailable")
                return
            data = [
                {
                    "id": record.run_id,
                    "issue": record.issue_text,
                    "status": record.status,
                    "repo_path": record.repo_id,
                    "created_at": record.started_at,
                    "cost": record.cost_usd,
                }
                for record in records
            ]
            payload = json.dumps(data).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]})
            await send({"type": "http.response.body", "body": payload, "more_body": False})
            return

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

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Callable[..., Awaitable[None]], status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        await send({"type": "http.response.start", "status": status_code, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def install_runtime_guards(app: Any) -> None:
    app.add_middleware(RuntimeGuardMiddleware)

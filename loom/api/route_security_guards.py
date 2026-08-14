"""Route-specific security checks that must not depend on optional middleware wiring."""

from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable

from loom.api.hardening import validate_webhook_url
from loom.api.runtime_guards import _owns_run, _principal_from_headers, _read_body


class RouteSecurityGuardMiddleware:
    """Enforce security-sensitive request checks before FastAPI route dispatch."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]) -> None:
        if scope.get("type") != "http" or os.getenv("LOOM_ENV", "production").lower() not in {"prod", "production"}:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if method not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        body, receive = await _read_body(receive)
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            payload = {}

        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        principal = _principal_from_headers(headers)

        if path.rstrip("/") in {"/api/v1/run/control", "/api/run/control"}:
            action = str(payload.get("action", "")).lower()
            run_id = str(payload.get("run_id", ""))
            if action == "rollback":
                if not run_id or not run_id.replace("_", "").replace("-", "").isalnum():
                    await self._reject(send, 400, "Invalid run_id")
                    return
                if not _owns_run(run_id, principal):
                    await self._reject(send, 404, "Run not found")
                    return

        if "integrations/slack/notify" in path or "webhooks/subscriptions" in path:
            webhook_url = payload.get("webhook_url") or payload.get("url")
            if webhook_url:
                try:
                    validate_webhook_url(str(webhook_url))
                except Exception as exc:
                    status_code = getattr(exc, "status_code", 400)
                    detail = getattr(exc, "detail", "Invalid webhook URL")
                    await self._reject(send, int(status_code), str(detail))
                    return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Callable[..., Awaitable[None]], status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})


def install_route_security_guards(app: Any) -> None:
    app.add_middleware(RouteSecurityGuardMiddleware)

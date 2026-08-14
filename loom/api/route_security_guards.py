"""Route-specific security checks that must not depend on optional middleware wiring."""

from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable

from loom.api.hardening import validate_webhook_url
from loom.api.runtime_guards import _owns_run, _read_body
from loom.auth.runtime_principal import principal_from_headers


class RouteSecurityGuardMiddleware:
    """Enforce security-sensitive request checks before FastAPI route dispatch."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http" or os.getenv("LOOM_ENV", "production").lower() not in {"prod", "production"}:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        principal = principal_from_headers(headers)

        body = b""
        if method in {"POST", "PUT", "PATCH"}:
            body, receive = await _read_body(receive)
            try:
                payload = json.loads(body or b"{}")
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = {}

        # Resource-specific tenant boundaries must hold even if a route dependency
        # or legacy alias is accidentally changed later.
        segments = [segment for segment in path.strip("/").split("/") if segment]
        target_org: str | None = None
        if len(segments) >= 3 and segments[0] == "api" and segments[1] == "v1" and segments[2] == "orgs":
            target_org = segments[3] if len(segments) > 3 else None
        elif len(segments) >= 5 and segments[:4] == ["api", "v1", "integrations", "bot"]:
            target_org = segments[4]

        if target_org is not None:
            if principal is None or str(target_org) != str(principal.org_id):
                await self._reject(send, 404, "Resource not found")
                return

        if path.rstrip("/") in {"/api/v1/entitlements/check", "/v1/entitlements/check"}:
            target = str(payload.get("org_id") or "")
            if target and (principal is None or target != str(principal.org_id)):
                await self._reject(send, 404, "Resource not found")
                return

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
                    await self._reject(
                        send,
                        int(getattr(exc, "status_code", 400)),
                        str(getattr(exc, "detail", "Invalid webhook URL")),
                    )
                    return
            if "webhooks/subscriptions" in path and payload.get("secret") and not (
                os.getenv("LOOM_WEBHOOK_SECRET_KEY") or os.getenv("LOOM_BACKUP_ENCRYPTION_KEY")
            ):
                await self._reject(send, 503, "Webhook secret encryption is not configured")
                return

        if path.startswith("/scim/"):
            required = os.getenv("SCIM_TOKEN")
            presented = headers.get("authorization", "")
            if not required or not presented.startswith("Bearer "):
                await self._reject(send, 401, "Authentication required")
                return
            import hmac
            if not hmac.compare_digest(presented[7:].strip(), required):
                await self._reject(send, 401, "Authentication required")
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Callable[..., Awaitable[None]], status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def install_route_security_guards(app: Any) -> None:
    app.add_middleware(RouteSecurityGuardMiddleware)

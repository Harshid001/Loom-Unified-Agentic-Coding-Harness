"""Late-bound hardening for components initialized during API import."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Awaitable, Callable

from cryptography.fernet import Fernet
from fastapi import Header, HTTPException


def _webhook_fernet() -> Fernet:
    key = os.getenv("LOOM_WEBHOOK_SECRET_KEY")
    if not key:
        if os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}:
            raise RuntimeError("LOOM_WEBHOOK_SECRET_KEY is required in production")
        key = os.getenv("LOOM_BACKUP_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("Webhook secret encryption key is not configured")
    return Fernet(key.encode())


def _encrypt_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    return "enc:" + _webhook_fernet().encrypt(secret.encode()).decode()


def _decrypt_secret(secret: str | None) -> str | None:
    if not secret or not secret.startswith("enc:"):
        return secret
    return _webhook_fernet().decrypt(secret[4:].encode()).decode()


class WebhookSignatureMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not ("/integrations/github/webhook" in path or "/integrations/gitlab/webhook" in path):
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            if message.get("type") != "http.request":
                continue
            chunks.append(message.get("body", b"") or b"")
            more = bool(message.get("more_body"))
        body = b"".join(chunks)

        valid = False
        production = os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}
        if "/github/" in path:
            secret = os.getenv("GITHUB_WEBHOOK_SECRET")
            signature = headers.get("x-hub-signature-256", "")
            if secret:
                expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                valid = hmac.compare_digest(signature, expected)
            else:
                valid = not production
        else:
            secret = os.getenv("GITLAB_WEBHOOK_SECRET")
            token = headers.get("x-gitlab-token", "")
            valid = hmac.compare_digest(token, secret) if secret else not production

        if not valid:
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"Invalid webhook signature"}'})
            return

        sent = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)


def _install_identity_and_stream_hardening(module: Any) -> None:
    """Patch legacy server symbols/routes after the server module is fully initialized."""
    try:
        from loom.auth.context import get_effective_principal, resolve_request_org

        module.get_effective_principal = get_effective_principal
        module.resolve_request_org = resolve_request_org
    except Exception:
        if os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}:
            raise

    source = '''
async def _hardened_stream_run(run_id: str):
    """Authenticated SSE stream scoped to the run's owning organization."""
    run_entry = ACTIVE_RUNS.get(run_id)
    if not run_entry:
        raise HTTPException(status_code=404, detail="Run not found")

    principal = get_effective_principal()
    run_state = run_entry.get("state")
    run_org = run_state.shared_data.get("org_id") if run_state else None
    if run_org != principal.org_id:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        run_entry["queues"].append(queue)
        terminal = False
        try:
            for event in list(run_entry.get("events", [])):
                yield "data: " + json.dumps(event) + chr(10) + chr(10)
                if event.get("type") == "status_change" and event.get("data", {}).get("status") in ("completed", "failed"):
                    terminal = True
                    break

            if not terminal:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=2.0)
                        yield "data: " + json.dumps(event) + chr(10) + chr(10)
                        if event.get("type") == "status_change" and event.get("data", {}).get("status") in ("completed", "failed"):
                            break
                    except asyncio.TimeoutError:
                        ping_event = {
                            "type": "ping",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "run_id": run_id,
                        }
                        yield "data: " + json.dumps(ping_event) + chr(10) + chr(10)
        except asyncio.CancelledError:
            pass
        finally:
            if queue in run_entry.get("queues", []):
                run_entry["queues"].remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
'''
    try:
        exec(source, module.__dict__)
        legacy_stream = getattr(module, "stream_run", None)
        hardened_stream = getattr(module, "_hardened_stream_run")
        if legacy_stream is not None:
            legacy_stream.__code__ = hardened_stream.__code__
            legacy_stream.__defaults__ = hardened_stream.__defaults__
            legacy_stream.__kwdefaults__ = hardened_stream.__kwdefaults__
    except Exception:
        if os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}:
            raise


def apply_late_hardening(module: Any) -> None:
    app = module.app
    app.add_middleware(WebhookSignatureMiddleware)
    _install_identity_and_stream_hardening(module)

    try:
        from loom.api.webhooks import WebhookEngine

        if not getattr(WebhookEngine, "_loom_secret_hardened", False):
            original_load = WebhookEngine._load_subscriptions
            original_save = WebhookEngine._save_subscriptions

            def load(self: Any) -> None:
                original_load(self)
                for subscription in self._subscriptions.values():
                    if subscription.secret:
                        subscription.secret = _decrypt_secret(subscription.secret)

            def save(self: Any) -> None:
                original_values = list(self._subscriptions.values())
                try:
                    for subscription in original_values:
                        if subscription.secret and not subscription.secret.startswith("enc:"):
                            subscription.secret = _encrypt_secret(subscription.secret)
                    original_save(self)
                finally:
                    for subscription in original_values:
                        if subscription.secret and subscription.secret.startswith("enc:"):
                            subscription.secret = _decrypt_secret(subscription.secret)

            WebhookEngine._load_subscriptions = load
            WebhookEngine._save_subscriptions = save
            WebhookEngine._loom_secret_hardened = True
    except Exception:
        if os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}:
            raise

    try:
        from loom.scim.provisioning import _require_scim_token, scim_router

        def secure_scim_token(x_scim_token: str | None = Header(None, alias="Authorization")) -> str:
            required = os.getenv("SCIM_TOKEN")
            if not required:
                raise HTTPException(status_code=503, detail="SCIM not enabled: SCIM_TOKEN not configured")
            expected = f"Bearer {required}"
            if not x_scim_token or not hmac.compare_digest(x_scim_token, expected):
                raise HTTPException(status_code=401, detail="Invalid SCIM bearer token")
            return x_scim_token

        secure_scim_token.__name__ = getattr(_require_scim_token, "__name__", "_require_scim_token")
        for route in getattr(scim_router, "routes", []):
            dependant = getattr(route, "dependant", None)
            if dependant is None:
                continue
            for dep in getattr(dependant, "dependencies", []):
                if getattr(dep.call, "__name__", "") == "_require_scim_token":
                    dep.call = secure_scim_token
    except Exception:
        pass

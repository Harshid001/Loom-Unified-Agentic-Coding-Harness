"""Explicit ASGI security hardening and lifecycle middleware."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any, Awaitable, Callable

from cryptography.fernet import Fernet

logger = logging.getLogger("loom.api.late_hardening")


def _webhook_fernet() -> Fernet | None:
    key = os.getenv("LOOM_WEBHOOK_SECRET_KEY") or os.getenv("LOOM_BACKUP_ENCRYPTION_KEY")
    return Fernet(key.encode()) if key else None


def _encrypt_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    f = _webhook_fernet()
    if f is None:
        return secret
    return "enc:" + f.encrypt(secret.encode()).decode()


def _decrypt_secret(secret: str | None) -> str | None:
    if not secret or not secret.startswith("enc:"):
        return secret
    f = _webhook_fernet()
    if f is None:
        return secret
    return f.decrypt(secret[4:].encode()).decode()


class WebhookSignatureMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        is_github = "/integrations/github/webhook" in path
        is_gitlab = "/integrations/gitlab/webhook" in path
        if not (is_github or is_gitlab):
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
        scope["_loom_raw_body"] = body

        production = os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}
        valid = False
        if is_github:
            secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
            signature = headers.get("x-hub-signature-256", "")
            if secret:
                expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                valid = bool(signature) and hmac.compare_digest(signature, expected)
            else:
                valid = not production
        else:
            secret = os.getenv("GITLAB_WEBHOOK_SECRET", "")
            token = headers.get("x-gitlab-token", "")
            if secret:
                valid = bool(token) and hmac.compare_digest(token, secret)
            else:
                valid = not production

        if not valid:
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"Invalid webhook signature"}'})
            return

        _sent = False
        async def replay_receive() -> dict[str, Any]:
            nonlocal _sent
            if _sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            _sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        from starlette.datastructures import State
        state_obj = scope.get("state") or State()
        state_obj.raw_body = body
        state_obj.webhook_signature_verified = True
        scope["state"] = state_obj
        await self.app(scope, replay_receive, send)


class PrincipalCleanupMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        try:
            from loom.auth.context import begin_request_auth_context
            begin_request_auth_context()
        except Exception:
            pass
        try:
            await self.app(scope, receive, send)
        finally:
            try:
                from loom.auth.context import end_request_auth_context
                end_request_auth_context()
            except Exception:
                pass


def install_terminal_webhook_normalizer() -> None:
    try:
        from loom.api.webhooks import WebhookEventType
        from loom.orchestrator.task_graph import RunStatus, TaskGraph
        if getattr(TaskGraph, "_loom_terminal_webhooks_patched", False):
            return
        original_fire = TaskGraph._fire_webhook
        original_record = TaskGraph._record_run
        def fire(self: Any, event_type: Any, data: dict[str, Any]) -> None:
            if event_type == WebhookEventType.RUN_FAILED and data.get("reason") == "human_review_required":
                event_type = WebhookEventType.RUN_COMPLETED
            original_fire(self, event_type, data)
        def record(self: Any) -> None:
            commit_gateway = self.state.shared_data.get("commit_gateway") or {}
            security_hold = self.state.shared_data.get("verification_decision") == "security_hold" or commit_gateway.get("status") == "security_hold" or bool(self.state.shared_data.get("security_hold_reason"))
            if security_hold:
                self.run_status = RunStatus.SECURITY_HOLD
            original_record(self)
        TaskGraph._fire_webhook = fire
        TaskGraph._record_run = record
        TaskGraph._loom_terminal_webhooks_patched = True
    except Exception:
        if os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}:
            raise


def install_webhook_secret_encryption() -> None:
    if not (os.getenv("LOOM_WEBHOOK_SECRET_KEY") or os.getenv("LOOM_BACKUP_ENCRYPTION_KEY")):
        return
    try:
        from loom.api.webhooks import WebhookEngine
        if getattr(WebhookEngine, "_loom_secret_hardened", False):
            return
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
        WebhookEngine._load_subscriptions = load  # type: ignore[method-assign]
        WebhookEngine._save_subscriptions = save  # type: ignore[method-assign]
        WebhookEngine._loom_secret_hardened = True  # type: ignore[attr-defined]
    except Exception:
        if os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}:
            raise


# ---------------------------------------------------------------------------
# Legacy no-op shim (kept for any remaining call sites during transition)
# ---------------------------------------------------------------------------


def apply_late_hardening(module: Any) -> None:  # noqa: ARG001
    """No-op.  All hardening is now composed explicitly in create_app().

    This function is retained to avoid ImportError in any code that still
    calls it, but it performs no action.  It will be removed in a future
    cleanup pass after all call sites are confirmed removed.
    """

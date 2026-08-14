"""Late-bound hardening components.

PRD-016: This module provides ASGI middleware classes that are composed
explicitly by create_app() in loom.api.app.  The legacy
``apply_late_hardening(module)`` function is kept as a no-op for any
remaining call sites during the transition, but does nothing.

Key changes from the original:
  - WebhookSignatureMiddleware now caches the raw request body in
    ``scope["_loom_raw_body"]`` AND replays it downstream so route handlers
    can call ``request.body()`` without receiving an empty response.
    (Fixes the double-body-read bug where the middleware consumed the stream
    and left an empty body for the FastAPI handler.)
  - ``apply_late_hardening(module)`` is a no-op; all composition is done in
    create_app().
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Awaitable, Callable

from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Secret encryption helpers (webhook subscription secret at rest)
# ---------------------------------------------------------------------------


def _webhook_fernet() -> Fernet | None:
    key = os.getenv("LOOM_WEBHOOK_SECRET_KEY") or os.getenv("LOOM_BACKUP_ENCRYPTION_KEY")
    if not key:
        return None
    return Fernet(key.encode())


def _encrypt_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    fernet = _webhook_fernet()
    if fernet is None:
        return secret
    return "enc:" + fernet.encrypt(secret.encode()).decode()


def _decrypt_secret(secret: str | None) -> str | None:
    if not secret or not secret.startswith("enc:"):
        return secret
    fernet = _webhook_fernet()
    if fernet is None:
        return secret
    return fernet.decrypt(secret[4:].encode()).decode()


# ---------------------------------------------------------------------------
# WebhookSignatureMiddleware
# ---------------------------------------------------------------------------


class WebhookSignatureMiddleware:
    """ASGI middleware that verifies inbound webhook signatures before routing.

    For GitHub webhooks:
        Requires ``X-Hub-Signature-256: sha256=<hmac>`` matching the
        ``GITHUB_WEBHOOK_SECRET`` environment variable.

    For GitLab webhooks:
        Requires ``X-Gitlab-Token`` matching the ``GITLAB_WEBHOOK_SECRET``
        environment variable.

    Body caching (double-read fix):
        The middleware reads the full request body stream to compute the HMAC.
        It then stores the raw bytes in ``scope["_loom_raw_body"]`` so that
        FastAPI route handlers can retrieve it via ``request.state.raw_body``
        without re-reading a consumed stream.  A ``replay_receive`` coroutine
        reconstructs the ASGI receive channel so downstream middleware and
        routes can call ``request.body()`` normally.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

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
        is_github = "/integrations/github/webhook" in path
        is_gitlab = "/integrations/gitlab/webhook" in path

        if not (is_github or is_gitlab):
            await self.app(scope, receive, send)
            return

        # --- Read full body from stream -----------------------------------------
        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            if message.get("type") != "http.request":
                # Pass through non-request messages (e.g. disconnect)
                continue
            chunks.append(message.get("body", b"") or b"")
            more = bool(message.get("more_body"))
        body = b"".join(chunks)

        # --- Cache raw body for downstream handlers ----------------------------
        scope["_loom_raw_body"] = body

        # --- Verify signature --------------------------------------------------
        valid = False
        production = os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}

        if is_github:
            secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
            signature = headers.get("x-hub-signature-256", "")
            if secret:
                expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                # Use constant-time comparison; guard against empty signature
                valid = bool(signature) and hmac.compare_digest(signature, expected)
            else:
                # No secret configured: allow in dev, reject in production
                valid = not production
        else:
            # GitLab
            secret = os.getenv("GITLAB_WEBHOOK_SECRET", "")
            token = headers.get("x-gitlab-token", "")
            if secret:
                valid = bool(token) and hmac.compare_digest(token, secret)
            else:
                valid = not production

        if not valid:
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b'{"detail":"Invalid webhook signature"}'})
            return

        # --- Replay body as a fresh ASGI receive stream ------------------------
        _sent = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal _sent
            if _sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            _sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        # Inject raw_body into Starlette request.state via a scope shim
        # so handlers can do: raw = getattr(request.state, "raw_body", None)
        original_state = scope.get("state")
        if original_state is None:
            # Starlette lazily creates scope["state"] as a State object
            # We pre-populate it here.
            from starlette.datastructures import State
            state_obj = State()
            state_obj.raw_body = body
            scope["state"] = state_obj
        else:
            try:
                original_state.raw_body = body
            except Exception:
                pass

        await self.app(scope, replay_receive, send)


# ---------------------------------------------------------------------------
# Request identity lifecycle middleware (principal cleanup per request)
# ---------------------------------------------------------------------------


class PrincipalCleanupMiddleware:
    """Clears the thread-local/contextvar principal at the end of each request."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
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


# ---------------------------------------------------------------------------
# Terminal webhook normalizer (TaskGraph integration)
# ---------------------------------------------------------------------------


def install_terminal_webhook_normalizer() -> None:
    """Patch TaskGraph to normalize terminal webhook events.

    Called once from create_app() during application startup.
    """
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
            security_hold = (
                self.state.shared_data.get("verification_decision") == "security_hold"
                or commit_gateway.get("status") == "security_hold"
                or bool(self.state.shared_data.get("security_hold_reason"))
            )
            if security_hold:
                self.run_status = RunStatus.SECURITY_HOLD
            original_record(self)

        TaskGraph._fire_webhook = fire
        TaskGraph._record_run = record
        TaskGraph._loom_terminal_webhooks_patched = True
    except Exception:
        if os.getenv("LOOM_ENV", "production").lower() in {"prod", "production"}:
            raise


# ---------------------------------------------------------------------------
# Webhook secret encryption for the WebhookEngine
# ---------------------------------------------------------------------------


def install_webhook_secret_encryption() -> None:
    """Transparently encrypt/decrypt webhook subscription secrets at rest.

    Called once from create_app() when LOOM_WEBHOOK_SECRET_KEY is set.
    """
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

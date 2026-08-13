"""Late-bound hardening for components initialized during API import."""

from __future__ import annotations

import hmac
import os
from typing import Any, Callable

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


def apply_late_hardening(module: Any) -> None:
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

"""Credential-to-principal resolution shared by ASGI guards."""

from __future__ import annotations

import os
import secrets
from typing import Any

from loom.auth.api_tokens import get_api_token_store
from loom.auth.context import AuthenticatedPrincipal, get_service_principal


def principal_from_headers(headers: dict[str, str]) -> AuthenticatedPrincipal | None:
    raw = headers.get("authorization") or headers.get("x-api-key") or headers.get("x-dashboard-auth")
    if not raw:
        return None
    token = raw[7:].strip() if raw.lower().startswith("bearer ") else raw.strip()
    if not token:
        return None

    configured = os.getenv("API_KEY")
    if configured and secrets.compare_digest(token, configured):
        return get_service_principal()

    try:
        record: Any = get_api_token_store().verify(token)
    except Exception:
        return None
    if record is None:
        return None

    return AuthenticatedPrincipal(
        user_id=record.user_id,
        org_id=record.org_id,
        token_id=record.id,
        auth_method="api_token",
    )

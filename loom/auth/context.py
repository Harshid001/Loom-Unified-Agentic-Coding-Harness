"""Authenticated request identity shared by auth and RBAC layers."""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Identity established by a verified credential."""

    user_id: str
    org_id: str
    token_id: Optional[str] = None
    auth_method: str = "api_key"


_principal: ContextVar[Optional[AuthenticatedPrincipal]] = ContextVar(
    "loom_authenticated_principal", default=None
)


def set_principal(principal: AuthenticatedPrincipal) -> AuthenticatedPrincipal:
    _principal.set(principal)
    return principal


def get_principal() -> Optional[AuthenticatedPrincipal]:
    return _principal.get()


def clear_principal() -> None:
    _principal.set(None)


def get_service_principal() -> AuthenticatedPrincipal:
    """Resolve the fixed identity represented by the shared API key."""
    return AuthenticatedPrincipal(
        user_id=os.getenv("API_KEY_USER_ID", "dev_user"),
        org_id=os.getenv("API_KEY_ORG_ID", "default"),
        token_id=None,
        auth_method="api_key",
    )


def _is_secure_runtime() -> bool:
    """Return whether client-supplied identity headers must be ignored.

    Production is always secure, even when a stale/global DEV_MODE environment
    variable is present. Header-based identity compatibility is available only
    when development mode is explicitly selected *and* the development bypass
    is explicitly enabled.
    """
    env = os.getenv("LOOM_ENV", "").lower()
    dev_flag = os.getenv("DEV_MODE", "").lower()

    if env in {"prod", "production"}:
        return True

    return not (env == "development" and dev_flag in {"true", "1", "yes", "on"})


def get_effective_principal(
    user_id_header: Optional[str] = None,
    org_id_header: Optional[str] = None,
) -> AuthenticatedPrincipal:
    """Return credential-bound identity, never forged client headers in secure runtime."""
    current = get_principal()
    # API-token identities are request-bound and authoritative.
    # Shared API-key identity is derived from current environment so an old
    # API-key principal cannot leak across requests or tests.
    principal = current if current is not None and current.auth_method == "api_token" else get_service_principal()

    if _is_secure_runtime():
        return principal

    return AuthenticatedPrincipal(
        user_id=user_id_header or principal.user_id,
        org_id=org_id_header or principal.org_id,
        token_id=principal.token_id,
        auth_method=principal.auth_method,
    )


def resolve_request_org(client_org_id: Optional[str] = None) -> str:
    return get_effective_principal(org_id_header=client_org_id).org_id


def require_authenticated_principal() -> AuthenticatedPrincipal:
    principal = get_principal()
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return principal

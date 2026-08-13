"""Authenticated request identity shared by auth and RBAC layers."""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


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
    """Resolve the fixed identity represented by the shared API key.

    Client-supplied X-User-Id/X-Org-Id headers are never consulted here.
    """
    return AuthenticatedPrincipal(
        user_id=os.getenv("API_KEY_USER_ID", "dev_user"),
        org_id=os.getenv("API_KEY_ORG_ID", "default"),
        token_id=None,
        auth_method="api_key",
    )


def get_effective_principal() -> AuthenticatedPrincipal:
    principal = get_principal()
    return principal if principal is not None else get_service_principal()

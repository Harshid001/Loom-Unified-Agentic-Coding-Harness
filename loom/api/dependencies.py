"""Shared FastAPI dependency factories for the Loom API.

All Depends() callables that are used across multiple routers live here.
This eliminates module-level singleton initialization scattered in server.py.
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from loom.auth.api_tokens import get_api_token_store
from loom.auth.context import (
    get_effective_principal,
    get_service_principal,
    set_principal,
)
from loom.business.entitlements import EntitlementService
from loom.business.models import Membership, MembershipRole, Organization, OrgTier
from loom.business.rbac import RBACEnforcer
from loom.db.records_store import RunRecordStore, get_run_record_store

# ---------------------------------------------------------------------------
# Singleton accessors (lazy, test-overridable)
# ---------------------------------------------------------------------------

_entitlements: EntitlementService | None = None


def get_entitlements() -> EntitlementService:
    global _entitlements
    if _entitlements is None:
        svc = EntitlementService()
        default_org = Organization(id="default", name="Default", tier=OrgTier.SOLO)
        svc.register_org(default_org)
        svc.add_membership(Membership(user_id="dev_user", org_id="default", role=MembershipRole.OWNER))
        _entitlements = svc
    return _entitlements


def reset_entitlements() -> None:
    """Test helper — reset the singleton so tests can configure a fresh instance."""
    global _entitlements
    _entitlements = None


def get_records_store() -> RunRecordStore:
    return get_run_record_store()


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def is_dev_mode() -> bool:
    env = os.getenv("LOOM_ENV", "development").lower()
    dev_flag = os.getenv("DEV_MODE", "").lower()
    if env in ("prod", "production") or dev_flag in ("false", "0", "no"):
        return False
    return env == "development" or dev_flag in ("true", "1", "yes")


def get_required_api_key() -> str | None:
    return os.getenv("API_KEY")


# ---------------------------------------------------------------------------
# Authentication dependency
# ---------------------------------------------------------------------------

async def verify_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Authenticate via X-API-Key header (master key or per-user token).

    In development mode with no API_KEY configured, falls through and sets
    a service principal automatically. In production, always requires auth.
    """
    required_key = get_required_api_key()

    # Master API key match
    if required_key and x_api_key and secrets.compare_digest(x_api_key, required_key):
        set_principal(get_service_principal())
        return x_api_key

    # Per-user token
    if x_api_key:
        token_store = get_api_token_store()
        record = token_store.verify(x_api_key)
        if record is not None:
            from loom.auth.context import AuthenticatedPrincipal
            set_principal(AuthenticatedPrincipal(
                user_id=record.user_id,
                org_id=record.org_id,
                token_id=record.id,
                auth_method="api_token",
            ))
            return x_api_key

    # Dev mode fallback
    if not required_key:
        if is_dev_mode():
            set_principal(get_service_principal())
            return x_api_key or "dev_key"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API_KEY environment variable is not configured. Production mode requires API_KEY or valid auth token.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing X-API-Key header",
    )


# Annotated shorthand usable in route signatures
AuthDep = Annotated[str, Depends(verify_api_key)]


# ---------------------------------------------------------------------------
# Organization resolution
# ---------------------------------------------------------------------------

def _default_org_id() -> str:
    return get_entitlements()._orgs and next(iter(get_entitlements()._orgs)) or "default"


def resolve_org_id(
    x_org_id: str = Header(default="", alias="X-Org-Id"),
) -> str:
    if is_dev_mode():
        entitlements = get_entitlements()
        orgs = list(getattr(entitlements, "_orgs", {}).keys())
        return x_org_id or (orgs[0] if orgs else "default")
    return get_effective_principal().org_id


OrgIdDep = Annotated[str, Depends(resolve_org_id)]


# ---------------------------------------------------------------------------
# RBAC helper
# ---------------------------------------------------------------------------

def get_rbac(org_id: str, user_id: str = "dev_user") -> RBACEnforcer:
    role = get_entitlements().get_role(org_id, user_id)
    return RBACEnforcer(role)

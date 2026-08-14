"""Consolidated security dependency functions for the Loom API.

Every protected endpoint declares its security boundary by depending on one
or more callables from this module. No runtime route mutation occurs here.

Dependency chain for run-scoped endpoints:

    require_authenticated_principal()
          ↓
    require_org_membership()          (implicit via principal.org_id)
          ↓
    require_run_access(run_id, action)
          ↓
    endpoint()
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from loom.api.dependencies import AuthDep, get_entitlements, get_rbac, is_dev_mode
from loom.auth.context import AuthenticatedPrincipal, get_effective_principal, require_authenticated_principal
from loom.business.audit_log import get_audit_logger
from loom.business.models import AuditAction
from loom.business.rbac import Action, RBACEnforcer
from loom.db.records_store import get_run_record_store

# ---------------------------------------------------------------------------
# Principal extraction
# ---------------------------------------------------------------------------

async def get_principal(
    _auth: AuthDep,
) -> AuthenticatedPrincipal:
    """Return the authenticated principal after verifying the API key."""
    principal = get_effective_principal()
    if principal is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return principal


PrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_principal)]


# ---------------------------------------------------------------------------
# RBAC enforcement
# ---------------------------------------------------------------------------

async def require_run_permission(
    principal: PrincipalDep,
    x_user_id: str = Header(default="dev_user", alias="X-User-Id"),
) -> RBACEnforcer:
    """Require TRIGGER_RUN action on the caller's org."""
    enforcer = get_rbac(principal.org_id, x_user_id)
    enforcer.authorize(Action.TRIGGER_RUN, resource=f"org:{principal.org_id}")
    return enforcer


async def require_admin_permission(
    principal: PrincipalDep,
    x_user_id: str = Header(default="dev_user", alias="X-User-Id"),
) -> RBACEnforcer:
    """Require MODIFY_ENTITLEMENTS action on the caller's org."""
    enforcer = get_rbac(principal.org_id, x_user_id)
    enforcer.authorize(Action.MODIFY_ENTITLEMENTS, resource=f"org:{principal.org_id}")
    return enforcer


async def require_auditor_permission(
    principal: PrincipalDep,
    x_user_id: str = Header(default="dev_user", alias="X-User-Id"),
) -> RBACEnforcer:
    """Require EXPORT_EVIDENCE action on the caller's org."""
    enforcer = get_rbac(principal.org_id, x_user_id)
    enforcer.authorize(Action.EXPORT_EVIDENCE, resource=f"org:{principal.org_id}")
    return enforcer


async def require_token_admin(
    principal: PrincipalDep,
    x_user_id: str = Header(default="dev_user", alias="X-User-Id"),
) -> AuthenticatedPrincipal:
    """Require token-management RBAC permission."""
    enforcer = get_rbac(principal.org_id, x_user_id)
    enforcer.authorize(Action.MODIFY_ENTITLEMENTS, resource=f"org:{principal.org_id}")
    return principal


# ---------------------------------------------------------------------------
# Run-scoped authorization
# ---------------------------------------------------------------------------

def require_run_access(run_id: str, action: Action, *, principal: AuthenticatedPrincipal) -> object:
    """Resolve a run and authorize tenant + role access.

    Cross-tenant access is silently converted to 404 to avoid leaking run existence.
    Raises HTTPException on authorization failure.
    """
    records_store = get_run_record_store()
    entitlements = get_entitlements()

    run = records_store.get_run(run_id)

    if run is None or not getattr(run, "org_id", None) or run.org_id != principal.org_id:
        if run is not None:
            # Audit the cross-tenant access attempt
            try:
                get_audit_logger().record(
                    org_id=principal.org_id,
                    actor_id=principal.user_id,
                    action=AuditAction.RUN_AUTHORIZATION_DENIED,
                )
            except Exception:
                pass
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    role = entitlements.get_role(principal.org_id, principal.user_id)
    from loom.business.rbac import RBACEnforcer
    try:
        RBACEnforcer(role).authorize(action, resource=f"org:{run.org_id}")
    except HTTPException:
        try:
            get_audit_logger().record(
                org_id=principal.org_id,
                actor_id=principal.user_id,
                action=AuditAction.RUN_AUTHORIZATION_DENIED,
            )
        except Exception:
            pass
        raise

    return run


# ---------------------------------------------------------------------------
# Entitlement check dependency factory
# ---------------------------------------------------------------------------

def require_entitlement(feature_key):
    """Factory: return a dependency that checks org entitlement for feature_key."""

    async def _check(
        _auth: AuthDep,
        x_org_id: str = Header(default="", alias="X-Org-Id"),
    ) -> bool:
        principal = require_authenticated_principal()
        org_id = principal.org_id if not is_dev_mode() else (x_org_id or principal.org_id)
        result = get_entitlements().check(org_id, feature_key)
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.reason or f"Feature '{feature_key.value}' not available",
            )
        return True

    return _check

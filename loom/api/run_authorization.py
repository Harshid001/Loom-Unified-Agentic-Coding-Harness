"""Centralized run-level authorization for tenant-isolated API routes.

PRD-016: The ``install_run_authorization(module)`` runtime route-mutation
function has been replaced by calling ``require_run_access()`` directly as a
plain function inside each route handler.  No FastAPI dependency-graph patching
or sys.meta_path magic is needed.

The ``install_run_authorization`` name is kept as a no-op shim for any call
sites that have not yet been updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from loom.auth.context import AuthenticatedPrincipal, require_authenticated_principal
from loom.business.audit_log import get_audit_logger
from loom.business.entitlements import EntitlementService
from loom.business.models import AuditAction
from loom.business.rbac import Action, RBACEnforcer
from loom.db.records_store import RunRecordStore, get_run_record_store


@dataclass(frozen=True)
class AuthorizationContext:
    principal: AuthenticatedPrincipal
    entitlements: EntitlementService
    records_store: RunRecordStore


_RUN_ACTIONS: dict[tuple[str, str], Action] = {
    ("GET", "/runs/{run_id}"): Action.VIEW_RUN,
    ("GET", "/runs/{run_id}/evidence"): Action.VIEW_RUN,
    ("GET", "/runs/{run_id}/records"): Action.VIEW_RUN,
    ("GET", "/runs/{run_id}/ast"): Action.VIEW_RUN,
    ("POST", "/run/control"): Action.TRIGGER_RUN,
    ("GET", "/stream/{run_id}"): Action.VIEW_RUN,
    ("POST", "/runs/{run_id}/rollback"): Action.ROLLBACK_RUN,
    ("POST", "/rollback/{run_id}"): Action.ROLLBACK_RUN,
    ("POST", "/runs/{run_id}/ci-report"): Action.REPORT_CI,
}


def require_run_access(
    run_id: str,
    action: Action,
    *,
    context: AuthorizationContext | None = None,
    module: Any | None = None,
) -> Any:
    """Resolve a run from the authoritative record store and authorize its tenant.

    Cross-tenant access is silently converted to 404 to avoid leaking run
    existence to callers from other organizations.
    """
    if context is None:
        principal = require_authenticated_principal()
        entitlements: EntitlementService = (
            (getattr(module, "_entitlements", None) if module else None) or EntitlementService()
        )
        records_store = get_run_record_store()
        context = AuthorizationContext(
            principal=principal,
            entitlements=entitlements,
            records_store=records_store,
        )

    run = context.records_store.get_run(run_id)

    # Fail-closed: missing run, missing org_id, or cross-tenant access attempt
    if run is None or not getattr(run, "org_id", None) or run.org_id != context.principal.org_id:
        if run is not None:
            try:
                get_audit_logger().record(
                    org_id=context.principal.org_id,
                    actor_id=context.principal.user_id,
                    action=AuditAction.RUN_AUTHORIZATION_DENIED,
                )
            except Exception:
                pass
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    role = context.entitlements.get_role(context.principal.org_id, context.principal.user_id)
    try:
        RBACEnforcer(role).authorize(action, resource=f"org:{run.org_id}")
    except HTTPException:
        try:
            get_audit_logger().record(
                org_id=context.principal.org_id,
                actor_id=context.principal.user_id,
                action=AuditAction.RUN_AUTHORIZATION_DENIED,
            )
        except Exception:
            pass
        raise

    return run


def _normalize_path(path: str) -> str:
    normalized = path
    for prefix in ("/api/v1", "/api", "/v1"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized or "/"


def _route_action(method: str, path: str) -> Action | None:
    return _RUN_ACTIONS.get((method.upper(), _normalize_path(path)))


def install_run_authorization(module: Any) -> None:  # noqa: ARG001
    """No-op shim.  Authorization is now declared via explicit Depends() in each route.

    Retained to avoid ImportError during the transition period.
    """

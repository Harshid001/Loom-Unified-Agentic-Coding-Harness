"""Centralized run-level authorization for tenant-isolated API routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import fastapi.dependencies.utils as fastapi_dep_utils
from fastapi import Depends, HTTPException, status

from loom.auth.context import AuthenticatedPrincipal, require_authenticated_principal
from loom.business.audit_log import get_audit_logger
from loom.business.entitlements import EntitlementService
from loom.business.models import AuditAction
from loom.business.rbac import Action, RBACEnforcer
from loom.db.records_store import RunRecordStore, get_run_record_store

get_dependant = fastapi_dep_utils.get_dependant
get_parameterless_sub_dependant = fastapi_dep_utils.get_parameterless_sub_dependant
get_flat_dependant: Any = getattr(fastapi_dep_utils, "get_flat_dependant", None)


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
    """Resolve a run from the authoritative record store and authorize its tenant."""
    if context is None:
        principal = require_authenticated_principal()
        entitlements: EntitlementService = (getattr(module, "_entitlements", None) if module else None) or EntitlementService()
        records_store = get_run_record_store()
        context = AuthorizationContext(
            principal=principal,
            entitlements=entitlements,
            records_store=records_store,
        )

    run = context.records_store.get_run(run_id)

    # Fail-closed check: missing run, missing/empty org_id, or cross-tenant access attempt
    if run is None or not getattr(run, "org_id", None) or run.org_id != context.principal.org_id:
        if run is not None:
            # Audit log cross-tenant security violation internally
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


def install_run_authorization(module: Any) -> None:
    """Install run authorization as FastAPI dependencies idempotently without replacing endpoints."""
    app = module.app

    for route in list(getattr(app, "routes", [])):
        endpoint = getattr(route, "endpoint", None)
        path = getattr(route, "path", "")
        methods = {str(method).upper() for method in (getattr(route, "methods", None) or set())}
        action = next((_route_action(method, path) for method in methods if _route_action(method, path) is not None), None)
        if endpoint is None or action is None:
            continue

        marker = "_loom_run_authorized"
        if getattr(route, marker, False):
            continue

        def _make_auth_dep(target_action: Action):
            async def authorize_run_dependency(
                run_id: str,
                _auth: Any = Depends(module.verify_api_key),
            ) -> None:
                require_run_access(run_id, target_action, module=module)

            return authorize_run_dependency

        auth_dep = _make_auth_dep(action)

        dependencies = list(getattr(route, "dependencies", []) or [])
        dependencies.append(Depends(auth_dep))
        route.dependencies = dependencies
        path_format = getattr(route, "path_format", route.path)
        route.dependant = get_dependant(path=path_format, call=route.endpoint, scope="function")
        for depends in route.dependencies[::-1]:
            route.dependant.dependencies.insert(
                0,
                get_parameterless_sub_dependant(depends=depends, path=path_format),
            )
        if hasattr(route, "_flat_dependant") and callable(get_flat_dependant):
            route._flat_dependant = get_flat_dependant(route.dependant)
        if hasattr(route, "get_route_handler"):
            from fastapi.routing import request_response
            route.app = request_response(route.get_route_handler())
        setattr(route, marker, True)

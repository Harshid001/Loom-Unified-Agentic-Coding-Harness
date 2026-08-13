"""Centralized run-level authorization for tenant-isolated API routes."""

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.dependencies.utils import get_dependant, get_flat_dependant, get_parameterless_sub_dependant

from loom.auth.context import require_authenticated_principal
from loom.business.rbac import Action, RBACEnforcer
from loom.db.records_store import get_run_record_store

_RUN_ACTIONS: dict[tuple[str, str], Action] = {
    ("GET", "/runs/{run_id}"): Action.VIEW_RUN,
    ("GET", "/runs/{run_id}/evidence"): Action.VIEW_RUN,
    ("GET", "/runs/{run_id}/records"): Action.VIEW_RUN,
    ("GET", "/stream/{run_id}"): Action.VIEW_RUN,
    ("POST", "/runs/{run_id}/rollback"): Action.ROLLBACK_RUN,
    ("POST", "/rollback/{run_id}"): Action.ROLLBACK_RUN,
    ("POST", "/runs/{run_id}/ci-report"): Action.REPORT_CI,
}


def require_run_access(run_id: str, action: Action, *, module: Any) -> Any:
    """Resolve a run from the authoritative record store and authorize its tenant."""
    principal = require_authenticated_principal()
    run = get_run_record_store().get_run(run_id)
    if run is None or run.org_id != principal.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    role = module._entitlements.get_role(principal.org_id, principal.user_id)
    RBACEnforcer(role).authorize(action, resource=f"org:{run.org_id}")
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
    """Install run authorization as FastAPI dependencies without replacing endpoints."""
    app = module.app

    for route in list(getattr(app, "routes", [])):
        endpoint = getattr(route, "endpoint", None)
        path = getattr(route, "path", "")
        methods = {str(method).upper() for method in (getattr(route, "methods", None) or set())}
        action = next((_route_action(method, path) for method in methods), None)
        if endpoint is None or action is None:
            continue

        marker = "_loom_run_authorized"
        if getattr(endpoint, marker, False):
            continue

        async def authorize_run_dependency(
            run_id: str,
            _auth: Any = Depends(module.verify_api_key),
            *,
            __action: Action = action,
        ) -> None:
            require_run_access(run_id, __action, module=module)

        setattr(authorize_run_dependency, marker, True)
        dependencies = list(getattr(route, "dependencies", []) or [])
        dependencies.append(Depends(authorize_run_dependency))
        route.dependencies = dependencies
        path_format = getattr(route, "path_format", route.path)
        route.dependant = get_dependant(path=path_format, call=route.endpoint, scope="function")
        for depends in route.dependencies[::-1]:
            route.dependant.dependencies.insert(
                0,
                get_parameterless_sub_dependant(depends=depends, path=path_format),
            )
        if hasattr(route, "_flat_dependant"):
            route._flat_dependant = get_flat_dependant(route.dependant)
        setattr(endpoint, marker, True)

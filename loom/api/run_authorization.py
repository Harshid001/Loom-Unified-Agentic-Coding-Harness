"""Centralized run-level authorization for tenant-isolated API routes."""

import asyncio
from typing import Any

from fastapi import HTTPException, status

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
    """Resolve a run from the authoritative record store and authorize its tenant.

    Missing and cross-tenant runs deliberately collapse to the same 404 response so
    an authenticated principal cannot use a run id as a tenant-discovery oracle.
    """
    principal = require_authenticated_principal()
    run = get_run_record_store().get_run(run_id)
    if run is None or run.org_id != principal.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    role = module._entitlements.get_role(principal.org_id, principal.user_id)
    RBACEnforcer(role).authorize(action, resource=f"org:{run.org_id}")
    return run


def _route_action(method: str, path: str) -> Action | None:
    return _RUN_ACTIONS.get((method.upper(), path))


def _set_route_callable(route: Any, endpoint: Any) -> None:
    """Update both FastAPI's public endpoint and its resolved dependency callable."""
    route.endpoint = endpoint
    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        dependant.call = endpoint


def install_run_authorization(module: Any) -> None:
    """Wrap only run-scoped routes after FastAPI routes have been registered."""
    app = module.app

    for route in list(getattr(app, "routes", [])):
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        methods = {str(method).upper() for method in (getattr(route, "methods", None) or set())}
        action = None
        for method in methods:
            candidate = _route_action(method, _normalize_path(path))
            if candidate is not None:
                action = candidate
                break
        if endpoint is None or action is None:
            continue
        if getattr(endpoint, "_loom_run_authorized", False):
            continue

        if asyncio.iscoroutinefunction(endpoint):
            async def guarded_async(*args: Any, __endpoint: Any = endpoint, __action: Action = action, **kwargs: Any) -> Any:
                run_id = str(kwargs.get("run_id") or (args[0] if args else ""))
                require_run_access(run_id, __action, module=module)
                return await __endpoint(*args, **kwargs)

            guarded_async.__name__ = getattr(endpoint, "__name__", "guarded_run_endpoint")
            guarded_async.__doc__ = getattr(endpoint, "__doc__", None)
            setattr(guarded_async, "_loom_run_authorized", True)
            _set_route_callable(route, guarded_async)
        else:
            def guarded_sync(*args: Any, __endpoint: Any = endpoint, __action: Action = action, **kwargs: Any) -> Any:
                run_id = str(kwargs.get("run_id") or (args[0] if args else ""))
                require_run_access(run_id, __action, module=module)
                return __endpoint(*args, **kwargs)

            guarded_sync.__name__ = getattr(endpoint, "__name__", "guarded_run_endpoint")
            guarded_sync.__doc__ = getattr(endpoint, "__doc__", None)
            setattr(guarded_sync, "_loom_run_authorized", True)
            _set_route_callable(route, guarded_sync)


def _normalize_path(path: str) -> str:
    """Map versioned and legacy route prefixes onto one authorization table."""
    normalized = path
    for prefix in ("/api/v1", "/api", "/v1"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized or "/"

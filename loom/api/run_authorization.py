"""Centralized run-level authorization for tenant-isolated API routes."""

from __future__ import annotations

import asyncio
import functools
import os
from typing import Any

from fastapi import HTTPException, status

from loom.auth.context import get_principal
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


def _is_dev_mode() -> bool:
    env = os.getenv("LOOM_ENV", "development").lower()
    dev_flag = os.getenv("DEV_MODE", "").lower()
    if env in ("prod", "production") or dev_flag in ("false", "0", "no"):
        return False
    return env == "development" or dev_flag in ("true", "1", "yes")


def require_run_access(run_id: str, action: Action, *, module: Any = None) -> Any:
    """Resolve a run from the authoritative record store and authorize its tenant.

    Missing and cross-tenant runs deliberately collapse to the same 404 response so
    an authenticated principal cannot use a run id as a tenant-discovery oracle.
    """
    principal = get_principal()
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    org_id = None
    run = get_run_record_store().get_run(run_id)
    if run is not None:
        org_id = run.org_id
    else:
        if module is not None and hasattr(module, "ACTIVE_RUNS"):
            active = getattr(module, "ACTIVE_RUNS", {}).get(run_id)
            if isinstance(active, dict) and "state" in active:
                org_id = str(getattr(active["state"], "shared_data", {}).get("org_id", "default"))
        if org_id is None:
            try:
                from loom.orchestrator.state import OrchestratorState
                chk = OrchestratorState.load_checkpoint(run_id)
                if chk is not None:
                    org_id = str(chk.shared_data.get("org_id", "default"))
            except Exception:
                pass

    if org_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if principal.org_id != org_id and principal.org_id != "default":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    from loom.business.models import MembershipRole

    if principal.org_id == "default":
        role = MembershipRole.OWNER
    else:
        get_ent = getattr(module, "get_entitlements", None) if module is not None else None
        entitlements = get_ent() if get_ent is not None else None
        if entitlements is None:
            role = getattr(module, "_entitlements", None) and module._entitlements.get_role(org_id, principal.user_id) or MembershipRole.OWNER
        else:
            role = entitlements.get_role(org_id, principal.user_id)

    RBACEnforcer(role).authorize(action, resource=f"org:{org_id}")
    return run


def _route_action(method: str, path: str) -> Action | None:
    return _RUN_ACTIONS.get((method.upper(), path))


def _set_route_callable(route: Any, endpoint: Any) -> None:
    """Update both FastAPI's public endpoint and its resolved dependency callable."""
    route.endpoint = endpoint
    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        dependant.call = endpoint
        dependant.is_coroutine = asyncio.iscoroutinefunction(endpoint)


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
            @functools.wraps(endpoint)
            async def guarded_async(*args: Any, __endpoint: Any = endpoint, __action: Action = action, **kwargs: Any) -> Any:
                run_id = str(kwargs.get("run_id") or (args[0] if args else ""))
                require_run_access(run_id, __action, module=module)
                return await __endpoint(*args, **kwargs)

            guarded_async._loom_run_authorized = True
            _set_route_callable(route, guarded_async)
        else:
            @functools.wraps(endpoint)
            def guarded_sync(*args: Any, __endpoint: Any = endpoint, __action: Action = action, **kwargs: Any) -> Any:
                run_id = str(kwargs.get("run_id") or (args[0] if args else ""))
                require_run_access(run_id, __action, module=module)
                return __endpoint(*args, **kwargs)

            guarded_sync._loom_run_authorized = True
            _set_route_callable(route, guarded_sync)


def _normalize_path(path: str) -> str:
    """Map versioned and legacy route prefixes onto one authorization table."""
    normalized = path
    for prefix in ("/api/v1", "/api", "/v1"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized or "/"

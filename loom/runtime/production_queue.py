"""Production-only request adapter that converts run creation into durable jobs."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.routing import APIRoute

from loom.api import server as server_module
from loom.api.routes import iter_routes
from loom.business.models import RunRecord
from loom.db.records_store import get_run_record_store
from loom.runtime.job_queue import JobQueue, RunJob


async def _production_create_run(
    req: server_module.RunRequest,
    _rbac: server_module.RBACEnforcer = Depends(server_module.require_run_permission),
    org_id: str = Depends(server_module.resolve_org_id),
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_idempotency_key_header: Optional[str] = Header(None, alias="X-Idempotency-Key"),
) -> dict[str, Any]:
    """Validate the production request and enqueue it without executing in API memory."""
    org = server_module._entitlements.get_org(org_id) or server_module._default_org
    sandbox_tier = (req.sandbox_tier or "A").upper()
    if sandbox_tier not in {"A", "B", "C"}:
        raise HTTPException(status_code=400, detail=f"Invalid sandbox_tier: {req.sandbox_tier}")

    tier_gated_feature = {
        "B": server_module.FeatureKey.SANDBOX_TIER_B_CONTAINER,
        "C": server_module.FeatureKey.SANDBOX_TIER_C_MICROVM,
    }
    feature = tier_gated_feature.get(sandbox_tier)
    if feature:
        result = server_module._entitlements.check(org_id, feature)
        if not result.allowed:
            raise HTTPException(status_code=403, detail=result.reason)

    from loom.business.usage_ledger import get_usage_ledger

    snapshot = get_usage_ledger().build_snapshot(org_id, org.tier)
    ok, reason = server_module._entitlements.evaluate_quota(org_id, snapshot)
    if not ok:
        raise HTTPException(status_code=402, detail=reason)

    run_id = f"run_{uuid.uuid4().hex}"
    req_repo = req.repo_path or "."
    if req_repo.startswith("https://") or req_repo.startswith("git@") or "github.com" in req_repo:
        from loom.api.server import clone_remote_repo
        from loom.integrations.github_client import resolve_vault_token

        token = None
        try:
            token = resolve_vault_token(f"vault:{org_id}", allow_ambient_fallback=True)
        except Exception:
            token = server_module.os.getenv("GITHUB_TOKEN", server_module.os.getenv("GH_TOKEN", None))

        raw_path = clone_remote_repo(req_repo, run_id, token=token or None)
    else:
        raw_path = Path(req_repo).resolve()
        if not raw_path.exists() or not raw_path.is_dir():
            raise HTTPException(status_code=400, detail="Target repo_path does not exist or is not a directory")

        allowed_roots = server_module.os.getenv("ALLOWED_REPO_ROOTS")
        if not allowed_roots:
            raise HTTPException(status_code=403, detail="ALLOWED_REPO_ROOTS is required in production")
        roots = [Path(item.strip()).resolve() for item in allowed_roots.split(",") if item.strip()]
        if not any(root == raw_path or root in raw_path.parents for root in roots):
            raise HTTPException(status_code=403, detail="repo_path is not within allowed repository roots")
    job = RunJob(
        job_id=f"job_{uuid.uuid4().hex}",
        run_id=run_id,
        org_id=org_id,
        repo_path=str(raw_path),
        issue=req.issue,
        model=req.model,
        mock=req.mock,
        sandbox_tier=sandbox_tier,
        auto_merge_threshold=org.auto_merge_threshold,
        created_at=time.time(),
    )

    get_run_record_store().record_run(
        RunRecord(
            run_id=run_id,
            org_id=org_id,
            repo_id=str(raw_path),
            issue_text=req.issue,
            status="queued",
            sandbox_tier=sandbox_tier,
        )
    )

    await JobQueue().enqueue(job)
    return {
        "run_id": run_id,
        "job_id": job.job_id,
        "status": "QUEUED",
        "stream_url": f"/api/v1/stream/{run_id}",
        "execution": "distributed",
    }


def install_production_queue(app: FastAPI) -> None:
    """Replace only the run-creation route with durable queue submission."""
    if not server_module.is_dev_mode() and not server_module.os.getenv("REDIS_URL"):
        raise RuntimeError("Production execution requires REDIS_URL")

    for route in iter_routes(app):
        if not isinstance(route, APIRoute):
            continue
        if route.path in {"/api/v1/run", "/api/run"}:
            route.endpoint = _production_create_run
            route.dependant.call = _production_create_run
    app.state.durable_jobs_installed = True

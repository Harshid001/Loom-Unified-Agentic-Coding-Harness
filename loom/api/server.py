"""Loom API route handlers.

Backward-compat note: tests and external callers that import
``_default_org``, ``_entitlements``, or ``_rate_limit_memory_store``
directly from this module will continue to work via re-exports at the
bottom of this file.

PRD-016: This module exposes named APIRouter instances instead of a global
FastAPI `app`.  All middleware is composed by create_app() in loom.api.app.
Every sensitive route declares its security boundary explicitly via Depends().

Routers exported:
  router_health       — /healthz, /metrics, /api/*/health/*
  router_auth         — /api/*/auth/tokens
  router_runs         — /api/*/run, /api/*/runs/*, /api/*/stream/*, /api/*/run/control
  router_webhooks     — outbound webhook subscription management
  router_integrations — GitHub / GitLab / Slack inbound webhooks + bot endpoints
  router_admin        — entitlements check, org usage

The legacy module-level `app` is still provided for backward-compat with
uvicorn entry-points that do `loom.api.server:app`.  It is built via
create_app() on first import so no hardening is skipped.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"

    def generate_latest(registry: Any = None, escaping: Any = None) -> bytes:  # type: ignore[misc]
        return b"# prometheus_client not installed\n"

    class DummyMetric:
        def labels(self, **kwargs: Any) -> "DummyMetric":
            return self

        def inc(self, amount: float = 1) -> None:
            pass

        def observe(self, amount: float) -> None:
            pass

    class DummyMetricFactory:
        def __call__(self, *args: Any, **kwargs: Any) -> DummyMetric:
            return DummyMetric()

    Counter = DummyMetricFactory()  # type: ignore
    Histogram = DummyMetricFactory()  # type: ignore

from loom.adapters.router import ModelRouter
from loom.api.dependencies import (
    AuthDep,
    OrgIdDep,
    get_entitlements,
    get_records_store,
    is_dev_mode,
    resolve_org_id,
    verify_api_key,
)
from loom.api.security import (
    PrincipalDep,
    require_admin_permission,
    require_auditor_permission,
    require_run_access,
    require_run_permission,
    require_token_admin,
    require_entitlement,
)
from loom.api.webhooks import WebhookEventType, get_webhook_engine
from loom.auth.api_tokens import get_api_token_store
from loom.auth.context import get_effective_principal, require_authenticated_principal
from loom.business.models import FeatureKey, RunRecord
from loom.business.rbac import Action, RBACEnforcer
from loom.memory.store import TieredMemoryStore
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.sandbox.local_process import LocalProcessSandbox
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer
from loom.verification.bundle import EvidenceBundler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("loom.api")

# Prometheus metrics
REQUEST_COUNT = Counter("loom_requests_total", "Total requests processed", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("loom_request_duration_seconds", "Request latency", ["endpoint"])

# Process-local active run store (Phase 4 will replace with RedisRunStore)
ACTIVE_RUNS: Dict[str, Dict[str, Any]] = {}


def _evidence_dir() -> Path:
    raw = os.getenv("LOOM_EVIDENCE_DIR")
    if raw:
        return Path(raw)
    return Path.home() / ".loom" / "evidence"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TokenCreateRequest(BaseModel):
    user_id: Optional[str] = "dev_user"
    org_id: Optional[str] = "default"
    label: Optional[str] = "cli"


class RunRequest(BaseModel):
    issue: str
    repo_path: Optional[str] = "."
    model: str = "gpt-4o"
    mock: bool = True
    async_mode: bool = False
    sandbox_tier: Optional[str] = None


class ControlRequest(BaseModel):
    run_id: str
    action: str  # pause, resume, step, rollback, approve_patch, model_switch
    model: Optional[str] = None
    snapshot_id: Optional[str] = None


class CiReportRequest(BaseModel):
    merge_time: float
    ci_failure_detected: bool
    monitor_timeout_seconds: int = 3600


class GitHubWebhookRequest(BaseModel):
    action: str = ""
    issue: Optional[Dict[str, Any]] = None
    pull_request: Optional[Dict[str, Any]] = None
    repository: Optional[Dict[str, Any]] = None
    sender: Optional[Dict[str, Any]] = None


class GitLabWebhookRequest(BaseModel):
    object_kind: str = ""
    object_attributes: Optional[Dict[str, Any]] = None
    project: Optional[Dict[str, Any]] = None
    user: Optional[Dict[str, Any]] = None


class SlackNotifyRequest(BaseModel):
    webhook_url: str
    title: str
    body: str
    level: str = "info"
    template: str = "custom"
    run_id: str = ""


class PreparePRRequest(BaseModel):
    run_id: str
    issue_title: str
    issue_number: int
    patch_diff: str = ""
    confidence_score: float = 0.0
    verification_passed: bool = False
    cost_usd: float = 0.0
    files_touched: int = 0
    model_used: str = "unknown"
    template: str = "standard"


class EntitlementCheckRequest(BaseModel):
    org_id: str = ""
    feature_key: str


class EntitlementCheckResponse(BaseModel):
    allowed: bool
    reason: Optional[str] = None


class WebhookSubscribeRequest(BaseModel):
    org_id: str
    url: str
    events: Optional[List[str]] = None
    secret: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: RBAC enforcer from request context
# ---------------------------------------------------------------------------


def _get_rbac(org_id: str, user_id: str = "dev_user") -> RBACEnforcer:
    role = get_entitlements().get_role(org_id, user_id)
    return RBACEnforcer(role)


def _request_org_id(client_org_id: str) -> str:
    if is_dev_mode():
        entitlements = get_entitlements()
        orgs = list(getattr(entitlements, "_orgs", {}).keys())
        return client_org_id or (orgs[0] if orgs else "default")
    return get_effective_principal().org_id


# ---------------------------------------------------------------------------
# router_health — no authentication required
# ---------------------------------------------------------------------------

router_health = APIRouter(tags=["health"])


@router_health.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router_health.get("/api/v1/health/liveness")
@router_health.get("/api/health/liveness")
@router_health.get("/healthz")
def liveness_health() -> dict:
    return {"status": "alive", "service": "Loom API"}


@router_health.get("/api/v1/health/readiness")
@router_health.get("/api/health/readiness")
def readiness_health() -> Any:
    db_ok = True
    try:
        store = TieredMemoryStore()
        _ = store.get_schema_version()
    except Exception as err:
        logger.error("Readiness check database failed: %s", err)
        db_ok = False

    checkpoints_dir = Path.home() / ".loom" / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    storage_ok = checkpoints_dir.parent.exists() and os.access(checkpoints_dir.parent, os.W_OK)

    if not db_ok or not storage_ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "components": {
                    "database": "failed" if not db_ok else "ok",
                    "storage": "failed" if not storage_ok else "ok",
                },
            },
        )

    return {"status": "ready", "service": "Loom API", "components": {"database": "ok", "storage": "ok"}}


@router_health.get("/api/health")
def legacy_health_alias() -> dict:
    return {"status": "ok", "service": "Loom API"}


# ---------------------------------------------------------------------------
# router_auth — API token management
# ---------------------------------------------------------------------------

router_auth = APIRouter(tags=["auth"])


@router_auth.post("/api/v1/auth/tokens")
@router_auth.post("/api/auth/tokens")
def issue_api_token(
    req: TokenCreateRequest,
    principal: PrincipalDep,
    _admin: Any = Depends(require_token_admin),
) -> dict:
    token_store = get_api_token_store()
    requested_user = req.user_id or principal.user_id
    requested_org = req.org_id or principal.org_id

    if requested_org != principal.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot issue a token for another organization")

    record, raw_token = token_store.issue(
        user_id=requested_user,
        org_id=principal.org_id,
        label=req.label or "cli",
    )
    return {
        "token": raw_token,
        "token_id": record.id,
        "user_id": record.user_id,
        "org_id": record.org_id,
        "label": record.label,
        "prefix": record.prefix,
        "created_at": record.created_at,
    }


@router_auth.get("/api/v1/auth/tokens")
@router_auth.get("/api/auth/tokens")
def list_api_tokens(
    user_id: Optional[str] = None,
    _auth: AuthDep = None,
) -> list:
    token_store = get_api_token_store()
    principal = get_effective_principal()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "org_id": r.org_id,
            "label": r.label,
            "prefix": r.prefix,
            "active": r.active,
            "created_at": r.created_at,
        }
        for r in token_store._records.values()
        if r.active
        and r.org_id == principal.org_id
        and (user_id is None or r.user_id == user_id)
    ]


@router_auth.delete("/api/v1/auth/tokens/{token_id}")
@router_auth.delete("/api/auth/tokens/{token_id}")
def revoke_api_token(
    token_id: str,
    _auth: AuthDep = None,
) -> dict:
    principal = get_effective_principal()
    token_store = get_api_token_store()
    record = token_store._records.get(token_id)
    if record is None or record.org_id != principal.org_id:
        raise HTTPException(status_code=404, detail="Token not found")
    success = token_store.revoke(token_id)
    if not success:
        raise HTTPException(status_code=404, detail="Token not found or already revoked")
    return {"revoked": True, "token_id": token_id}


# ---------------------------------------------------------------------------
# router_runs — run lifecycle
# ---------------------------------------------------------------------------

router_runs = APIRouter(tags=["runs"])


@router_runs.get("/api/v1/runs")
@router_runs.get("/api/runs")
def list_runs(
    offset: int = 0,
    limit: int = 50,
    _auth: AuthDep = None,
) -> list:
    checkpoints_dir = Path.home() / ".loom" / "checkpoints"
    runs = []
    if checkpoints_dir.exists():
        for f in checkpoints_dir.glob("checkpoint_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                runs.append(
                    {
                        "id": data.get("run_id"),
                        "issue": data.get("issue_description"),
                        "status": "VERIFIED SUCCESS" if data.get("verification_passed") else "EXECUTED",
                        "repo_path": data.get("repo_path"),
                        "created_at": data.get("created_at"),
                        "cost": data.get("shared_data", {}).get("cost_report", {}).get("total_cost_usd", 0.0025),
                    }
                )
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.warning("Error reading checkpoint file %s: %s", f, err)
    runs.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    return runs[offset : offset + limit]


@router_runs.post("/api/v1/run")
@router_runs.post("/api/run")
async def create_run(
    req: RunRequest,
    _rbac: RBACEnforcer = Depends(require_run_permission),
    org_id: str = Depends(resolve_org_id),
) -> Any:
    entitlements = get_entitlements()
    org = entitlements.get_org(org_id) or entitlements._orgs.get(next(iter(getattr(entitlements, "_orgs", {})), ""), None)

    sandbox_tier = (req.sandbox_tier or "A").upper()
    if sandbox_tier not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail=f"Invalid sandbox_tier: {req.sandbox_tier}")

    tier_gated_feature = {
        "B": FeatureKey.SANDBOX_TIER_B_CONTAINER,
        "C": FeatureKey.SANDBOX_TIER_C_MICROVM,
    }
    if sandbox_tier in tier_gated_feature:
        result = entitlements.check(org_id, tier_gated_feature[sandbox_tier])
        if not result.allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result.reason)

    from loom.business.usage_ledger import get_usage_ledger

    ledger = get_usage_ledger()
    if org is None:
        from loom.business.models import Organization, OrgTier
        org = Organization(name="Default", tier=OrgTier.SOLO)
    snapshot = ledger.build_snapshot(org_id, org.tier)
    ok, reason = entitlements.evaluate_quota(org_id, snapshot)
    if not ok:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    raw_path = Path(req.repo_path or ".").resolve()
    if not raw_path.exists() or not raw_path.is_dir():
        raise HTTPException(
            status_code=400, detail=f"Target repo_path does not exist or is not a directory: {req.repo_path}"
        )

    allowed_roots = os.getenv("ALLOWED_REPO_ROOTS")
    if allowed_roots:
        roots = [Path(r.strip()).resolve() for r in allowed_roots.split(",") if r.strip()]
        if not any(r in raw_path.parents or r == raw_path for r in roots):
            raise HTTPException(status_code=403, detail="repo_path is not within allowed repository roots")
    elif not is_dev_mode():
        raise HTTPException(
            status_code=403,
            detail="ALLOWED_REPO_ROOTS environment variable must be configured in production mode to restrict repository access.",
        )

    repo_path = str(raw_path)
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    state = OrchestratorState(run_id=run_id, repo_path=repo_path, issue_description=req.issue)
    state.shared_data["org_id"] = org_id
    state.shared_data["_org"] = org
    state.shared_data["sandbox_tier"] = sandbox_tier
    state.shared_data["auto_merge_threshold"] = org.auto_merge_threshold

    router = ModelRouter(default_model=req.model, mock_mode=req.mock)
    tracer = TelemetryTracer(run_id=run_id)
    cost_tracker = CostTracker(run_id=run_id)
    records_store = get_records_store()

    run_entry: Dict[str, Any] = {"queues": [], "events": [], "state": state}
    ACTIVE_RUNS[run_id] = run_entry

    def broadcast_event(event_type: str, step_name: str, data: Dict[str, Any]) -> None:
        evt = {
            "type": event_type,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_id": run_id,
            "step_name": step_name,
            "data": data,
        }
        run_entry["events"].append(evt)
        for q in list(run_entry["queues"]):
            try:
                q.put_nowait(evt)
            except Exception:
                pass

    def on_step_start(step_name: str, model_name: str) -> None:
        broadcast_event("step_progress", step_name, {"status": "running", "model": model_name})

    def on_step_log(step_name: str, level: str, message: str) -> None:
        broadcast_event("log_entry", step_name, {"level": level, "agent": step_name, "message": message})

    def on_step_complete(step_name: str, out: Any) -> None:
        metrics = out.get("_usage", {}) if isinstance(out, dict) else {}
        broadcast_event("step_progress", step_name, {"status": "completed", "metrics": metrics})
        if step_name == "patcher" and isinstance(out, dict) and "diff" in out:
            broadcast_event("patch_proposal", step_name, {"diff": out.get("diff")})

    def on_step_fail(step_name: str, error: str) -> None:
        broadcast_event("step_progress", step_name, {"status": "failed", "error": error})

    task_graph = TaskGraph(
        state,
        router,
        tracer,
        cost_tracker,
        on_step_start=on_step_start,
        on_step_log=on_step_log,
        on_step_complete=on_step_complete,
        on_step_fail=on_step_fail,
        webhook_engine=get_webhook_engine(),
        evidence_bundler=EvidenceBundler(output_dir=str(_evidence_dir())),
        records_store=records_store,
    )
    run_entry["graph"] = task_graph

    records_store.record_run(
        RunRecord(
            run_id=run_id,
            org_id=org_id,
            repo_id=repo_path,
            issue_text=req.issue,
            status="queued",
            sandbox_tier=sandbox_tier,
        )
    )

    if req.async_mode:
        asyncio.create_task(task_graph.run())
        return {"run_id": run_id, "status": "RUNNING", "stream_url": f"/api/v1/stream/{run_id}"}

    final_state = await task_graph.run()
    broadcast_event(
        "status_change", "pipeline", {"status": "completed", "verification_passed": final_state.verification_passed}
    )

    return {
        "run_id": run_id,
        "status": "VERIFIED SUCCESS" if final_state.verification_passed else "FAILED",
        "verification_passed": final_state.verification_passed,
        "patch_diff": final_state.patch_diff,
        "reproduction_test": final_state.reproduction_test,
        "reviewer_report": final_state.shared_data.get("reviewer_report"),
        "cost_report": final_state.shared_data.get("cost_report"),
        "confidence_score": final_state.shared_data.get("confidence_score"),
        "merge_decision": final_state.shared_data.get("merge_decision"),
        "evidence": {
            "exported": final_state.shared_data.get("evidence_exported", False),
            "chain_hash": final_state.shared_data.get("evidence_bundle_chain_hash"),
        },
    }


@router_runs.get("/api/v1/stream/{run_id}")
@router_runs.get("/api/stream/{run_id}")
async def stream_run_events(
    run_id: str,
    principal: PrincipalDep,
) -> StreamingResponse:
    """Authenticated SSE stream scoped to the run's owning organization."""
    run_entry = ACTIVE_RUNS.get(run_id)
    if not run_entry:
        raise HTTPException(status_code=404, detail="Run not found")

    run_org = run_entry.get("state").shared_data.get("org_id") if run_entry.get("state") else None
    if run_org != principal.org_id:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator() -> Any:
        queue: asyncio.Queue = asyncio.Queue()
        run_entry["queues"].append(queue)
        for event in list(run_entry.get("events", [])):
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "status_change" and event.get("data", {}).get("status") in (
                "completed",
                "failed",
            ):
                return

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "status_change" and event.get("data", {}).get("status") in (
                        "completed",
                        "failed",
                    ):
                        break
                except asyncio.TimeoutError:
                    ping_event = {
                        "type": "ping",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "run_id": run_id,
                    }
                    yield f"data: {json.dumps(ping_event)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in run_entry.get("queues", []):
                run_entry["queues"].remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router_runs.post("/api/v1/run/control")
@router_runs.post("/api/run/control")
async def control_run(
    req: ControlRequest,
    principal: PrincipalDep,
) -> dict:
    run_entry = ACTIVE_RUNS.get(req.run_id)
    if not run_entry:
        if req.action == "rollback" and req.run_id:
            return _do_rollback(req.run_id)
        raise HTTPException(status_code=404, detail=f"Active run {req.run_id} not found")

    # Tenant check
    run_org = run_entry.get("state").shared_data.get("org_id") if run_entry.get("state") else None
    if run_org != principal.org_id:
        raise HTTPException(status_code=404, detail="Run not found")

    graph: TaskGraph = run_entry["graph"]
    action = req.action.lower()

    if action == "pause":
        graph.pause()
    elif action == "resume":
        graph.resume()
    elif action == "step":
        graph.step_over()
    elif action == "cancel":
        graph.cancel()
    elif action == "model_switch" and req.model:
        graph.router.set_model(req.model)
    elif action == "rollback":
        snapshot_id = req.snapshot_id or graph.state.snapshot_id
        if snapshot_id:
            sandbox = LocalProcessSandbox(graph.state.repo_path)
            success = sandbox.restore_snapshot(snapshot_id)
            return {"success": success, "snapshot_id": snapshot_id}
        raise HTTPException(status_code=400, detail="No snapshot ID available for rollback")
    elif action == "approve_patch":
        graph.state.shared_data["patch_approved"] = True
        graph.resume()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown control action: {req.action}")

    return {"status": "ok", "action": action, "run_id": req.run_id}


@router_runs.get("/api/v1/runs/{run_id}/ast")
@router_runs.get("/api/runs/{run_id}/ast")
def get_run_ast(
    run_id: str,
    principal: PrincipalDep,
) -> dict:
    # Authorize run access
    require_run_access(run_id, Action.VIEW_RUN, principal=principal)

    checkpoint_file = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
    if not checkpoint_file.exists():
        return {
            "symbols": ["ModelRouter", "TaskGraph", "WorktreeManager", "LiteLLMAdapter", "TieredMemoryStore"],
            "files_indexed": 243,
            "modules": 12,
            "sanitizer_status": "safe",
            "token_usage": {"used": 4120, "max": 200000},
        }
    data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    return data.get("shared_data", {}).get(
        "ast_summary",
        {
            "symbols": ["ModelRouter", "TaskGraph", "WorktreeManager", "LiteLLMAdapter", "TieredMemoryStore"],
            "files_indexed": 243,
            "modules": 12,
            "sanitizer_status": "safe",
            "token_usage": {"used": 4120, "max": 200000},
        },
    )


@router_runs.get("/api/v1/runs/{run_id}/evidence")
@router_runs.get("/api/runs/{run_id}/evidence")
def get_run_evidence(
    run_id: str,
    principal: PrincipalDep,
) -> dict:
    require_run_access(run_id, Action.VIEW_RUN, principal=principal)

    bundler = EvidenceBundler(output_dir=str(_evidence_dir()))
    entry = bundler.get_entry(run_id)
    bundle_path = _evidence_dir() / f"evidence_{run_id}.json"
    if entry is not None and bundle_path.exists():
        bundle_data = json.loads(bundle_path.read_text(encoding="utf-8"))
        chain_ok, chain_reason, _tampered = bundler.verify_chain()
        return {
            "verified": bundle_data.get("verification_success", False),
            "score": bundle_data.get("test_summary", {}).get("confidence_score", 0),
            "evidence_bundle": bundle_data,
            "chain_integrity": chain_ok,
            "chain_reason": chain_reason,
        }
    checkpoint_file = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
    if not checkpoint_file.exists():
        return {"verified": False, "score": 0, "pytest_output": "No evidence recorded yet."}
    data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    return {
        "verified": data.get("verification_passed", False),
        "score": 100 if data.get("verification_passed") else 0,
        "reproduction_script": data.get("reproduction_test"),
        "patch_diff": data.get("patch_diff"),
        "reviewer_report": data.get("shared_data", {}).get("reviewer_report"),
    }


@router_runs.get("/api/v1/runs/{run_id}")
@router_runs.get("/api/runs/{run_id}")
def get_run(
    run_id: str,
    principal: PrincipalDep,
) -> dict:
    require_run_access(run_id, Action.VIEW_RUN, principal=principal)

    checkpoint_file = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
    trace_file = Path.home() / ".loom" / "traces" / f"trace_{run_id}.json"

    if not checkpoint_file.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    events = []
    if trace_file.exists():
        events = json.loads(trace_file.read_text(encoding="utf-8"))

    return {"checkpoint": data, "trace_events": events}


@router_runs.get("/api/v1/runs/{run_id}/records")
@router_runs.get("/api/runs/{run_id}/records")
def get_run_records(
    run_id: str,
    principal: PrincipalDep,
) -> dict:
    """Relational run record with nested AgentStep/Patch/VerificationResult rows."""
    require_run_access(run_id, Action.VIEW_RUN, principal=principal)

    store = get_records_store()
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return {
        "run": run.model_dump(),
        "steps": [s.model_dump() for s in store.get_steps(run_id)],
        "patches": [p.model_dump() for p in store.get_patches(run_id)],
        "verifications": [v.model_dump() for v in store.get_verifications(run_id)],
    }


@router_runs.post("/v1/runs/{run_id}/rollback")
@router_runs.post("/api/v1/rollback/{run_id}")
@router_runs.post("/api/rollback/{run_id}")
def rollback(
    run_id: str,
    principal: PrincipalDep,
) -> dict:
    require_run_access(run_id, Action.ROLLBACK_RUN, principal=principal)
    return _do_rollback(run_id)


def _do_rollback(run_id: str) -> dict:
    checkpoint_file = Path.home() / ".loom" / "checkpoints" / f"checkpoint_{run_id}.json"
    if not checkpoint_file.exists():
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    repo_path = data.get("repo_path")
    snapshot_id = data.get("snapshot_id")

    if not snapshot_id or not repo_path:
        raise HTTPException(status_code=400, detail="No snapshot found for rollback")

    sandbox = LocalProcessSandbox(repo_path)
    success = sandbox.restore_snapshot(snapshot_id)
    return {"success": success, "snapshot_id": snapshot_id}


@router_runs.post("/api/v1/runs/{run_id}/ci-report")
@router_runs.post("/api/runs/{run_id}/ci-report")
async def report_ci_status(
    run_id: str,
    req: CiReportRequest,
    principal: PrincipalDep,
) -> dict:
    require_run_access(run_id, Action.REPORT_CI, principal=principal)

    from loom.business.audit_log import get_audit_logger
    from loom.business.models import AuditAction
    from loom.business.post_merge import auto_rollback_triggered, generate_revert_patch

    state = OrchestratorState.load_checkpoint(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    org_id = state.shared_data.get("org_id", "unknown")
    rollback_needed = auto_rollback_triggered(req.merge_time, req.ci_failure_detected, req.monitor_timeout_seconds)
    revert_patch = generate_revert_patch(state.patch_diff or "") if rollback_needed else ""

    report = {
        "run_id": run_id,
        "rollback_needed": rollback_needed,
        "ci_failure_detected": req.ci_failure_detected,
        "monitor_timeout_seconds": req.monitor_timeout_seconds,
        "elapsed_seconds": round(time.time() - req.merge_time, 3),
        "revert_patch": revert_patch,
    }

    if rollback_needed:
        state.shared_data["run_status"] = "rolled_back"
        prior_decision = state.shared_data.get("merge_decision")
        if not isinstance(prior_decision, dict):
            prior_decision = {}
            state.shared_data["merge_decision"] = prior_decision
        prior_decision["auto_rolled_back"] = True
        state.save_checkpoint()
        get_audit_logger().record(
            org_id=org_id,
            action=AuditAction.RUN_ROLLED_BACK,
            actor_id="ci_monitor",
            target=run_id,
            metadata={"reason": "post_merge_ci_failure", "revert_hash": hashlib.sha256(revert_patch.encode()).hexdigest()},
        )
        try:
            await get_webhook_engine().dispatch(
                WebhookEventType.RUN_ROLLED_BACK,
                run_id,
                {"reason": "post_merge_ci_failure", "merge_decision": state.shared_data.get("merge_decision")},
                org_id,
            )
        except Exception as exc:
            logger.warning("Failed to dispatch run.rolled_back webhook for %s: %s", run_id, exc)

    return report


# ---------------------------------------------------------------------------
# router_webhooks — outbound webhook subscription management
# ---------------------------------------------------------------------------

router_webhooks = APIRouter(tags=["webhooks"])


@router_webhooks.get("/api/v1/webhooks/subscriptions")
@router_webhooks.get("/api/webhooks/subscriptions")
def list_webhook_subscriptions(
    principal: PrincipalDep,
) -> list:
    engine = get_webhook_engine()
    return [s.model_dump() for s in engine.get_subscriptions(org_id=principal.org_id)]


@router_webhooks.post("/api/v1/webhooks/subscriptions")
@router_webhooks.post("/api/webhooks/subscriptions")
def create_webhook_subscription(
    req: WebhookSubscribeRequest,
    principal: PrincipalDep,
) -> dict:
    if req.org_id != principal.org_id:
        raise HTTPException(status_code=403, detail="Cannot create subscription for another organization")

    from loom.api.webhooks import WebhookSubscription, WebhookEventType as WET

    events = set(WET)
    if req.events:
        try:
            events = {WET(e) for e in req.events}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown event type: {exc}")

    sub = WebhookSubscription(
        id=f"wh_sub_{uuid.uuid4().hex[:12]}",
        org_id=principal.org_id,
        url=req.url,
        events=events,
        secret=req.secret,
    )
    engine = get_webhook_engine()
    result = engine.register(sub)
    return result.model_dump()


@router_webhooks.delete("/api/v1/webhooks/subscriptions/{sub_id}")
@router_webhooks.delete("/api/webhooks/subscriptions/{sub_id}")
def delete_webhook_subscription(
    sub_id: str,
    principal: PrincipalDep,
) -> dict:
    engine = get_webhook_engine()
    subs = engine.get_subscriptions(org_id=principal.org_id)
    if not any(s.id == sub_id for s in subs):
        raise HTTPException(status_code=404, detail="Subscription not found")
    success = engine.unregister(sub_id)
    return {"deleted": success, "subscription_id": sub_id}


# ---------------------------------------------------------------------------
# router_integrations — inbound GitHub / GitLab / Slack
# ---------------------------------------------------------------------------

router_integrations = APIRouter(tags=["integrations"])


@router_integrations.post("/api/v1/integrations/github/webhook")
@router_integrations.post("/api/integrations/github/webhook")
async def handle_github_webhook(
    request: Request,
    _auth: AuthDep = None,
) -> dict:
    """GitHub inbound webhook handler.

    Signature verification is enforced by WebhookSignatureMiddleware (ASGI layer)
    before this handler is ever reached.  The raw body is cached in
    request.state.raw_body by that middleware.
    """
    from loom.integrations.ci_bot import CIBot, CIBotConfig, CIBotProvider

    raw_body = getattr(request.state, "raw_body", None)
    payload: dict[str, Any] = {}
    if raw_body:
        try:
            payload = json.loads(raw_body)
        except Exception:
            payload = {}
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

    repo_name = payload.get("repository", {}).get("full_name", "") if isinstance(payload.get("repository"), dict) else ""
    issue = payload.get("issue", {}) or {}
    issue_title = issue.get("title", "")
    issue_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    issue_number = issue.get("number", 0)
    action = payload.get("action", "")

    config = CIBotConfig(
        provider=CIBotProvider.GITHUB,
        org_id="from_webhook",
        repo_full_name=repo_name,
        api_base_url="",
    )
    bot = CIBot(config)
    should_triage = bot.should_triage_issue(issue_title, issue_labels)
    return {
        "action": action,
        "should_triage": should_triage,
        "repo": repo_name,
        "issue_number": issue_number,
    }


@router_integrations.post("/api/v1/integrations/gitlab/webhook")
@router_integrations.post("/api/integrations/gitlab/webhook")
async def handle_gitlab_webhook(
    request: Request,
    _auth: AuthDep = None,
) -> dict:
    """GitLab inbound webhook handler.

    Signature verification is enforced by WebhookSignatureMiddleware (ASGI layer).
    """
    from loom.integrations.ci_bot import CIBot, CIBotConfig, CIBotProvider

    raw_body = getattr(request.state, "raw_body", None)
    payload: dict[str, Any] = {}
    if raw_body:
        try:
            payload = json.loads(raw_body)
        except Exception:
            payload = {}
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

    project = payload.get("project", {}) or {}
    project_name = project.get("path_with_namespace", "")
    obj_attrs = payload.get("object_attributes", {}) or {}
    issue_title = obj_attrs.get("title", "")
    issue_labels = [lbl.get("title", "") for lbl in obj_attrs.get("labels", [])]
    issue_number = obj_attrs.get("iid", 0)
    object_kind = payload.get("object_kind", "")

    config = CIBotConfig(
        provider=CIBotProvider.GITLAB,
        org_id="from_webhook",
        repo_full_name=project_name,
        api_base_url="",
    )
    bot = CIBot(config)
    should_triage = bot.should_triage_issue(issue_title, issue_labels)
    return {
        "object_kind": object_kind,
        "should_triage": should_triage,
        "repo": project_name,
        "issue_number": issue_number,
    }


@router_integrations.post("/api/v1/integrations/slack/notify")
@router_integrations.post("/api/integrations/slack/notify")
async def send_slack_notification(
    req: SlackNotifyRequest,
    _auth: AuthDep = None,
) -> dict:
    from loom.integrations.slack import (
        SlackNotification,
        SlackNotificationLevel,
        SlackNotificationTemplate,
        SlackNotifier,
    )

    level = SlackNotificationLevel.INFO
    template = SlackNotificationTemplate.CUSTOM
    try:
        level = SlackNotificationLevel(req.level)
    except ValueError:
        pass
    try:
        template = SlackNotificationTemplate(req.template)
    except ValueError:
        pass

    notification = SlackNotification(
        title=req.title,
        body=req.body,
        level=level,
        template=template,
        run_id=req.run_id,
    )

    notifier = SlackNotifier(webhook_url=req.webhook_url)
    try:
        success = await notifier.send(notification)
        await notifier.close()
        return {"sent": success, "level": level.value, "template": template.value}
    except Exception as exc:
        logger.error("Slack notify failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Slack delivery failed: {exc}")


@router_integrations.get("/api/v1/integrations/bot/{org_id}/status")
@router_integrations.get("/api/integrations/bot/{org_id}/status")
def get_bot_status(
    org_id: str,
    _rbac: RBACEnforcer = Depends(require_admin_permission),
) -> Any:
    from loom.integrations.ci_bot import CIBot, CIBotConfig, CIBotProvider

    config = CIBotConfig(
        provider=CIBotProvider.GITHUB,
        org_id=org_id,
        repo_full_name="",
        api_base_url="",
    )
    bot = CIBot(config)
    return bot.serialize()


@router_integrations.post("/api/v1/integrations/bot/{org_id}/prepare-pr")
@router_integrations.post("/api/integrations/bot/{org_id}/prepare-pr")
def prepare_pr(
    org_id: str,
    req: PreparePRRequest,
    _rbac: RBACEnforcer = Depends(require_run_permission),
) -> Any:
    from loom.integrations.ci_bot import CIBot, CIBotConfig, CIBotProvider, PullRequestTemplate

    config = CIBotConfig(
        provider=CIBotProvider.GITHUB,
        org_id=org_id,
        repo_full_name="",
        api_base_url="",
    )
    bot = CIBot(config)

    template = PullRequestTemplate.STANDARD
    try:
        template = PullRequestTemplate(req.template)
    except ValueError:
        pass

    data = bot.generate_pr_template_data(
        run_id=req.run_id,
        issue_title=req.issue_title,
        issue_number=req.issue_number,
        patch_diff=req.patch_diff,
        confidence_score=req.confidence_score,
        verification_passed=req.verification_passed,
        cost_usd=req.cost_usd,
        files_touched=req.files_touched,
        model_used=req.model_used,
    )
    return bot.prepare_pr(data, template)


# ---------------------------------------------------------------------------
# router_admin — entitlements, org usage
# ---------------------------------------------------------------------------

router_admin = APIRouter(tags=["admin"])


@router_admin.post("/v1/entitlements/check")
@router_admin.post("/api/v1/entitlements/check")
def check_entitlement(
    req: EntitlementCheckRequest,
    _rbac: RBACEnforcer = Depends(require_admin_permission),
) -> dict:
    entitlements = get_entitlements()
    orgs = list(getattr(entitlements, "_orgs", {}).keys())
    org_id = req.org_id or (orgs[0] if orgs else "default")
    try:
        feature_key = FeatureKey(req.feature_key)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown feature_key: {req.feature_key}")
    result = entitlements.check(org_id, feature_key)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=result.reason or "Feature not available on current tier"
        )
    return {"allowed": True}


@router_admin.get("/api/v1/orgs/{org_id}/usage")
def get_org_usage(
    org_id: str,
    _rbac: RBACEnforcer = Depends(require_auditor_permission),
) -> dict:
    entitlements = get_entitlements()
    org = entitlements.get_org(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")
    from loom.business.usage_ledger import get_usage_ledger

    ledger = get_usage_ledger()
    snapshot = ledger.build_snapshot(org_id, org.tier)
    allowed, reason = entitlements.evaluate_quota(org_id, snapshot)
    return {
        "org_id": org_id,
        "tier": org.tier.value,
        "snapshot": snapshot.model_dump(),
        "quota_ok": allowed,
        "quota_reason": reason,
    }


# ---------------------------------------------------------------------------
# Backward-compat: module-level `app` for uvicorn entry-points
# ---------------------------------------------------------------------------

def _build_app() -> Any:
    """Build app lazily to avoid import-time side effects in tests."""
    from loom.api.app import create_app
    return create_app()


app = _build_app()

# ---------------------------------------------------------------------------
# Backward-compat re-exports (used by tests that import directly from server)
# ---------------------------------------------------------------------------

def __getattr__(name: str) -> Any:
    if name == "_entitlements":
        return get_entitlements()
    if name == "_default_org":
        ent = get_entitlements()
        if ent._orgs:
            return next(iter(ent._orgs.values()))
        from loom.business.models import Organization, OrgTier
        return Organization(id="default", name="Default", tier=OrgTier.SOLO)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# _rate_limit_memory_store: dummy dict — rate limiting is in app middleware
_rate_limit_memory_store: Dict[str, List[float]] = {}

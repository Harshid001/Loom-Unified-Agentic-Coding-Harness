"""Shared run executor used by durable production workers."""

from __future__ import annotations

import time
from typing import Any, Dict

from loom.adapters.router import ModelRouter
from loom.api.webhooks import get_webhook_engine
from loom.business.models import RunRecord
from loom.db.records_store import get_run_record_store
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer
from loom.verification.bundle import EvidenceBundler


async def execute_run_job(job: Any) -> OrchestratorState:
    """Reconstruct and execute a queued run without importing FastAPI request state."""
    state = OrchestratorState(run_id=job.run_id, repo_path=job.repo_path, issue_description=job.issue)
    state.shared_data["org_id"] = job.org_id
    state.shared_data["sandbox_tier"] = job.sandbox_tier
    state.shared_data["auto_merge_threshold"] = job.auto_merge_threshold

    router = ModelRouter(default_model=job.model, mock_mode=job.mock)
    tracer = TelemetryTracer(run_id=job.run_id)
    cost_tracker = CostTracker(run_id=job.run_id)
    records_store = get_run_record_store()
    evidence = EvidenceBundler()

    def on_step_start(step_name: str, model_name: str) -> None:
        records_store.record_agent_step(job.run_id, step_name, "running", None)

    def on_step_complete(step_name: str, output: Any) -> None:
        records_store.record_agent_step(job.run_id, step_name, "completed", output if isinstance(output, dict) else None)

    def on_step_fail(step_name: str, error: str) -> None:
        records_store.record_agent_step(job.run_id, step_name, "failed", {"error": error})

    graph = TaskGraph(
        state,
        router,
        tracer,
        cost_tracker,
        on_step_start=on_step_start,
        on_step_complete=on_step_complete,
        on_step_fail=on_step_fail,
        webhook_engine=get_webhook_engine(),
        evidence_bundler=evidence,
        records_store=records_store,
    )
    records_store.record_run(
        RunRecord(
            run_id=job.run_id,
            org_id=job.org_id,
            repo_id=job.repo_path,
            issue_text=job.issue,
            status="queued",
            sandbox_tier=job.sandbox_tier,
        )
    )
    started = time.time()
    try:
        final_state = await graph.run()
        state.shared_data["worker_duration_seconds"] = round(time.time() - started, 3)
        return final_state
    except Exception as exc:
        state.shared_data["worker_duration_seconds"] = round(time.time() - started, 3)
        state.shared_data["worker_error"] = str(exc)
        raise

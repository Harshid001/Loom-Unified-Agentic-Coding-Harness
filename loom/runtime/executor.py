"""Shared run executor used by durable production workers."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from loom.adapters.router import ModelRouter
from loom.api.webhooks import get_webhook_engine
from loom.business.models import RunRecord
from loom.db.records_store import get_run_record_store
from loom.infra.distributed import RedisCoordinator
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.runtime.budget import RunBudget, cost_from_summary, tokens_from_summary
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer
from loom.verification.bundle import EvidenceBundler


def _resume_node(state: OrchestratorState, sequence: list[tuple[str, Any]]) -> Optional[str]:
    """Return the first node that is not durably completed in a checkpoint."""
    for name, _ in sequence:
        node = state.nodes.get(name)
        if node is None or node.status != "completed":
            return name
    return None


async def execute_run_job(job: Any) -> OrchestratorState:
    """Reconstruct and execute a queued run, resuming from the latest checkpoint."""
    checkpoint = OrchestratorState.load_checkpoint(job.run_id)
    if checkpoint is not None:
        state = checkpoint
        state.repo_path = job.repo_path
        state.issue_description = job.issue
    else:
        state = OrchestratorState(run_id=job.run_id, repo_path=job.repo_path, issue_description=job.issue)

    state.shared_data["org_id"] = job.org_id
    state.shared_data["sandbox_tier"] = job.sandbox_tier
    state.shared_data["auto_merge_threshold"] = job.auto_merge_threshold

    try:
        from loom.api import server as server_module

        org = server_module._entitlements.get_org(job.org_id) or server_module._default_org
        state.shared_data["_org"] = org
    except Exception:
        state.shared_data["_org"] = None

    router = ModelRouter(default_model=job.model, mock_mode=job.mock)
    tracer = TelemetryTracer(run_id=job.run_id)
    cost_tracker = CostTracker(run_id=job.run_id)
    records_store = get_run_record_store()
    evidence = EvidenceBundler()
    coordinator = RedisCoordinator()
    budget = RunBudget.from_env()

    async def publish(event_type: str, step_name: str, data: dict[str, Any]) -> None:
        if coordinator.enabled:
            await coordinator.record_event(
                job.run_id,
                {
                    "type": event_type,
                    "timestamp": time.time(),
                    "run_id": job.run_id,
                    "step_name": step_name,
                    "data": data,
                },
            )

    def on_step_start(step_name: str, model_name: str) -> None:
        if coordinator.enabled:
            asyncio.create_task(publish("step_progress", step_name, {"status": "running", "model": model_name}))

    def on_step_complete(step_name: str, output: Any) -> None:
        if coordinator.enabled:
            metrics = output.get("_usage", {}) if isinstance(output, dict) else {}
            asyncio.create_task(publish("step_progress", step_name, {"status": "completed", "metrics": metrics}))

    def on_step_fail(step_name: str, error: str) -> None:
        if coordinator.enabled:
            asyncio.create_task(publish("step_progress", step_name, {"status": "failed", "error": error}))

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

    resume_from = _resume_node(state, graph.NODE_SEQUENCE) if checkpoint is not None else None
    started = time.time()
    stop_watchdog = asyncio.Event()

    async def control_loop() -> None:
        async for message in coordinator.control_stream(job.run_id):
            action = str(message.get("action", "")).lower()
            payload = message.get("payload") or {}
            if action == "pause":
                graph.pause()
            elif action == "resume":
                graph.resume()
            elif action == "step":
                graph.step_over()
            elif action == "cancel":
                graph.cancel()
            elif action == "model_switch" and payload.get("model"):
                graph.router.set_model(str(payload["model"]))

    control_task = asyncio.create_task(control_loop()) if coordinator.enabled else None

    async def enforce_budget() -> None:
        """Poll hard runtime limits and cancel between agent boundaries when exceeded."""
        while not stop_watchdog.is_set():
            await asyncio.sleep(1.0)
            elapsed = time.time() - started
            summary = cost_tracker.get_summary()
            cost = cost_from_summary(summary)
            tokens = tokens_from_summary(summary)

            reason: Optional[str] = None
            if budget.max_duration_seconds is not None and elapsed >= budget.max_duration_seconds:
                reason = f"maximum run duration of {budget.max_duration_seconds:.0f}s exceeded"
            elif budget.max_cost_usd is not None and cost >= budget.max_cost_usd:
                reason = f"maximum run cost of ${budget.max_cost_usd:.4f} exceeded"
            elif budget.max_tokens is not None and tokens >= budget.max_tokens:
                reason = f"maximum run token budget of {budget.max_tokens} exceeded"

            if reason:
                state.shared_data["budget_exceeded"] = True
                state.shared_data["budget_exceeded_reason"] = reason
                graph.cancel()
                await publish("budget_exceeded", "pipeline", {"reason": reason})
                return

    watchdog = asyncio.create_task(enforce_budget()) if any(
        value is not None
        for value in (
            budget.max_duration_seconds,
            budget.max_cost_usd,
            budget.max_tokens,
        )
    ) else None

    try:
        if coordinator.enabled:
            await coordinator.update_run_status(job.run_id, "running")
            await publish("status_change", "pipeline", {"status": "running"})
        final_state = await graph.run(resume_from=resume_from)
        final_state.shared_data["worker_duration_seconds"] = round(time.time() - started, 3)
        if coordinator.enabled:
            status = str(graph.run_status.value if hasattr(graph.run_status, "value") else graph.run_status)
            if final_state.shared_data.get("budget_exceeded"):
                status = "failed"
            await coordinator.update_run_status(job.run_id, status)
            await publish("status_change", "pipeline", {"status": status})
        return final_state
    except Exception as exc:
        state.shared_data["worker_duration_seconds"] = round(time.time() - started, 3)
        state.shared_data["worker_error"] = str(exc)
        state.save_checkpoint()
        if coordinator.enabled:
            await coordinator.update_run_status(job.run_id, "failed")
            await publish("status_change", "pipeline", {"status": "failed", "error": str(exc)})
        raise
    finally:
        stop_watchdog.set()
        if watchdog is not None:
            watchdog.cancel()
            try:
                await watchdog
            except asyncio.CancelledError:
                pass
        if control_task is not None:
            control_task.cancel()
            try:
                await control_task
            except asyncio.CancelledError:
                pass
        await coordinator.close()


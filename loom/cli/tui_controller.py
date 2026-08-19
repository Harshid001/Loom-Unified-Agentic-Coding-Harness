"""Controller that bridges the Textual TUI and the real Loom TaskGraph."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from loom.adapters.router import ModelRouter
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer


@dataclass
class ControllerEvent:
    kind: str
    node: str = "system"
    level: str = "info"
    message: str = ""
    data: Optional[dict[str, Any]] = None


class TUIRunController:
    """Owns the live TaskGraph and translates backend callbacks into UI events."""

    def __init__(self, emit: Callable[[ControllerEvent], None]):
        self.emit = emit
        self.state: Optional[OrchestratorState] = None
        self.graph: Optional[TaskGraph] = None
        self.router: Optional[ModelRouter] = None
        self.tracer: Optional[TelemetryTracer] = None
        self.cost_tracker: Optional[CostTracker] = None
        self.task: Optional[asyncio.Task[Any]] = None
        self.started_at: Optional[float] = None

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def create(self, issue: str, repo_path: str, model: str) -> OrchestratorState:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        self.state = OrchestratorState(run_id=run_id, repo_path=repo_path, issue_description=issue)
        self.router = ModelRouter(default_model=model, mock_mode=False)
        self.tracer = TelemetryTracer(run_id)
        self.cost_tracker = CostTracker(run_id)
        self.graph = TaskGraph(
            state=self.state,
            router=self.router,
            tracer=self.tracer,
            cost_tracker=self.cost_tracker,
            on_step_start=self._on_step_start,
            on_step_log=self._on_step_log,
            on_step_complete=self._on_step_complete,
            on_step_fail=self._on_step_fail,
        )
        return self.state

    def start(self, issue: str, repo_path: str, model: str) -> None:
        if self.running:
            return
        if not issue.strip():
            self.emit(ControllerEvent("error", message="Issue description is required.", level="warn"))
            return
        state = self.create(issue.strip(), repo_path, model.strip() or "claude-3-7-sonnet-20250219")
        assert self.graph is not None
        self.started_at = time.time()
        self.emit(ControllerEvent("run_started", message=f"Started run {state.run_id}"))
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        assert self.graph is not None
        try:
            await self.graph.run()
            self.emit(ControllerEvent("run_completed", message="TaskGraph execution finished."))
        except asyncio.CancelledError:
            self.emit(ControllerEvent("run_cancelled", level="warn", message="Run cancelled."))
            raise
        except Exception as exc:
            self.emit(ControllerEvent("run_failed", level="error", message=str(exc)))
        finally:
            if self.tracer:
                self.tracer.close()

    def pause(self) -> None:
        if self.graph:
            self.graph.pause()
            self.emit(ControllerEvent("state", message="Execution paused.", level="warn"))

    def resume(self) -> None:
        if self.graph:
            self.graph.resume()
            self.emit(ControllerEvent("state", message="Execution resumed."))

    def step(self) -> None:
        if self.graph:
            self.graph.step_over()
            self.emit(ControllerEvent("state", message="Step-over requested."))

    def cancel(self) -> None:
        if self.graph:
            self.graph.cancel()
            self.emit(ControllerEvent("state", message="Cancellation requested.", level="warn"))

    def rollback(self) -> None:
        if self.graph:
            self.graph.rollback()
            self.emit(ControllerEvent("state", message="Rollback state requested.", level="warn"))

    def approve_patch(self) -> None:
        if self.state is None:
            return
        self.state.shared_data["human_review_decision"] = "approved"
        self.emit(ControllerEvent("approval", node="reviewer", message="Patch approved by operator."))

    def reject_patch(self) -> None:
        if self.state is None:
            return
        self.state.shared_data["human_review_decision"] = "rejected"
        self.rollback()
        self.emit(ControllerEvent("approval", node="reviewer", level="warn", message="Patch rejected; rollback requested."))

    def metrics(self) -> dict[str, Any]:
        if not self.cost_tracker:
            return {"tokens": 0, "cost": 0.0, "elapsed": 0.0}
        summary = self.cost_tracker.get_summary()
        elapsed = (time.time() - self.started_at) if self.started_at else 0.0
        return {
            "tokens": summary.get("total_tokens", 0),
            "cost": summary.get("total_cost_usd", 0.0),
            "elapsed": elapsed,
        }

    def _on_step_start(self, node: str, model: str) -> None:
        self.emit(ControllerEvent("node_started", node=node, data={"model": model}))

    def _on_step_log(self, node: str, level: str, message: str) -> None:
        self.emit(ControllerEvent("log", node=node, level=level, message=message))

    def _on_step_complete(self, node: str, output: Any) -> None:
        self.emit(ControllerEvent("node_completed", node=node, data=output if isinstance(output, dict) else {}))

    def _on_step_fail(self, node: str, message: str) -> bool:
        self.emit(ControllerEvent("node_failed", node=node, level="error", message=message))
        return False

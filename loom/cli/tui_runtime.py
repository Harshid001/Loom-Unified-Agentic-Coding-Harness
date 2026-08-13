"""Runtime adapter for the terminal UI."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from loom.adapters.router import ModelRouter
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer


@dataclass
class RuntimeEvent:
    kind: str
    node: str = "system"
    level: str = "info"
    message: str = ""
    data: dict[str, Any] | None = None

class TUIRuntime:
    def __init__(self, emit: Callable[[RuntimeEvent], None]):
        self.emit = emit
        self.state: OrchestratorState | None = None
        self.graph: TaskGraph | None = None
        self.tracer: TelemetryTracer | None = None
        self.costs: CostTracker | None = None
        self.task: asyncio.Task[Any] | None = None
        self.started_at: float | None = None

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def start(self, issue: str, repo: str, model: str) -> None:
        if self.running or not issue.strip():
            return
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        self.state = OrchestratorState(run_id=run_id, repo_path=repo, issue_description=issue.strip())
        router = ModelRouter(default_model=model, mock_mode=False)
        self.tracer = TelemetryTracer(run_id)
        self.costs = CostTracker(run_id)
        self.graph = TaskGraph(
            state=self.state,
            router=router,
            tracer=self.tracer,
            cost_tracker=self.costs,
            on_step_start=self._started,
            on_step_log=self._log,
            on_step_complete=self._completed,
            on_step_fail=self._failed,
        )
        self.started_at = time.time()
        self.emit(RuntimeEvent("started", message=run_id))
        self.task = asyncio.create_task(self._execute())

    async def _execute(self) -> None:
        try:
            state = await self.graph.run()  # type: ignore[union-attr]
            status = str(state.shared_data.get("run_status", "unknown")).split(".")[-1].lower()
            self.emit(RuntimeEvent("finished", level="info" if status == "merged" else "warn", message=status, data={"status": status}))
        except asyncio.CancelledError:
            self.emit(RuntimeEvent("stopped", level="warn", message="Execution stopped."))
        except Exception as exc:
            self.emit(RuntimeEvent("failed", level="error", message=str(exc)))
        finally:
            if self.tracer:
                self.tracer.close()

    def pause(self) -> None:
        if self.graph:
            self.graph.pause()
            self.emit(RuntimeEvent("state", level="warn", message="Paused"))

    def resume(self) -> None:
        if self.graph:
            self.graph.resume()
            self.emit(RuntimeEvent("state", message="Resumed"))

    def step(self) -> None:
        if self.graph:
            self.graph.step_over()
            self.emit(RuntimeEvent("state", message="Step requested"))

    def stop(self) -> None:
        if self.graph:
            self.graph.cancel()
            self.emit(RuntimeEvent("state", level="warn", message="Stop requested"))

    def rollback(self) -> None:
        if self.graph:
            self.graph.cancel()
            self.graph.rollback()
            self.emit(RuntimeEvent("state", level="warn", message="Rollback requested"))

    def metrics(self) -> dict[str, float | int]:
        summary = self.costs.get_summary() if self.costs else {}
        return {
            "tokens": int(summary.get("total_tokens", 0)),
            "cost": float(summary.get("total_cost_usd", 0.0)),
            "elapsed": time.time() - self.started_at if self.started_at else 0.0,
        }

    def _started(self, node: str, model: str) -> None:
        self.emit(RuntimeEvent("node_started", node=node, data={"model": model}))

    def _log(self, node: str, level: str, message: str) -> None:
        self.emit(RuntimeEvent("log", node=node, level=level, message=message))

    def _completed(self, node: str, output: Any) -> None:
        self.emit(RuntimeEvent("node_completed", node=node, data=output if isinstance(output, dict) else {}))

    def _failed(self, node: str, message: str) -> bool:
        self.emit(RuntimeEvent("node_failed", node=node, level="error", message=message))
        return False

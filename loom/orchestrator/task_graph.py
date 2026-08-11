import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Type

from loom.adapters.router import ModelRouter
from loom.orchestrator.agents import OnboardingAgent, PatcherAgent, ReproductionAgent, ReviewerAgent, VerifierAgent
from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import NodeStatus, OrchestratorState
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer

logger = logging.getLogger("loom.orchestrator")


class TaskGraph:
    """DAG Task Graph Engine managing agent execution flow, state persistence, and recovery loops."""

    NODE_SEQUENCE: List[Tuple[str, Type[BaseAgent]]] = [
        ("onboarding", OnboardingAgent),
        ("reproduction", ReproductionAgent),
        ("patcher", PatcherAgent),
        ("verifier", VerifierAgent),
        ("reviewer", ReviewerAgent),
    ]

    def __init__(
        self,
        state: OrchestratorState,
        router: ModelRouter,
        tracer: TelemetryTracer,
        cost_tracker: CostTracker,
        advanced_model_map: Optional[Dict[str, str]] = None,
        on_step_start: Any = None,
        on_step_log: Any = None,
        on_step_complete: Any = None,
        on_step_fail: Any = None,
    ):
        self.state = state
        self.router = router
        self.tracer = tracer
        self.cost_tracker = cost_tracker
        self.advanced_model_map = advanced_model_map or {}
        self.state.shared_data["mock_mode"] = self.router.mock_mode
        self.on_step_start_cb = on_step_start
        self.on_step_log_cb = on_step_log
        self.on_step_complete_cb = on_step_complete
        self.on_step_fail_cb = on_step_fail

        # Interactive controls
        self.is_paused: bool = False
        self.is_cancelled: bool = False
        self.step_mode: bool = False

    def pause(self) -> None:
        self.is_paused = True
        logger.info(f"TaskGraph for run {self.state.run_id} paused")

    def resume(self) -> None:
        self.is_paused = False
        self.step_mode = False
        logger.info(f"TaskGraph for run {self.state.run_id} resumed")

    def step_over(self) -> None:
        self.is_paused = False
        self.step_mode = True
        logger.info(f"TaskGraph for run {self.state.run_id} step-over triggered")

    def cancel(self) -> None:
        self.is_cancelled = True
        self.is_paused = False
        logger.info(f"TaskGraph for run {self.state.run_id} cancelled")

    def emit_log(self, step_name: str, level: str, message: str) -> None:
        if self.on_step_log_cb:
            try:
                self.on_step_log_cb(step_name, level, message)
            except Exception as err:
                logger.warning(f"Error in step log callback: {err}")

    def get_sequence(
        self,
        resume_from: Optional[str] = None,
        parallel_groups: Optional[List[List[Tuple[str, Type[BaseAgent]]]]] = None,
    ) -> List[Tuple[str, Type[BaseAgent]]]:
        if parallel_groups:
            return [(name, cls) for group in parallel_groups for name, cls in group]

        if resume_from:
            result = []
            found = False
            for name, cls in self.NODE_SEQUENCE:
                if name == resume_from:
                    found = True
                if found:
                    result.append((name, cls))
            return result

        return list(self.NODE_SEQUENCE)

    def resolve_model(self, node_name: str) -> str:
        if node_name in self.advanced_model_map:
            return self.advanced_model_map[node_name]
        return self.router.resolve_model(node_name)

    async def run(
        self,
        resume_from: Optional[str] = None,
        on_node_start: Any = None,
        on_node_complete: Any = None,
        on_node_error: Any = None,
    ) -> OrchestratorState:
        node_sequence = self.get_sequence(resume_from=resume_from)

        start_cb = on_node_start or self.on_step_start_cb
        complete_cb = on_node_complete or self.on_step_complete_cb
        error_cb = on_node_error or self.on_step_fail_cb

        for node_name, agent_cls in node_sequence:
            if self.is_cancelled:
                logger.info(f"Pipeline cancelled before executing {node_name}")
                break

            # Handle pause state
            import asyncio
            while self.is_paused and not self.is_cancelled:
                await asyncio.sleep(0.2)

            if self.is_cancelled:
                logger.info(f"Pipeline cancelled during pause before executing {node_name}")
                break

            model_name = self.resolve_model(node_name)
            adapter = self.router.get_adapter(node_name)
            agent = agent_cls(name=node_name, adapter=adapter, model_name=model_name)

            status = NodeStatus(node_name=node_name, status="running", started_at=time.time())
            self.state.nodes[node_name] = status
            self.state.current_node = node_name
            self.state.save_checkpoint()

            self.tracer.log_event("task_start", node_name, {"model": model_name})
            self.emit_log(node_name, "info", f"Executing agent {node_name} using model {model_name}...")

            if start_cb:
                try:
                    start_cb(node_name, model_name)
                except Exception as err:
                    logger.warning(f"Error in start_cb: {err}")

            try:
                out = await agent.execute(self.state)
                status.status = "completed"
                status.completed_at = time.time()
                status.output = out
                self.tracer.log_event("task_completed", node_name, out)

                usage_info = out.get("_usage") if isinstance(out, dict) else None
                if usage_info:
                    p_tokens = usage_info.get("prompt_tokens", 150)
                    c_tokens = usage_info.get("completion_tokens", 50)
                    cost = usage_info.get("estimated_cost_usd", 0.0005)
                    self.cost_tracker.add_usage(node_name, p_tokens, c_tokens, cost)
                else:
                    self.cost_tracker.add_usage(node_name, 150, 50, 0.0005)

                self.emit_log(node_name, "success", f"Agent {node_name} completed successfully")

                if complete_cb:
                    try:
                        complete_cb(node_name, out)
                    except Exception as err:
                        logger.warning(f"Error in complete_cb: {err}")

            except Exception as e:
                logger.error(f"Task node {node_name} failed: {e}")
                status.status = "failed"
                status.completed_at = time.time()
                status.error = str(e)
                self.tracer.log_event("task_failed", node_name, {"error": str(e)})
                self.emit_log(node_name, "error", f"Agent {node_name} failed: {e}")

                if error_cb:
                    try:
                        should_continue = error_cb(node_name, str(e))
                        if not should_continue:
                            break
                    except Exception:
                        break
                else:
                    break

            self.state.save_checkpoint()

            if self.step_mode:
                self.is_paused = True
                self.step_mode = False

        self.state.shared_data["cost_report"] = self.cost_tracker.get_summary()
        self.state.save_checkpoint()
        return self.state

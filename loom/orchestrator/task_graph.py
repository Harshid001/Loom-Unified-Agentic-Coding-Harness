import logging
import time

from loom.adapters.router import ModelRouter
from loom.orchestrator.agents import OnboardingAgent, PatcherAgent, ReproductionAgent, ReviewerAgent, VerifierAgent
from loom.orchestrator.state import NodeStatus, OrchestratorState
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer

logger = logging.getLogger("loom.orchestrator")

class TaskGraph:
    """DAG Task Graph Engine managing agent execution flow, state persistence, and recovery loops."""

    def __init__(self, state: OrchestratorState, router: ModelRouter, tracer: TelemetryTracer, cost_tracker: CostTracker):
        self.state = state
        self.router = router
        self.tracer = tracer
        self.cost_tracker = cost_tracker
        self.state.shared_data["mock_mode"] = self.router.mock_mode

    async def run(self) -> OrchestratorState:
        node_sequence = [
            ("onboarding", OnboardingAgent),
            ("reproduction", ReproductionAgent),
            ("patcher", PatcherAgent),
            ("verifier", VerifierAgent),
            ("reviewer", ReviewerAgent)
        ]

        for node_name, agent_cls in node_sequence:
            model_name = self.router.resolve_model(node_name)
            adapter = self.router.get_adapter(node_name)
            agent = agent_cls(name=node_name, adapter=adapter, model_name=model_name)

            status = NodeStatus(node_name=node_name, status="running", started_at=time.time())
            self.state.nodes[node_name] = status
            self.state.current_node = node_name
            self.state.save_checkpoint()

            self.tracer.log_event("task_start", node_name, {"model": model_name})

            try:
                out = await agent.execute(self.state)
                status.status = "completed"
                status.completed_at = time.time()
                status.output = out
                self.tracer.log_event("task_completed", node_name, out)

                # PRD-008: Pass real usage data from agent response to cost tracker
                usage_info = out.get("_usage") if isinstance(out, dict) else None
                if usage_info:
                    p_tokens = usage_info.get("prompt_tokens", 150)
                    c_tokens = usage_info.get("completion_tokens", 50)
                    cost = usage_info.get("estimated_cost_usd", 0.0005)
                    self.cost_tracker.add_usage(node_name, p_tokens, c_tokens, cost)
                else:
                    self.cost_tracker.add_usage(node_name, 150, 50, 0.0005)
            except Exception as e:
                logger.error(f"Task node {node_name} failed: {e}")
                status.status = "failed"
                status.completed_at = time.time()
                status.error = str(e)
                self.tracer.log_event("task_failed", node_name, {"error": str(e)})
                break

            self.state.save_checkpoint()

        self.state.shared_data["cost_report"] = self.cost_tracker.get_summary()
        self.state.save_checkpoint()
        return self.state

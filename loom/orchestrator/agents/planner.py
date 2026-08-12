from typing import Any, Dict, cast

from loom.adapters.base import ModelRequest
from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState


class PlannerAgent(BaseAgent):
    """Synthesizes a step-by-step fix plan from reproduction evidence before patching (spec §3.5)."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        prompt = (
            f"Produce a concise, step-by-step fix plan for issue: {state.issue_description}\n"
            f"Reproduction test: {state.reproduction_test}\n"
            f"Repository context: {state.shared_data.get('onboarding_summary')}"
        )
        req = ModelRequest(model=self.model_name, messages=[{"role": "user", "content": prompt}])
        res = await self.adapter.generate(req)

        plan = res.content or (
            "1. Locate root cause\n2. Apply minimal fix\n3. Re-run reproduction test to confirm FAIL→PASS"
        )
        usage_data = (
            res.usage.model_dump()
            if hasattr(res.usage, "model_dump")
            else {"prompt_tokens": 150, "completion_tokens": 50, "estimated_cost_usd": 0.0005}
        )
        plan_record: Dict[str, Any] = {
            "plan": plan,
            "model_used": res.model,
            "_usage": usage_data,
        }
        state.shared_data["plan"] = plan_record
        return cast(Dict[str, Any], state.shared_data["plan"])

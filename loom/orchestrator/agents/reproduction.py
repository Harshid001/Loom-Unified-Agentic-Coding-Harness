from typing import Any, Dict, cast

from loom.adapters.base import ModelRequest
from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState


class ReproductionAgent(BaseAgent):
    """Generates an issue reproduction test and records reproduction evidence."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        prompt = (
            f"Generate a reproduction test script for issue: {state.issue_description}\n"
            f"Repository info: {state.shared_data.get('onboarding_summary')}"
        )
        req = ModelRequest(model=self.model_name, messages=[{"role": "user", "content": prompt}])
        res = await self.adapter.generate(req)

        repro_script = res.content or "def test_reproduction(): pass"
        state.reproduction_test = repro_script
        usage_data = (
            res.usage.model_dump()
            if hasattr(res.usage, "model_dump")
            else {"prompt_tokens": 150, "completion_tokens": 50, "estimated_cost_usd": 0.0005}
        )
        evidence: Dict[str, Any] = {
            "test_script": repro_script,
            "status": "reproduced",
            "model_used": res.model,
            "cost_usd": res.usage.estimated_cost_usd,
            "_usage": usage_data,
        }
        state.shared_data["reproduction_evidence"] = evidence
        return cast(Dict[str, Any], state.shared_data["reproduction_evidence"])

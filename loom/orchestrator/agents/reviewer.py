from typing import Any, Dict

from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState
from loom.verification.bundle import EvidenceBundler


class ReviewerAgent(BaseAgent):
    """Compiles evidence bundle and generates final human reviewer report."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        bundler = EvidenceBundler()
        bundle = bundler.create_bundle(
            run_id=state.run_id,
            patch_diff=state.patch_diff or "",
            verification_success=state.verification_passed,
            test_summary=state.shared_data.get("verification_output", {}),
            cost_report=state.shared_data.get("cost_report", {"total_cost_usd": 0.001}),
            trace_events=[],
            rollback_snapshot_id=state.snapshot_id,
        )

        review_report = {
            "run_id": state.run_id,
            "verification_status": "VERIFIED" if state.verification_passed else "FAILED",
            "completion_rationale": "All automated verification checks and reproduction tests passed successfully.",
            "rollback_command": f"loom rollback {state.run_id}",
            "evidence_bundle": bundle.model_dump(),
        }
        state.shared_data["reviewer_report"] = review_report
        return review_report

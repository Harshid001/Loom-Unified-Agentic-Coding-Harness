
import pytest

from loom.adapters.router import ModelRouter
from loom.cli.main import _execute_task_graph
from loom.orchestrator.agents import (
    OnboardingAgent,
    PatcherAgent,
    PlannerAgent,
    ReproductionAgent,
    ReviewerAgent,
    VerifierAgent,
)
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer


@pytest.fixture(autouse=True)
def mock_all_agents(monkeypatch):
    async def fake_onboard(self, state):
        return {"repo_map": {}}

    async def fake_repro(self, state):
        return {"status": "reproduced"}

    async def fake_plan(self, state):
        return {"plan": {}}

    async def fake_patch(self, state):
        return {"patch_diff": "diff"}

    async def fake_verify(self, state):
        return {"overall_success": True}

    async def fake_review(self, state):
        return {"report": "approved"}

    monkeypatch.setattr(OnboardingAgent, "execute", fake_onboard)
    monkeypatch.setattr(ReproductionAgent, "execute", fake_repro)
    monkeypatch.setattr(PlannerAgent, "execute", fake_plan)
    monkeypatch.setattr(PatcherAgent, "execute", fake_patch)
    monkeypatch.setattr(VerifierAgent, "execute", fake_verify)
    monkeypatch.setattr(ReviewerAgent, "execute", fake_review)


@pytest.mark.asyncio
async def test_cli_and_api_sequence_parity(tmp_path):
    # Verify TaskGraph canonical sequence
    canonical_names = [name for name, _ in TaskGraph.NODE_SEQUENCE]
    assert canonical_names == ["onboarding", "reproduction", "planner", "patcher", "verifier", "reviewer"]

    state = OrchestratorState(run_id="run_cli_test", repo_path=str(tmp_path), issue_description="Test issue")
    router = ModelRouter(mock_mode=True)
    tracer = TelemetryTracer(run_id="run_cli_test", log_dir=str(tmp_path / "traces"))
    cost_tracker = CostTracker(run_id="run_cli_test")

    final_state = await _execute_task_graph(
        state=state,
        router=router,
        advanced_router=None,
        tracer=tracer,
        cost_tracker=cost_tracker,
        fast=False,
    )

    # All 6 nodes must be executed in order
    assert "onboarding" in final_state.nodes
    assert "reproduction" in final_state.nodes
    assert "planner" in final_state.nodes
    assert "patcher" in final_state.nodes
    assert "verifier" in final_state.nodes
    assert "reviewer" in final_state.nodes


@pytest.mark.asyncio
async def test_cli_fast_mode_skips_planner(tmp_path):
    state = OrchestratorState(run_id="run_cli_fast", repo_path=str(tmp_path), issue_description="Test issue")
    router = ModelRouter(mock_mode=True)
    tracer = TelemetryTracer(run_id="run_cli_fast", log_dir=str(tmp_path / "traces"))
    cost_tracker = CostTracker(run_id="run_cli_fast")

    final_state = await _execute_task_graph(
        state=state,
        router=router,
        advanced_router=None,
        tracer=tracer,
        cost_tracker=cost_tracker,
        fast=True,
    )

    assert "onboarding" in final_state.nodes
    assert "reproduction" in final_state.nodes
    assert "planner" not in final_state.nodes
    assert "patcher" in final_state.nodes
    assert "verifier" in final_state.nodes
    assert "reviewer" in final_state.nodes

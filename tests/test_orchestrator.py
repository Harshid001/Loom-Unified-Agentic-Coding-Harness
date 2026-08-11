import asyncio
import pytest
from loom.adapters.router import ModelRouter
from loom.telemetry.tracer import TelemetryTracer
from loom.telemetry.cost_tracker import CostTracker
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph

@pytest.mark.asyncio
async def test_task_graph_execution(tmp_path):
    run_id = "test_run_001"
    state = OrchestratorState(
        run_id=run_id,
        repo_path=str(tmp_path),
        issue_description="Fix null pointer exception"
    )
    router = ModelRouter(mock_mode=True)
    tracer = TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces"))
    cost_tracker = CostTracker(run_id=run_id)

    task_graph = TaskGraph(state, router, tracer, cost_tracker)
    final_state = await task_graph.run()

    assert "onboarding" in final_state.nodes
    assert final_state.nodes["onboarding"].status == "completed"
    assert "reproduction" in final_state.nodes
    assert "patcher" in final_state.nodes
    assert "verifier" in final_state.nodes
    assert "reviewer" in final_state.nodes
    assert final_state.shared_data.get("reviewer_report") is not None


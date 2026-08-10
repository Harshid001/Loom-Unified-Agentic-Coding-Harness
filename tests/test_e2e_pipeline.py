import asyncio
import pytest
from pathlib import Path
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph
from loom.adapters.router import ModelRouter
from loom.telemetry.tracer import TelemetryTracer
from loom.telemetry.cost_tracker import CostTracker
from loom.sandbox.local_process import LocalProcessSandbox

def test_full_pipeline_e2e(tmp_path):
    async def run():
        # Setup temporary repository fixture
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        src_file = repo_dir / "app.py"
        src_file.write_text("def add(a, b):\n    return a - b  # Bug: subtraction instead of addition\n", encoding="utf-8")

        run_id = "test_run_e2e_001"
        state = OrchestratorState(
            run_id=run_id,
            repo_path=str(repo_dir),
            issue_description="Fix bug in add function: returns a - b instead of a + b"
        )

        router = ModelRouter(default_model="claude-3-5-sonnet-20241022", mock_mode=True)
        tracer = TelemetryTracer(run_id=run_id, log_dir=str(tmp_path / "traces"))
        cost_tracker = CostTracker(run_id=run_id)

        task_graph = TaskGraph(state, router, tracer, cost_tracker)
        final_state = await task_graph.run()

        # Check execution state assertions
        assert final_state.run_id == run_id
        assert "repo_map" in final_state.shared_data
        assert final_state.reproduction_test is not None
        assert final_state.verification_passed is True
        assert len(tracer.events) > 0

        # Verify Sandbox snapshot restoration / rollback flow
        sandbox = LocalProcessSandbox(repo_path=str(repo_dir))
        snapshot_id = sandbox.create_snapshot("Pre-patch snapshot")
        assert snapshot_id is not None
        
        # Modify file and restore
        src_file.write_text("broken content", encoding="utf-8")
        success = sandbox.restore_snapshot(snapshot_id)
        assert success is True
        assert "def add" in src_file.read_text(encoding="utf-8")

    asyncio.run(run())

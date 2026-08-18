"""Unit tests for loom.runtime.executor."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loom.orchestrator.state import NodeStatus, OrchestratorState
from loom.runtime.executor import _resume_node, execute_run_job
from loom.runtime.job_queue import RunJob


@pytest.fixture
def sample_job():
    return RunJob(
        job_id="job_exec_001",
        run_id="run_exec_001",
        org_id="org_exec",
        repo_path="/workspace/exec_repo",
        issue="Fix memory leak in buffer",
        model="gpt-4o",
        mock=True,
        sandbox_tier="A",
        auto_merge_threshold=0.9,
        created_at=1000.0,
        attempts=0,
    )


def test_resume_node_helper():
    state = OrchestratorState(run_id="run_test", repo_path="/tmp", issue_description="issue")
    sequence = [("onboarding", MagicMock), ("reproduction", MagicMock), ("planner", MagicMock)]

    # 1. No nodes completed -> resumes from first node
    assert _resume_node(state, sequence) == "onboarding"

    # 2. First node completed -> resumes from second node
    state.nodes["onboarding"] = NodeStatus(node_name="onboarding", status="completed")
    assert _resume_node(state, sequence) == "reproduction"

    # 3. All nodes completed -> returns None
    state.nodes["reproduction"] = NodeStatus(node_name="reproduction", status="completed")
    state.nodes["planner"] = NodeStatus(node_name="planner", status="completed")
    assert _resume_node(state, sequence) is None


@pytest.mark.asyncio
async def test_execute_run_job_fresh_success(sample_job, tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_REPO_ROOTS", str(tmp_path))

    mock_coord = MagicMock()
    mock_coord.enabled = True
    mock_coord.record_event = AsyncMock()
    mock_coord.update_run_status = AsyncMock()
    mock_coord.close = AsyncMock()

    async def fake_control_stream(run_id):
        yield {"action": "step"}

    mock_coord.control_stream = fake_control_stream

    mock_store = MagicMock()
    mock_store.record_run = MagicMock()

    with patch("loom.runtime.executor.RedisCoordinator", return_value=mock_coord), \
         patch("loom.runtime.executor.get_run_record_store", return_value=mock_store), \
         patch("loom.orchestrator.task_graph.TaskGraph.run", new=AsyncMock()) as mock_run:

        async def fake_run(*args, **kwargs):
            mock_run_state = OrchestratorState(run_id=sample_job.run_id, repo_path=sample_job.repo_path, issue_description=sample_job.issue)
            return mock_run_state

        mock_run.side_effect = fake_run

        final_state = await execute_run_job(sample_job)

        assert final_state.run_id == sample_job.run_id
        assert "worker_duration_seconds" in final_state.shared_data
        assert mock_store.record_run.called
        assert mock_coord.update_run_status.called
        assert mock_coord.close.called


@pytest.mark.asyncio
async def test_execute_run_job_resumes_from_checkpoint(sample_job, tmp_path):
    existing_state = OrchestratorState(run_id=sample_job.run_id, repo_path=sample_job.repo_path, issue_description=sample_job.issue)
    existing_state.nodes["onboarding"] = NodeStatus(node_name="onboarding", status="completed")

    mock_coord = MagicMock()
    mock_coord.enabled = False
    mock_coord.close = AsyncMock()

    mock_store = MagicMock()

    with patch("loom.orchestrator.state.OrchestratorState.load_checkpoint", return_value=existing_state), \
         patch("loom.runtime.executor.RedisCoordinator", return_value=mock_coord), \
         patch("loom.runtime.executor.get_run_record_store", return_value=mock_store), \
         patch("loom.orchestrator.task_graph.TaskGraph.run", new=AsyncMock(return_value=existing_state)) as mock_run:

        final_state = await execute_run_job(sample_job)

        assert final_state.run_id == sample_job.run_id
        # Should have called run with resume_from set
        assert mock_run.call_args[1].get("resume_from") == "reproduction"


@pytest.mark.asyncio
async def test_execute_run_job_handles_failure_and_checkpoints(sample_job, tmp_path):
    mock_coord = MagicMock()
    mock_coord.enabled = True
    mock_coord.record_event = AsyncMock()
    mock_coord.update_run_status = AsyncMock()
    mock_coord.close = AsyncMock()

    async def fake_empty_stream(run_id):
        if False:
            yield {}

    mock_coord.control_stream = fake_empty_stream
    mock_store = MagicMock()

    with patch("loom.runtime.executor.RedisCoordinator", return_value=mock_coord), \
         patch("loom.runtime.executor.get_run_record_store", return_value=mock_store), \
         patch("loom.orchestrator.task_graph.TaskGraph.run", side_effect=RuntimeError("Pipeline crash")):

        with pytest.raises(RuntimeError, match="Pipeline crash"):
            await execute_run_job(sample_job)

        assert mock_coord.update_run_status.called
        assert any(call.args[1] == "failed" for call in mock_coord.update_run_status.call_args_list)
        assert mock_coord.close.called


@pytest.mark.asyncio
async def test_execute_run_job_budget_watchdog(sample_job, monkeypatch):
    monkeypatch.setenv("LOOM_MAX_RUN_DURATION_SECONDS", "0.01")

    mock_coord = MagicMock()
    mock_coord.enabled = True
    mock_coord.record_event = AsyncMock()
    mock_coord.update_run_status = AsyncMock()
    mock_coord.close = AsyncMock()

    async def fake_empty_stream(run_id):
        if False:
            yield {}

    mock_coord.control_stream = fake_empty_stream
    mock_store = MagicMock()

    async def slow_run(resume_from=None):
        await asyncio.sleep(0.05)
        state = OrchestratorState(run_id=sample_job.run_id, repo_path=sample_job.repo_path, issue_description=sample_job.issue)
        state.shared_data["budget_exceeded"] = True
        return state

    with patch("loom.runtime.executor.RedisCoordinator", return_value=mock_coord), \
         patch("loom.runtime.executor.get_run_record_store", return_value=mock_store), \
         patch("loom.orchestrator.task_graph.TaskGraph.run", side_effect=slow_run):

        final_state = await execute_run_job(sample_job)
        assert final_state.shared_data.get("budget_exceeded") is True


@pytest.mark.asyncio
async def test_execute_run_job_control_and_step_callbacks(sample_job, tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_REPO_ROOTS", str(tmp_path))

    mock_coord = MagicMock()
    mock_coord.enabled = True
    mock_coord.record_event = AsyncMock()
    mock_coord.update_run_status = AsyncMock()
    mock_coord.close = AsyncMock()

    async def fake_control_stream(run_id):
        yield {"action": "pause"}
        yield {"action": "resume"}
        yield {"action": "step"}
        yield {"action": "cancel"}
        yield {"action": "model_switch", "payload": {"model": "gpt-4o-mini"}}

    mock_coord.control_stream = fake_control_stream
    mock_store = MagicMock()

    async def mock_run_invoking_callbacks(self, resume_from=None):
        # Allow control loop to process messages
        await asyncio.sleep(0.02)
        if self.on_step_start_cb:
            self.on_step_start_cb("onboarding", "mock")
        if self.on_step_complete_cb:
            self.on_step_complete_cb("onboarding", {"_usage": {"tokens": 100}})
        if self.on_step_fail_cb:
            self.on_step_fail_cb("onboarding", "step failure")
        return self.state

    with patch("loom.runtime.executor.RedisCoordinator", return_value=mock_coord), \
         patch("loom.runtime.executor.get_run_record_store", return_value=mock_store), \
         patch("loom.orchestrator.task_graph.TaskGraph.run", side_effect=mock_run_invoking_callbacks, autospec=True):

        final_state = await execute_run_job(sample_job)
        assert final_state.run_id == sample_job.run_id
        assert mock_coord.record_event.called



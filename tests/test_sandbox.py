import pytest

from loom.orchestrator.state import OrchestratorState
from loom.sandbox.factory import sandbox_for_state
from loom.sandbox.firecracker_sandbox import FirecrackerSandbox
from loom.sandbox.local_process import LocalProcessSandbox


def test_local_sandbox(tmp_path):
    sandbox = LocalProcessSandbox(str(tmp_path))
    result = sandbox.run_command("python -c \"print('hello')\"")
    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_production_factory_uses_firecracker_for_tier_b(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("LOOM_FIRECRACKER_WORKER_URL", "http://firecracker-worker:8101")
    monkeypatch.setenv("LOOM_FIRECRACKER_WORKER_TOKEN", "worker-secret")
    state = OrchestratorState(run_id="run_test", repo_path=str(tmp_path), issue_description="test")
    state.shared_data["sandbox_tier"] = "B"
    sandbox = sandbox_for_state(state)
    assert isinstance(sandbox, FirecrackerSandbox)


def test_production_factory_uses_firecracker_for_tier_c(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("LOOM_FIRECRACKER_WORKER_URL", "http://firecracker-worker:8101")
    monkeypatch.setenv("LOOM_FIRECRACKER_WORKER_TOKEN", "worker-secret")
    state = OrchestratorState(run_id="run_test", repo_path=str(tmp_path), issue_description="test")
    state.shared_data["sandbox_tier"] = "C"
    sandbox = sandbox_for_state(state)
    assert isinstance(sandbox, FirecrackerSandbox)

import pytest

from loom.business.models import OrgTier
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.docker_sandbox import DockerSandbox
from loom.sandbox.factory import sandbox_for_state
from loom.sandbox.firecracker_sandbox import FirecrackerSandbox
from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.remote import RemoteDockerSandbox
from loom.sandbox.tiers import SandboxContext, SandboxTier, SandboxTierSelector


def test_production_factory_uses_firecracker_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("LOOM_FIRECRACKER_WORKER_URL", "http://firecracker-worker:8101")
    monkeypatch.setenv("LOOM_FIRECRACKER_WORKER_TOKEN", "worker-secret")

    state = OrchestratorState(run_id="run_test", repo_path=str(tmp_path), issue_description="test")
    state.shared_data["sandbox_tier"] = "C"

    sandbox = sandbox_for_state(state)
    assert isinstance(sandbox, FirecrackerSandbox)


def test_production_factory_fails_closed_for_missing_firecracker_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_URL", raising=False)
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_TOKEN", raising=False)

    state = OrchestratorState(run_id="run_test", repo_path=str(tmp_path), issue_description="test")
    state.shared_data["sandbox_tier"] = "C"

    with pytest.raises(RuntimeError, match="requires LOOM_FIRECRACKER_WORKER_URL"):
        sandbox_for_state(state)

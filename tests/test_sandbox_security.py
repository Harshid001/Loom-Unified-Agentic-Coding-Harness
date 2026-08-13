import pytest

from loom.orchestrator.state import OrchestratorState
from loom.sandbox.docker_sandbox import DockerSandbox
from loom.sandbox.factory import sandbox_for_state


def _state(tier: str) -> OrchestratorState:
    state = OrchestratorState(run_id=f"run_{tier}", repo_path="/tmp/repo", issue_description="sandbox")
    state.shared_data["sandbox_tier"] = tier
    return state


def test_production_tier_a_is_rejected(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    with pytest.raises(RuntimeError, match="Tier A"):
        sandbox_for_state(_state("A"))


def test_docker_network_is_disabled_by_default(tmp_path):
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("LOOM_ENV", "production")
        sandbox = DockerSandbox(str(tmp_path))
        assert sandbox.allow_network is False
    finally:
        monkeypatch.undo()

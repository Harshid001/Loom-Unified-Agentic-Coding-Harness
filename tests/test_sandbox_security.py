from pathlib import Path

import pytest

from loom.orchestrator.state import OrchestratorState
from loom.sandbox.factory import sandbox_for_state
from loom.sandbox.firecracker_sandbox import FirecrackerSandbox


def test_production_tier_a_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    state = OrchestratorState(run_id="run_test", repo_path=str(tmp_path), issue_description="test")
    state.shared_data["sandbox_tier"] = "A"
    with pytest.raises(RuntimeError, match="Production Tier A host execution is disabled"):
        sandbox_for_state(state)


def test_firecracker_fails_closed_without_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_URL", raising=False)
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_CMD", raising=False)
    result = FirecrackerSandbox(str(tmp_path)).run_command(["python", "-c", "print(1)"])
    assert result.exit_code == 125
    assert "LOOM_FIRECRACKER_WORKER_URL" in result.stderr

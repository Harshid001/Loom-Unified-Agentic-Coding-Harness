import pytest

from loom.business.models import OrgTier
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.docker_sandbox import DockerSandbox
from loom.sandbox.factory import sandbox_for_state
from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.remote import RemoteDockerSandbox
from loom.sandbox.tiers import SandboxContext, SandboxTier, SandboxTierSelector


def test_local_sandbox(tmp_path):
    sandbox = LocalProcessSandbox(str(tmp_path))
    res = sandbox.run_command("python -c \"print('hello')\"")
    assert res.exit_code == 0
    assert "hello" in res.stdout


def test_cross_instance_rollback(tmp_path):
    test_file = tmp_path / "app.py"
    test_file.write_text("original content", encoding="utf-8")

    sandbox1 = LocalProcessSandbox(str(tmp_path))
    snap_id = sandbox1.create_snapshot("test_snap")

    test_file.write_text("mutated content", encoding="utf-8")
    assert test_file.read_text(encoding="utf-8") == "mutated content"

    sandbox2 = LocalProcessSandbox(str(tmp_path))
    success = sandbox2.restore_snapshot(snap_id)

    assert success is True
    assert test_file.read_text(encoding="utf-8") == "original content"


def test_docker_sandbox_instantiation(tmp_path):
    sandbox = DockerSandbox(str(tmp_path), cpu_limit=2.0, memory_mb=4096)
    assert sandbox.image_name == "python:3.11-slim"
    assert sandbox.cpu_limit == 2.0
    assert sandbox.memory_mb == 4096


def test_docker_sandbox_fails_closed_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    sandbox = DockerSandbox(str(tmp_path), allow_local_fallback=False)
    monkeypatch.setattr(sandbox, "is_docker_available", lambda: False)

    result = sandbox.run_command(["python", "-c", "print('must-not-run-on-host')"])

    assert result.exit_code == 125
    assert "fail-closed" in result.stderr


def test_docker_sandbox_allows_explicit_dev_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    sandbox = DockerSandbox(str(tmp_path), allow_local_fallback=True)
    monkeypatch.setattr(sandbox, "is_docker_available", lambda: False)

    result = sandbox.run_command(["python", "-c", "print('dev-fallback')"])

    assert result.exit_code == 0
    assert "dev-fallback" in result.stdout


def test_sandbox_tier_selector_creates_docker_sandbox(tmp_path):
    selector = SandboxTierSelector()
    ctx = SandboxContext(org_tier=OrgTier.ENTERPRISE, sandbox_tier=SandboxTier.B_DOCKER_CONTAINER)
    ctx = selector.select_with_resources(ctx)
    sandbox = selector.create_sandbox(ctx, str(tmp_path))
    assert isinstance(sandbox, DockerSandbox)
    assert sandbox.cpu_limit == 2.0

    ctx_c = SandboxContext(org_tier=OrgTier.ENTERPRISE, patch_risk_high=True)
    ctx_c = selector.select_with_resources(ctx_c)
    sandbox_c = selector.create_sandbox(ctx_c, str(tmp_path))
    assert isinstance(sandbox_c, DockerSandbox)
    assert sandbox_c.read_only_root is True


def test_production_factory_requires_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("LOOM_SANDBOX_WORKER_URL", raising=False)
    monkeypatch.delenv("SANDBOX_WORKER_TOKEN", raising=False)

    state = OrchestratorState(run_id="run_test", repo_path=str(tmp_path), issue_description="test")
    state.shared_data["sandbox_tier"] = "B"

    with pytest.raises(RuntimeError, match="requires LOOM_SANDBOX_WORKER_URL"):
        sandbox_for_state(state)


def test_production_factory_uses_remote_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("LOOM_SANDBOX_WORKER_URL", "http://sandbox-worker:8100")
    monkeypatch.setenv("SANDBOX_WORKER_TOKEN", "worker-secret")

    state = OrchestratorState(run_id="run_test", repo_path=str(tmp_path), issue_description="test")
    state.shared_data["sandbox_tier"] = "B"

    sandbox = sandbox_for_state(state)
    assert isinstance(sandbox, RemoteDockerSandbox)


def test_production_factory_fails_closed_for_fake_firecracker(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("LOOM_SANDBOX_WORKER_URL", "http://sandbox-worker:8100")
    monkeypatch.setenv("SANDBOX_WORKER_TOKEN", "worker-secret")

    state = OrchestratorState(run_id="run_test", repo_path=str(tmp_path), issue_description="test")
    state.shared_data["sandbox_tier"] = "C"

    with pytest.raises(RuntimeError, match="requires a configured Firecracker worker"):
        sandbox_for_state(state)

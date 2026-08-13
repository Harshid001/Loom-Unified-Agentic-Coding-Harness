from loom.business.models import OrgTier
from loom.sandbox.docker_sandbox import DockerSandbox
from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.tiers import SandboxContext, SandboxTier, SandboxTierSelector


def test_local_sandbox(tmp_path):
    sandbox = LocalProcessSandbox(str(tmp_path))
    res = sandbox.run_command("python -c \"print('hello')\"")
    assert res.exit_code == 0
    assert "hello" in res.stdout


def test_cross_instance_rollback(tmp_path):
    test_file = tmp_path / "app.py"
    test_file.write_text("original content", encoding="utf-8")

    # Instance 1: Create snapshot
    sandbox1 = LocalProcessSandbox(str(tmp_path))
    snap_id = sandbox1.create_snapshot("test_snap")

    # Mutate file
    test_file.write_text("mutated content", encoding="utf-8")
    assert test_file.read_text(encoding="utf-8") == "mutated content"

    # Instance 2: Restore snapshot across fresh instance/process boundary
    sandbox2 = LocalProcessSandbox(str(tmp_path))
    success = sandbox2.restore_snapshot(snap_id)

    assert success is True
    assert test_file.read_text(encoding="utf-8") == "original content"


def test_docker_sandbox_instantiation(tmp_path):
    sandbox = DockerSandbox(str(tmp_path), cpu_limit=2.0, memory_mb=4096)
    assert sandbox.image_name == "python:3.11-slim"
    assert sandbox.cpu_limit == 2.0
    assert sandbox.memory_mb == 4096


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

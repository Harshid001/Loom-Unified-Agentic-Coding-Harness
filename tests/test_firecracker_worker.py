import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Configure token before module import
os.environ.setdefault("LOOM_FIRECRACKER_WORKER_TOKEN", "test-worker-token")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from loom.sandbox import firecracker_worker
from loom.sandbox.firecracker_worker import (
    app,
    authenticate,
    resolve_repo,
    sha256_file,
)


@pytest.fixture
def worker_client(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(firecracker_worker, "WORKER_TOKEN", "test-worker-token")
    monkeypatch.setattr(firecracker_worker, "REPO_ROOT", tmp_path / "repos")
    (tmp_path / "repos").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(firecracker_worker, "RUNTIME_DIR", tmp_path / "runtime")
    (tmp_path / "runtime").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(firecracker_worker, "EVIDENCE_DIR", tmp_path / "evidence")
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    return TestClient(app)


def test_authenticate_valid_and_invalid(monkeypatch):
    monkeypatch.setattr(firecracker_worker, "WORKER_TOKEN", "secret-token")

    # Valid
    authenticate(authorization="Bearer secret-token")

    # Missing / wrong
    with pytest.raises(HTTPException) as exc:
        authenticate(authorization=None)
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        authenticate(authorization="Bearer wrong-token")
    assert exc.value.status_code == 401


def test_resolve_repo_security(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repos"
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(firecracker_worker, "REPO_ROOT", repo_root)
    monkeypatch.setattr(firecracker_worker, "ENFORCE_ORG_ROOT", True)

    org_root = repo_root / "org_123"
    org_root.mkdir()
    valid_repo = org_root / "project"
    valid_repo.mkdir()

    # Valid resolution
    res = resolve_repo(str(valid_repo), org_id="org_123")
    assert res == valid_repo.resolve()

    # Outside org root
    other_repo = repo_root / "other_org" / "project"
    other_repo.mkdir(parents=True, exist_ok=True)
    with pytest.raises(HTTPException) as exc:
        resolve_repo(str(other_repo), org_id="org_123")
    assert exc.value.status_code == 403

    # Outside repository root entirely
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(HTTPException) as exc:
        resolve_repo(str(outside), org_id="org_123")
    assert exc.value.status_code == 403


def test_sha256_file(tmp_path: Path):
    f = tmp_path / "data.txt"
    f.write_text("hello world")
    digest = sha256_file(f)
    assert len(digest) == 64
    assert digest == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_health_endpoint(worker_client):
    with patch("loom.sandbox.firecracker_worker.host_health", return_value={"status": "ok", "runtime": "firecracker"}):
        resp = worker_client.get("/health", headers={"Authorization": "Bearer test-worker-token"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_execute_endpoint(worker_client, tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repos"
    org_repo = repo_root / "org_test" / "my_repo"
    org_repo.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(firecracker_worker, "REPO_ROOT", repo_root)
    monkeypatch.setattr(firecracker_worker, "ENFORCE_ORG_ROOT", True)

    mock_vm = MagicMock()
    mock_vm.__enter__.return_value = mock_vm
    mock_vm.exec.return_value = {
        "status": "ok",
        "exit_code": 0,
        "stdout": "success\n",
        "stderr": "",
        "timed_out": False,
    }

    with patch("loom.sandbox.firecracker_worker.host_health", return_value={"status": "ok"}), \
         patch("loom.sandbox.firecracker_worker.sha256_file", return_value="dummyhash"), \
         patch("loom.sandbox.firecracker_worker.FirecrackerVM", return_value=mock_vm), \
         patch("loom.sandbox.firecracker_worker.FirecrackerConfig.validate"):
        payload = {
            "run_id": "run-001",
            "org_id": "org_test",
            "repo_path": str(org_repo),
            "command": "python test.py",
            "timeout": 30,
        }
        resp = worker_client.post(
            "/execute",
            json=payload,
            headers={"Authorization": "Bearer test-worker-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["exit_code"] == 0
        assert data["stdout"] == "success\n"
        assert (tmp_path / "evidence" / "run-001.json").exists()


def test_execute_network_rejected(worker_client):
    payload = {
        "run_id": "run-net",
        "org_id": "org_test",
        "repo_path": "/some/path",
        "command": "curl example.com",
        "network": True,
    }
    resp = worker_client.post(
        "/execute",
        json=payload,
        headers={"Authorization": "Bearer test-worker-token"},
    )
    assert resp.status_code == 400
    assert "network-enabled" in resp.json()["detail"]


def test_snapshot_and_restore_endpoints(worker_client, tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repos"
    org_repo = repo_root / "org_test" / "snap_repo"
    org_repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(firecracker_worker, "REPO_ROOT", repo_root)

    with patch("loom.sandbox.firecracker_worker.WorktreeManager") as mock_wt:
        instance = mock_wt.return_value
        instance.create_snapshot.return_value = "snap-123"
        instance.restore_snapshot.return_value = True

        snap_resp = worker_client.post(
            "/snapshot",
            json={"org_id": "org_test", "repo_path": str(org_repo), "label": "test-snap"},
            headers={"Authorization": "Bearer test-worker-token"},
        )
        assert snap_resp.status_code == 200
        assert snap_resp.json()["snapshot_id"] == "snap-123"

        restore_resp = worker_client.post(
            "/restore",
            json={"org_id": "org_test", "repo_path": str(org_repo), "snapshot_id": "snap-123"},
            headers={"Authorization": "Bearer test-worker-token"},
        )
        assert restore_resp.status_code == 200
        assert restore_resp.json()["restored"] is True


def test_recover_endpoint(worker_client):
    with patch("loom.sandbox.firecracker_worker.reconcile_runtime", return_value={"cleaned": 2, "failed": 0}):
        resp = worker_client.post("/recover", headers={"Authorization": "Bearer test-worker-token"})
        assert resp.status_code == 200
        assert resp.json()["cleaned"] == 2


def test_health_failure_503(worker_client):
    with patch("loom.sandbox.firecracker_worker.host_health", side_effect=RuntimeError("KVM unavailable")):
        resp = worker_client.get("/health", headers={"Authorization": "Bearer test-worker-token"})
        assert resp.status_code == 503
        assert "KVM unavailable" in resp.json()["detail"]


def test_execute_failure_502(worker_client, tmp_path: Path, monkeypatch):
    from loom.sandbox.firecracker_vm import FirecrackerVMError

    repo_root = tmp_path / "repos"
    org_repo = repo_root / "org_test" / "fail_repo"
    org_repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(firecracker_worker, "REPO_ROOT", repo_root)

    with patch("loom.sandbox.firecracker_worker.host_health", return_value={"status": "ok"}), \
         patch("loom.sandbox.firecracker_worker.sha256_file", return_value="dummyhash"), \
         patch("loom.sandbox.firecracker_worker.FirecrackerConfig.validate"), \
         patch("loom.sandbox.firecracker_worker.FirecrackerVM", side_effect=FirecrackerVMError("VM boot failure")):
        resp = worker_client.post(
            "/execute",
            json={"run_id": "run-fail", "org_id": "org_test", "repo_path": str(org_repo), "command": "echo 1"},
            headers={"Authorization": "Bearer test-worker-token"},
        )
        assert resp.status_code == 502


def test_sha256sum_file_contains_real_hash():
    """Production-grade guard: infra/firecracker/SHA256SUM must contain a real
    64-char hex hash that matches the upstream Firecracker v1.16.1 release,
    not the placeholder. The host validator fails closed otherwise."""
    import re

    repo_root = Path(__file__).resolve().parents[1]
    sha256_file = repo_root / "infra" / "firecracker" / "SHA256SUM"
    assert sha256_file.exists(), "infra/firecracker/SHA256SUM must exist"

    raw = sha256_file.read_text(encoding="utf-8")
    hashes = [
        line.strip().lower()
        for line in raw.splitlines()
        if re.fullmatch(r"[0-9a-fA-F]{64}", line.strip())
    ]
    assert len(hashes) == 1, f"Expected exactly one hash, got {len(hashes)}: {hashes}"
    assert set(hashes[0]) != {"0"}, "Placeholder (all zeros) hash detected"
    # Officially published Firecracker v1.16.1 x86_64 release hash:
    assert hashes[0] == (
        "382a02a869e4d6d5cb14c40577f9545e8458021ea8b0b2d3fc10ec14d9c242e6"
    ), f"SHA256SUM must pin the published v1.16.1 hash; got {hashes[0]}"


def test_host_health_rejects_missing_approved_hash(tmp_path: Path):
    """host_health() must fail closed when the approved SHA256SUM contains
    no real hash (regression for the old placeholder-text issue)."""
    import io as _io
    import os as _os

    fake_hash_file = tmp_path / "SHA256SUM.empty"
    fake_hash_file.write_text("# REQUIRED: replace with the SHA-256...\n", encoding="utf-8")

    binary = tmp_path / "firecracker_bin"
    binary.write_bytes(b"fake-firecracker-binary-content-for-hash-test")
    kernel = tmp_path / "vmlinux"
    kernel.write_bytes(b"kernel")
    rootfs = tmp_path / "rootfs.ext4"
    rootfs.write_bytes(b"rootfs")

    _orig_name = _os.name
    _os.name = "posix"
    try:
        with patch.object(firecracker_worker, "APPROVED_HASH_FILE", fake_hash_file), \
             patch.object(firecracker_worker, "FIRECRACKER_BIN", binary), \
             patch.object(firecracker_worker, "KERNEL_PATH", kernel), \
             patch.object(firecracker_worker, "ROOTFS_PATH", rootfs), \
             patch.object(firecracker_worker.platform, "machine", return_value="x86_64"), \
             patch.object(firecracker_worker.os, "popen", lambda cmd: _io.StringIO("Firecracker v1.16.1\n")), \
             patch.object(firecracker_worker.os, "access", lambda p, m: True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            with pytest.raises(RuntimeError, match="approved Firecracker SHA256"):
                firecracker_worker.host_health()
    finally:
        _os.name = _orig_name


def test_host_health_rejects_mismatched_hash(tmp_path: Path):
    """host_health() must fail closed when the approved hash doesn't match
    the actual binary hash."""
    import io as _io
    import os as _os

    fake_hash_file = tmp_path / "SHA256SUM"
    fake_hash_file.write_text("0" * 64 + "\n", encoding="utf-8")

    binary = tmp_path / "firecracker_bin"
    binary.write_bytes(b"some-binary-content")
    kernel = tmp_path / "vmlinux"
    kernel.write_bytes(b"kernel")
    rootfs = tmp_path / "rootfs.ext4"
    rootfs.write_bytes(b"rootfs")

    _orig_name = _os.name
    _os.name = "posix"
    try:
        with patch.object(firecracker_worker, "APPROVED_HASH_FILE", fake_hash_file), \
             patch.object(firecracker_worker, "FIRECRACKER_BIN", binary), \
             patch.object(firecracker_worker, "KERNEL_PATH", kernel), \
             patch.object(firecracker_worker, "ROOTFS_PATH", rootfs), \
             patch.object(firecracker_worker.platform, "machine", return_value="x86_64"), \
             patch.object(firecracker_worker.os, "popen", lambda cmd: _io.StringIO("Firecracker v1.16.1\n")), \
             patch.object(firecracker_worker.os, "access", lambda p, m: True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            with pytest.raises(RuntimeError, match="approved Firecracker SHA256"):
                firecracker_worker.host_health()
    finally:
        _os.name = _orig_name


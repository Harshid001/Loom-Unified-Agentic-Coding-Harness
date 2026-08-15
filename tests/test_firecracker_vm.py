import json
import socket
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loom.sandbox.firecracker_vm import (
    FirecrackerConfig,
    FirecrackerVM,
    FirecrackerVMError,
    reconcile_runtime,
)


@pytest.fixture
def mock_fc_paths(tmp_path: Path):
    bin_path = tmp_path / "firecracker"
    bin_path.write_text("binary")
    kernel_path = tmp_path / "vmlinux"
    kernel_path.write_text("kernel")
    rootfs_path = tmp_path / "rootfs.ext4"
    rootfs_path.write_text("rootfs")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    return bin_path, kernel_path, rootfs_path, runtime_dir


def test_firecracker_config_validate_posix_check(mock_fc_paths):
    bin_p, kern_p, root_p, run_dir = mock_fc_paths
    cfg = FirecrackerConfig(binary=bin_p, kernel=kern_p, rootfs=root_p, runtime_dir=run_dir)

    with patch("os.name", "nt"):
        with pytest.raises(FirecrackerVMError, match="virtio-vsock"):
            cfg.validate()


def test_firecracker_config_validate_missing_files(tmp_path: Path):
    cfg = FirecrackerConfig(
        binary=tmp_path / "missing_bin",
        kernel=tmp_path / "missing_kern",
        rootfs=tmp_path / "missing_root",
        runtime_dir=tmp_path / "runtime",
    )
    with patch("os.name", "posix"), patch.object(socket, "AF_VSOCK", 40, create=True):
        with pytest.raises(FirecrackerVMError, match="missing binary"):
            cfg.validate()


def test_firecracker_config_validate_resources(mock_fc_paths):
    bin_p, kern_p, root_p, run_dir = mock_fc_paths
    cfg = FirecrackerConfig(binary=bin_p, kernel=kern_p, rootfs=root_p, runtime_dir=run_dir, vcpus=0)
    with patch("os.name", "posix"), patch.object(socket, "AF_VSOCK", 40, create=True):
        with pytest.raises(FirecrackerVMError, match="invalid VM resource limits"):
            cfg.validate()

    cfg2 = FirecrackerConfig(binary=bin_p, kernel=kern_p, rootfs=root_p, runtime_dir=run_dir, guest_cid=1)
    with patch("os.name", "posix"), patch.object(socket, "AF_VSOCK", 40, create=True):
        with pytest.raises(FirecrackerVMError, match="invalid guest communication"):
            cfg2.validate()


def test_firecracker_config_validate_kvm(mock_fc_paths):
    bin_p, kern_p, root_p, run_dir = mock_fc_paths
    cfg = FirecrackerConfig(binary=bin_p, kernel=kern_p, rootfs=root_p, runtime_dir=run_dir)
    with patch("os.name", "posix"), patch.object(socket, "AF_VSOCK", 40, create=True):
        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(FirecrackerVMError, match="/dev/kvm"):
                cfg.validate()


def test_firecracker_vm_lifecycle(mock_fc_paths):
    bin_p, kern_p, root_p, run_dir = mock_fc_paths
    cfg = FirecrackerConfig(binary=bin_p, kernel=kern_p, rootfs=root_p, runtime_dir=run_dir)
    metadata = {"test": "meta"}
    vm = FirecrackerVM(cfg, "run-123", metadata)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.pid = 99999
    mock_process.poll.return_value = None

    with patch.object(FirecrackerConfig, "validate"), \
         patch("subprocess.Popen", return_value=mock_process), \
         patch.object(vm, "_wait_api"), \
         patch.object(vm, "_put"), \
         patch.object(vm, "_wait_guest"):
        with vm:
            assert vm.dir.exists()
            meta = json.loads((vm.dir / "metadata.json").read_text(encoding="utf-8"))
            assert meta["pid"] == 99999

    assert vm.process is None
    assert not vm.dir.exists()


def test_firecracker_vm_put_error(mock_fc_paths):
    bin_p, kern_p, root_p, run_dir = mock_fc_paths
    cfg = FirecrackerConfig(binary=bin_p, kernel=kern_p, rootfs=root_p, runtime_dir=run_dir)
    vm = FirecrackerVM(cfg, "run-err", {})

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal error"
    mock_client = MagicMock()
    mock_client.put.return_value = mock_resp
    mock_client_ctx = MagicMock()
    mock_client_ctx.__enter__.return_value = mock_client
    mock_client_ctx.__exit__.return_value = False

    with patch.object(vm, "_client", return_value=mock_client_ctx):
        with pytest.raises(FirecrackerVMError, match="Firecracker /test: 500"):
            vm._put("/test", {})


def test_firecracker_vm_sync_and_exec(mock_fc_paths, tmp_path: Path):
    bin_p, kern_p, root_p, run_dir = mock_fc_paths
    cfg = FirecrackerConfig(binary=bin_p, kernel=kern_p, rootfs=root_p, runtime_dir=run_dir)
    vm = FirecrackerVM(cfg, "run-exec", {})
    vm.dir.mkdir(parents=True, exist_ok=True)

    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')")

    # Mock vsock socket for sync_repository
    mock_sock = MagicMock()
    mock_sock.__enter__.return_value = mock_sock

    with patch("subprocess.run"), \
         patch.object(socket, "AF_VSOCK", 40, create=True), \
         patch("socket.socket", return_value=mock_sock), \
         patch.object(vm, "_recv_line", side_effect=[{"status": "ok"}, {"status": "ok", "exit_code": 0, "stdout": "hello\n", "stderr": ""}]):
        # Create dummy repo.tar
        (vm.dir / "repo.tar").write_bytes(b"dummy tar")
        vm.sync_repository(repo_dir)

        result = vm.exec(["python", "main.py"], cwd="/workspace", timeout=30, env={"FOO": "bar"})
        assert result["status"] == "ok"
        assert result["exit_code"] == 0
        assert result["stdout"] == "hello\n"


def test_reconcile_runtime(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    vm_dir1 = runtime_dir / "vm-1"
    vm_dir1.mkdir()
    (vm_dir1 / "metadata.json").write_text(json.dumps({"pid": 12345}), encoding="utf-8")

    vm_dir2 = runtime_dir / "vm-2"
    vm_dir2.mkdir()
    (vm_dir2 / "metadata.json").write_text("invalid json", encoding="utf-8")

    with patch("os.kill", return_value=None):
        report = reconcile_runtime(runtime_dir)

    assert report["cleaned"] == 1
    assert report["failed"] == 1
    assert not vm_dir1.exists()


def test_firecracker_vm_wait_api(mock_fc_paths):
    bin_p, kern_p, root_p, run_dir = mock_fc_paths
    cfg = FirecrackerConfig(binary=bin_p, kernel=kern_p, rootfs=root_p, runtime_dir=run_dir)
    vm = FirecrackerVM(cfg, "run-wait-api", {})
    vm.dir.mkdir(parents=True, exist_ok=True)
    vm.api_socket.write_text("")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client_ctx = MagicMock()
    mock_client_ctx.__enter__.return_value = mock_client
    mock_client_ctx.__exit__.return_value = False

    with patch.object(vm, "_client", return_value=mock_client_ctx):
        vm._wait_api()


def test_firecracker_vm_recv_line():
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [b'{"status": "ok", "message": ', b'"done"}\n']
    data = FirecrackerVM._recv_line(mock_sock)
    assert data["status"] == "ok"
    assert data["message"] == "done"

    # Closed connection
    mock_sock_closed = MagicMock()
    mock_sock_closed.recv.return_value = b""
    with pytest.raises(FirecrackerVMError, match="guest closed connection"):
        FirecrackerVM._recv_line(mock_sock_closed)


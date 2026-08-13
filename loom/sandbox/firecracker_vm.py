"""Firecracker VM lifecycle for Loom Tier C."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, cast

import httpx


class FirecrackerVMError(RuntimeError):
    pass


@dataclass(frozen=True)
class FirecrackerConfig:
    binary: Path
    kernel: Path
    rootfs: Path
    runtime_dir: Path
    vcpus: int = 2
    memory_mb: int = 4096
    guest_cid: int = 3
    guest_port: int = 1024

    def validate(self) -> None:
        if os.name != "posix" or not hasattr(socket, "AF_VSOCK"):
            raise FirecrackerVMError("Firecracker execution requires Linux virtio-vsock support")
        for name, path in (("binary", self.binary), ("kernel", self.kernel), ("rootfs", self.rootfs)):
            if not path.is_file():
                raise FirecrackerVMError(f"missing {name}: {path}")
        if not (1 <= self.vcpus <= 32 and self.memory_mb >= 128):
            raise FirecrackerVMError("invalid VM resource limits")
        if self.guest_cid < 3 or not (1 <= self.guest_port <= 65535):
            raise FirecrackerVMError("invalid guest communication settings")
        if not Path("/dev/kvm").exists() or not os.access("/dev/kvm", os.R_OK | os.W_OK):
            raise FirecrackerVMError("worker cannot access /dev/kvm")


class FirecrackerVM:
    def __init__(self, config: FirecrackerConfig, run_id: str, metadata: Dict[str, Any]):
        self.config = config
        self.run_id = run_id
        self.metadata = metadata
        self.dir = (config.runtime_dir / run_id).resolve()
        self.api_socket = self.dir / "api.socket"
        self.vsock_socket = self.dir / "guest.vsock"
        self.process: Optional[subprocess.Popen[str]] = None

    def __enter__(self) -> "FirecrackerVM":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.destroy()

    def start(self) -> None:
        self.config.validate()
        self.config.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.dir.mkdir(mode=0o700)
        rootfs = self.dir / "rootfs.ext4"
        shutil.copy2(self.config.rootfs, rootfs)
        self._write_meta({"pid": None, "started_at": time.time()})
        self.process = subprocess.Popen(
            [str(self.config.binary), "--api-sock", str(self.api_socket)],
            cwd=self.dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self._write_meta({"pid": self.process.pid})
        try:
            self._wait_api()
            self._put(
                "/boot-source",
                {
                    "kernel_image_path": str(self.config.kernel),
                    "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
                },
            )
            self._put(
                "/drives/rootfs",
                {
                    "drive_id": "rootfs",
                    "path_on_host": str(rootfs),
                    "is_root_device": True,
                    "is_read_only": False,
                },
            )
            self._put(
                "/machine-config",
                {"vcpu_count": self.config.vcpus, "mem_size_mib": self.config.memory_mb, "smt": False},
            )
            self._put(
                "/vsock",
                {
                    "vsock_id": "guest-vsock",
                    "guest_cid": self.config.guest_cid,
                    "uds_path": str(self.vsock_socket),
                },
            )
            self._put("/actions", {"action_type": "InstanceStart"})
            self._wait_guest()
        except Exception:
            self.destroy()
            raise

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.HTTPTransport(uds=str(self.api_socket)), timeout=5.0)

    def _put(self, path: str, payload: Dict[str, Any]) -> None:
        with self._client() as client:
            response = client.put(f"http://localhost{path}", json=payload)
            if response.status_code not in {200, 204}:
                raise FirecrackerVMError(f"Firecracker {path}: {response.status_code} {response.text}")

    def _wait_api(self) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.process and self.process.poll() is not None:
                raise FirecrackerVMError(f"Firecracker exited: {self.process.returncode}")
            if self.api_socket.exists():
                try:
                    with self._client() as client:
                        response = client.get("http://localhost/version")
                        if response.status_code == 200:
                            return
                except httpx.HTTPError:
                    pass
            time.sleep(0.05)
        raise FirecrackerVMError("Firecracker API socket did not become ready")

    def _wait_guest(self) -> None:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    sock.connect((self.config.guest_cid, self.config.guest_port))
                    sock.sendall(b'{"op":"health"}\n')
                    if self._recv_line(sock).get("status") == "ok":
                        return
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            time.sleep(0.1)
        raise FirecrackerVMError("guest agent did not become ready")

    @staticmethod
    def _recv_line(sock: socket.socket) -> dict[str, Any]:
        data = bytearray()
        while not data.endswith(b"\n"):
            part = sock.recv(65536)
            if not part:
                raise FirecrackerVMError("guest closed connection")
            data.extend(part)
        return cast(dict[str, Any], json.loads(bytes(data).decode()))

    def sync_repository(self, repo: Path) -> None:
        archive = self.dir / "repo.tar"
        subprocess.run(
            ["tar", "--format=posix", "--exclude=.loom_snapshots", "-cf", str(archive), "."],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        with socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM) as sock:
            sock.settimeout(60)
            sock.connect((self.config.guest_cid, self.config.guest_port))
            sock.sendall(
                (json.dumps({"op": "sync_workspace", "size": archive.stat().st_size, "sha256": digest}) + "\n").encode()
            )
            with archive.open("rb") as src:
                for chunk in iter(lambda: src.read(65536), b""):
                    sock.sendall(chunk)
            result = self._recv_line(sock)
            if result.get("status") != "ok":
                raise FirecrackerVMError(str(result.get("error", "workspace sync failed")))
        archive.unlink(missing_ok=True)

    def exec(self, argv: Iterable[str], cwd: str, timeout: int, env: Dict[str, str]) -> dict[str, Any]:
        payload = {"op": "exec", "argv": list(argv), "cwd": cwd, "timeout": timeout, "env": env}
        with socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout + 5)
            sock.connect((self.config.guest_cid, self.config.guest_port))
            sock.sendall((json.dumps(payload) + "\n").encode())
            return self._recv_line(sock)

    def destroy(self) -> None:
        if self.process and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except OSError:
                    pass
        self.process = None
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write_meta(self, values: Dict[str, Any]) -> None:
        self.metadata.update(values)
        (self.dir / "metadata.json").write_text(json.dumps(self.metadata, indent=2, sort_keys=True), encoding="utf-8")


def reconcile_runtime(runtime_dir: Path) -> Dict[str, int]:
    cleaned = failed = 0
    if not runtime_dir.exists():
        return {"cleaned": 0, "failed": 0}
    for vm_dir in runtime_dir.iterdir():
        if not vm_dir.is_dir():
            continue
        try:
            data = json.loads((vm_dir / "metadata.json").read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            if pid:
                proc_cmdline = Path(f"/proc/{pid}/cmdline")
                if proc_cmdline.exists():
                    raw = proc_cmdline.read_bytes().replace(b"\x00", b" ").decode(errors="ignore")
                    if "firecracker" not in Path(raw.split()[0]).name.lower() and "firecracker" not in raw.lower():
                        failed += 1
                        continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            shutil.rmtree(vm_dir, ignore_errors=True)
            cleaned += 1
        except Exception:
            failed += 1
    return {"cleaned": cleaned, "failed": failed}

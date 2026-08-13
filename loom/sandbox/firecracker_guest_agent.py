"""Guest-side command agent for Loom Firecracker rootfs images.

Install this module in the immutable Firecracker rootfs and run it as a root
systemd service. The service communicates only over virtio-vsock.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict

try:
    import resource
except ImportError:  # pragma: no cover - POSIX-only stdlib module
    resource = None  # type: ignore[assignment]

DEFAULT_PORT = 1024
WORKSPACE = Path("/workspace")
MAX_ENV_VARS = 128
MAX_ENV_VALUE = 8192
FORBIDDEN_ENV = {"LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH", "NODE_OPTIONS", "RUBYOPT", "PERL5OPT"}


def _safe_extract(tar_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(tar_path, "r:") as archive:
        for member in archive.getmembers():
            member_path = (root / member.name).resolve()
            if root not in member_path.parents and member_path != root:
                raise ValueError(f"tar member escapes workspace: {member.name}")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ValueError(f"unsupported archive member type: {member.name}")
        archive.extractall(root)


def _apply_limits(timeout: int) -> None:
    if resource is None:
        return
    resource.setrlimit(resource.RLIMIT_CPU, (max(1, timeout), max(1, timeout + 1)))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NPROC, (512, 512))


def _validate_env(env: Dict[str, str]) -> Dict[str, str]:
    if len(env) > MAX_ENV_VARS:
        raise ValueError("too many environment variables")
    clean: Dict[str, str] = {}
    for key, value in env.items():
        if (
            not isinstance(key, str)
            or not key
            or "=" in key
            or "\x00" in key
            or key in FORBIDDEN_ENV
        ):
            raise ValueError("invalid or forbidden environment variable name")
        if not isinstance(value, str) or "\x00" in value or len(value) > MAX_ENV_VALUE:
            raise ValueError("invalid environment variable value")
        clean[key] = value
    return clean


def _exec(payload: Dict[str, Any]) -> Dict[str, Any]:
    argv = payload.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or "\x00" in x for x in argv):
        raise ValueError("argv must be a non-empty string list")
    timeout = int(payload.get("timeout", 60))
    if timeout < 1 or timeout > 3600:
        raise ValueError("timeout out of range")
    cwd = Path(str(payload.get("cwd") or WORKSPACE)).resolve()
    if WORKSPACE not in cwd.parents and cwd != WORKSPACE:
        raise ValueError("cwd escapes workspace")
    env = {
        "PATH": os.getenv("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "HOME": "/workspace",
    }
    env.update(_validate_env(payload.get("env") or {}))
    _apply_limits(timeout)
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return {
            "status": "ok",
            "command": " ".join(argv),
            "exit_code": process.returncode,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        stdout, stderr = process.communicate(timeout=2)
        return {
            "status": "ok",
            "command": " ".join(argv),
            "exit_code": 124,
            "stdout": stdout or "",
            "stderr": stderr or "guest command timed out",
            "timed_out": True,
        }


def _handle(sock: socket.socket) -> None:
    with sock:
        reader = sock.makefile("rb")
        first = reader.readline(1024 * 1024)
        if not first:
            return
        payload = json.loads(first.decode("utf-8"))
        op = payload.get("op")
        if op == "health":
            sock.sendall(b'{"status":"ok","runtime":"loom-guest-agent"}\n')
            return
        if op == "sync_workspace":
            size = int(payload.get("size", 0))
            if size <= 0 or size > 4 * 1024 * 1024 * 1024:
                raise ValueError("invalid workspace size")
            expected = str(payload.get("sha256", ""))
            with tempfile.NamedTemporaryFile(dir="/tmp", delete=False) as temp:
                temp_path = Path(temp.name)
                remaining = size
                digest = hashlib.sha256()
                while remaining:
                    chunk = reader.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError("workspace stream ended early")
                    temp.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
            if digest.hexdigest() != expected:
                temp_path.unlink(missing_ok=True)
                raise ValueError("workspace digest mismatch")
            _safe_extract(temp_path, WORKSPACE)
            temp_path.unlink(missing_ok=True)
            sock.sendall(b'{"status":"ok"}\n')
            return
        if op == "exec":
            response = _exec(payload)
            sock.sendall((json.dumps(response) + "\n").encode("utf-8"))
            return
        raise ValueError(f"unknown operation: {op}")


def serve(port: int = DEFAULT_PORT) -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM) as server:
        server.bind((socket.VMADDR_CID_ANY, port))
        server.listen(16)
        while True:
            conn, _ = server.accept()
            try:
                _handle(conn)
            except Exception as exc:
                try:
                    conn.sendall((json.dumps({"status": "error", "error": str(exc)}) + "\n").encode("utf-8"))
                finally:
                    conn.close()


if __name__ == "__main__":
    serve(int(os.getenv("LOOM_GUEST_AGENT_PORT", str(DEFAULT_PORT))))

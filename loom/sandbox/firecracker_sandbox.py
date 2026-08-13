"""Firecracker microVM sandbox provider.

This provider is intentionally fail-closed: production Tier C runs require an
actual Firecracker binary, kernel/rootfs configuration, and an explicit worker
socket. It never downgrades to Docker/local execution.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Union

from loom.sandbox.base import BaseSandbox, CommandResult
from loom.sandbox.worktree import WorktreeManager


class FirecrackerUnavailable(RuntimeError):
    """Raised when Tier C infrastructure is not configured."""


class FirecrackerSandbox(BaseSandbox):
    """Execute a command in a disposable Firecracker microVM.

    The implementation uses an external Firecracker worker process. The worker
    is responsible for creating the VM, mounting the workspace, enforcing the
    jailer/cgroup boundary, executing the argv, collecting output and destroying
    the VM. This class remains a small provider boundary so the orchestrator does
    not depend on Firecracker-specific details.
    """

    def __init__(self, repo_path: str, worker_socket: Optional[str] = None):
        self.repo_path = Path(repo_path).resolve()
        self.worker_socket = worker_socket or os.getenv("LOOM_FIRECRACKER_WORKER_SOCKET")
        self.worktree_manager = WorktreeManager(str(self.repo_path))
        self.binary = os.getenv("FIRECRACKER_BIN", "firecracker")

    def _ensure_configured(self) -> None:
        if not self.worker_socket:
            raise FirecrackerUnavailable(
                "Tier C requires LOOM_FIRECRACKER_WORKER_SOCKET; refusing Docker/local fallback"
            )
        if not Path(self.repo_path).is_dir():
            raise FirecrackerUnavailable(f"Repository path does not exist: {self.repo_path}")

    def run_command(
        self,
        cmd: Union[str, list[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        start = time.time()
        try:
            self._ensure_configured()
        except FirecrackerUnavailable as exc:
            return CommandResult(
                command=cmd if isinstance(cmd, str) else " ".join(cmd),
                exit_code=125,
                stdout="",
                stderr=str(exc),
                duration_seconds=0.0,
                timed_out=False,
            )

        request_id = f"loom-{uuid.uuid4().hex}"
        argv = cmd if isinstance(cmd, list) else ["/bin/sh", "-lc", cmd]
        payload = {
            "request_id": request_id,
            "repo_path": str(self.repo_path),
            "cwd": cwd or str(self.repo_path),
            "argv": argv,
            "timeout": timeout,
            "env": env or {},
        }

        # The production worker contract is intentionally external to the core
        # process. JSONL over stdin/stdout keeps this provider testable without
        # adding a Firecracker Python dependency.
        worker = os.getenv("LOOM_FIRECRACKER_WORKER_CMD")
        if not worker:
            return CommandResult(
                command=cmd if isinstance(cmd, str) else " ".join(cmd),
                exit_code=125,
                stdout="",
                stderr="LOOM_FIRECRACKER_WORKER_CMD is required for Tier C execution",
                duration_seconds=round(time.time() - start, 3),
                timed_out=False,
            )

        try:
            import json

            result = subprocess.run(
                worker.split(),
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=timeout + 10,
                stdin=subprocess.PIPE,
                check=False,
            )
            if result.returncode != 0:
                return CommandResult(
                    command=cmd if isinstance(cmd, str) else " ".join(cmd),
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr or "Firecracker worker failed",
                    duration_seconds=round(time.time() - start, 3),
                    timed_out=False,
                )
            data = json.loads(result.stdout or "{}")
            return CommandResult(
                command=str(data.get("command") or (cmd if isinstance(cmd, str) else " ".join(cmd))),
                exit_code=int(data.get("exit_code", 1)),
                stdout=str(data.get("stdout", "")),
                stderr=str(data.get("stderr", "")),
                duration_seconds=round(float(data.get("duration_seconds", time.time() - start)), 3),
                timed_out=bool(data.get("timed_out", False)),
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=cmd if isinstance(cmd, str) else " ".join(cmd),
                exit_code=124,
                stdout="",
                stderr=f"Firecracker worker timed out after {timeout} seconds",
                duration_seconds=round(time.time() - start, 3),
                timed_out=True,
            )
        except (OSError, ValueError) as exc:
            return CommandResult(
                command=cmd if isinstance(cmd, str) else " ".join(cmd),
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_seconds=round(time.time() - start, 3),
                timed_out=False,
            )

    def create_snapshot(self, label: str) -> str:
        return self.worktree_manager.create_snapshot(label)

    def restore_snapshot(self, snapshot_id: str) -> bool:
        return self.worktree_manager.restore_snapshot(snapshot_id)

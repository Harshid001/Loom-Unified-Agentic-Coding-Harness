"""Loom-facing Firecracker microVM sandbox provider."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast
from urllib.parse import urlparse

import httpx

from loom.sandbox.base import BaseSandbox, CommandResult
from loom.sandbox.worktree import WorktreeManager


class FirecrackerUnavailable(RuntimeError):
    """Raised when Tier C infrastructure is not configured."""


class FirecrackerSandbox(BaseSandbox):
    """Delegate Tier C execution to an authenticated Firecracker worker."""

    def __init__(self, repo_path: str, worker_url: Optional[str] = None, worker_token: Optional[str] = None):
        self.repo_path = Path(repo_path).resolve()
        self.worker_url: str = worker_url or os.getenv("LOOM_FIRECRACKER_WORKER_URL") or ""
        self.worker_token = worker_token or os.getenv("LOOM_FIRECRACKER_WORKER_TOKEN") or os.getenv("SANDBOX_WORKER_TOKEN")
        self.worktree_manager = WorktreeManager(str(self.repo_path))

    def _ensure_configured(self) -> None:
        production = os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}
        if production and not self.worker_url:
            raise FirecrackerUnavailable("Production Tier C requires LOOM_FIRECRACKER_WORKER_URL")
        if not self.worker_url and not os.getenv("LOOM_FIRECRACKER_WORKER_CMD"):
            raise FirecrackerUnavailable("Tier C requires LOOM_FIRECRACKER_WORKER_URL")
        if self.worker_url and not self.worker_token:
            raise FirecrackerUnavailable("Tier C worker authentication requires LOOM_FIRECRACKER_WORKER_TOKEN")
        if production and self.worker_url:
            parsed = urlparse(self.worker_url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise FirecrackerUnavailable("Production Firecracker worker URL must use HTTPS")
        if not self.repo_path.is_dir():
            raise FirecrackerUnavailable(f"Repository path does not exist: {self.repo_path}")

    def _remote(self, payload: dict[str, object], timeout: int) -> CommandResult:
        assert self.worker_url and self.worker_token
        started = time.time()
        headers = {"Authorization": f"Bearer {self.worker_token}"}
        try:
            with httpx.Client(timeout=float(timeout) + 15, follow_redirects=False, verify=True) as client:
                response = client.post(f"{self.worker_url.rstrip('/')}/execute", json=payload, headers=headers)
                response.raise_for_status()
                data = cast(dict[str, Any], response.json())
            return CommandResult(
                command=str(data.get("command", "")),
                exit_code=int(data.get("exit_code", 1)),
                stdout=str(data.get("stdout", "")),
                stderr=str(data.get("stderr", "")),
                duration_seconds=float(data.get("duration_seconds", time.time() - started)),
                timed_out=bool(data.get("timed_out", False)),
            )
        except httpx.HTTPError as exc:
            return CommandResult(
                command=" ".join(str(x) for x in cast(List[str], payload.get("argv", []))),
                exit_code=125,
                stdout="",
                stderr="Firecracker worker request failed",
                duration_seconds=round(time.time() - started, 3),
                timed_out=False,
            )

    def _dev_harness(self, payload: dict[str, object], command: str, timeout: int) -> CommandResult:
        worker = os.getenv("LOOM_FIRECRACKER_WORKER_CMD")
        if not worker:
            raise FirecrackerUnavailable("Firecracker worker command is not configured")
        started = time.time()
        try:
            result = subprocess.run(
                shlex.split(worker),
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=timeout + 10,
                check=False,
            )
            if result.returncode != 0:
                return CommandResult(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr, duration_seconds=round(time.time() - started, 3))
            data = cast(dict[str, Any], json.loads(result.stdout or "{}"))
            return CommandResult(
                command=str(data.get("command", command)),
                exit_code=int(data.get("exit_code", 1)),
                stdout=str(data.get("stdout", "")),
                stderr=str(data.get("stderr", "")),
                duration_seconds=float(data.get("duration_seconds", time.time() - started)),
                timed_out=bool(data.get("timed_out", False)),
            )
        except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            timed_out = isinstance(exc, subprocess.TimeoutExpired)
            return CommandResult(command=command, exit_code=124 if timed_out else 1, stdout="", stderr=str(exc), duration_seconds=round(time.time() - started, 3), timed_out=timed_out)

    def run_command(self, cmd: Union[str, List[str]], cwd: Optional[str] = None, timeout: int = 60, env: Optional[Dict[str, str]] = None) -> CommandResult:
        command = cmd if isinstance(cmd, str) else " ".join(cmd)
        try:
            self._ensure_configured()
        except FirecrackerUnavailable as exc:
            return CommandResult(command=command, exit_code=125, stdout="", stderr=str(exc), duration_seconds=0.0, timed_out=False)
        argv = cmd if isinstance(cmd, list) else ["/bin/sh", "-lc", cmd]
        payload: dict[str, object] = {
            "run_id": f"loom-{uuid.uuid4().hex}",
            "org_id": os.getenv("LOOM_ORG_ID", "unknown"),
            "repo_path": str(self.repo_path),
            "argv": argv,
            "cwd": "/workspace" if cwd is None else str(cwd),
            "timeout": timeout,
            "env": env or {},
            "network": False,
        }
        if self.worker_url:
            return self._remote(payload, timeout)
        return self._dev_harness(payload, command, timeout)

    def create_snapshot(self, label: str) -> str:
        return self.worktree_manager.create_snapshot(label)

    def restore_snapshot(self, snapshot_id: str) -> bool:
        return self.worktree_manager.restore_snapshot(snapshot_id)

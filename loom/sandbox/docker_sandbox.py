import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from loom.sandbox.base import BaseSandbox, CommandResult
from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.worktree import WorktreeManager

logger = logging.getLogger("loom.sandbox.docker")


class DockerSandbox(BaseSandbox):
    """Execute commands inside an isolated Docker container.

    Production mode deliberately fails closed when Docker is unavailable. A local
    process fallback is retained only for explicit development/test usage so a
    missing Docker daemon can never silently remove the sandbox boundary.
    """

    def __init__(
        self,
        repo_path: str,
        image_name: str = "python:3.11-slim",
        cpu_limit: float = 2.0,
        memory_mb: int = 4096,
        read_only_root: bool = False,
        allow_network: bool = True,
        allow_local_fallback: Optional[bool] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.worktree_manager = WorktreeManager(str(self.repo_path))
        self.image_name = image_name
        self.cpu_limit = cpu_limit
        self.memory_mb = memory_mb
        self.read_only_root = read_only_root
        self.allow_network = allow_network
        self.allow_local_fallback = (
            allow_local_fallback
            if allow_local_fallback is not None
            else os.getenv("LOOM_ENV", "development").lower() not in {"prod", "production"}
        )
        self.fallback_sandbox = LocalProcessSandbox(repo_path)
        self._docker_available: Optional[bool] = None

    def is_docker_available(self) -> bool:
        if self._docker_available is not None:
            return self._docker_available
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5,
                stdin=subprocess.DEVNULL,
            )
            self._docker_available = res.returncode == 0
        except (OSError, subprocess.SubprocessError):
            self._docker_available = False

        if not self._docker_available:
            logger.warning("Docker environment unavailable for sandbox execution")
        return self._docker_available

    def _docker_unavailable_result(self, cmd: Union[str, List[str]]) -> CommandResult:
        command = cmd if isinstance(cmd, str) else " ".join(cmd)
        return CommandResult(
            command=command,
            exit_code=125,
            stdout="",
            stderr=(
                "Docker sandbox unavailable. Production execution is fail-closed; "
                "start Docker or configure an approved sandbox worker."
            ),
            duration_seconds=0.0,
            timed_out=False,
        )

    def run_command(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        if not self.is_docker_available():
            if self.allow_local_fallback:
                logger.warning("Using development-only local sandbox fallback")
                return self.fallback_sandbox.run_command(cmd=cmd, cwd=cwd, timeout=timeout, env=env)
            return self._docker_unavailable_result(cmd)

        exec_cwd = Path(cwd).resolve() if cwd else self.repo_path
        try:
            exec_cwd.relative_to(self.repo_path)
        except ValueError:
            exec_cwd = self.repo_path

        rel_cwd = exec_cwd.relative_to(self.repo_path)
        container_workdir = f"/workspace/{rel_cwd}" if str(rel_cwd) != "." else "/workspace"

        if isinstance(cmd, str):
            cmd_str = cmd
            cmd_args = ["sh", "-c", cmd]
        else:
            cmd_str = " ".join(cmd)
            cmd_args = cmd

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--init",
            "-v",
            f"{self.repo_path}:/workspace:rw",
            "-w",
            container_workdir,
            f"--cpus={self.cpu_limit}",
            f"--memory={self.memory_mb}m",
            "--pids-limit=256",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
        ]

        if not self.allow_network:
            docker_cmd.extend(["--network", "none"])

        if self.read_only_root:
            docker_cmd.extend(["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev"])

        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])

        docker_cmd.append(self.image_name)
        docker_cmd.extend(cmd_args)

        start_time = time.time()
        try:
            res = subprocess.run(
                docker_cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
            duration = time.time() - start_time
            return CommandResult(
                command=cmd_str,
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                duration_seconds=round(duration, 3),
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.time() - start_time
            out_str = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err_str = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return CommandResult(
                command=cmd_str,
                exit_code=124,
                stdout=out_str,
                stderr=err_str or f"Container command timed out after {timeout} seconds.",
                duration_seconds=round(duration, 3),
                timed_out=True,
            )
        except OSError as exc:
            return CommandResult(
                command=cmd_str,
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_seconds=round(time.time() - start_time, 3),
                timed_out=False,
            )

    def create_snapshot(self, label: str) -> str:
        return self.worktree_manager.create_snapshot(label)

    def restore_snapshot(self, snapshot_id: str) -> bool:
        return self.worktree_manager.restore_snapshot(snapshot_id)

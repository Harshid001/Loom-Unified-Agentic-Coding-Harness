import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from loom.sandbox.base import BaseSandbox, CommandResult
from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.worktree import WorktreeManager

logger = logging.getLogger("loom.sandbox.docker")


class DockerSandbox(BaseSandbox):
    """Executes commands inside an isolated Docker container with strict CPU/memory limits and dropped privileges."""

    def __init__(
        self,
        repo_path: str,
        image_name: str = "python:3.11-slim",
        cpu_limit: float = 2.0,
        memory_mb: int = 4096,
        read_only_root: bool = False,
        allow_network: bool = True,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.worktree_manager = WorktreeManager(str(self.repo_path))
        self.image_name = image_name
        self.cpu_limit = cpu_limit
        self.memory_mb = memory_mb
        self.read_only_root = read_only_root
        self.allow_network = allow_network

        # Fallback local process sandbox if Docker binary or daemon is unavailable
        self.fallback_sandbox = LocalProcessSandbox(repo_path)
        self._docker_available: Optional[bool] = None

    def is_docker_available(self) -> bool:
        if self._docker_available is not None:
            return self._docker_available
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            self._docker_available = (res.returncode == 0)
        except Exception:
            self._docker_available = False

        if not self._docker_available:
            logger.warning("Docker environment unavailable for Tier B/C sandbox; falling back to process isolation with warnings.")
        return self._docker_available

    def run_command(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        if not self.is_docker_available():
            return self.fallback_sandbox.run_command(cmd=cmd, cwd=cwd, timeout=timeout, env=env)

        exec_cwd = Path(cwd).resolve() if cwd else self.repo_path
        if not exec_cwd.is_relative_to(self.repo_path) and exec_cwd != self.repo_path:
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
            "-v",
            f"{self.repo_path}:/workspace:rw",
            "-w",
            container_workdir,
            f"--cpus={self.cpu_limit}",
            f"--memory={self.memory_mb}m",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
        ]

        if not self.allow_network:
            docker_cmd.extend(["--network", "none"])

        if self.read_only_root:
            docker_cmd.extend(["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid"])

        if env:
            for k, v in env.items():
                docker_cmd.extend(["-e", f"{k}={v}"])

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
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            out_str = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err_str = (
                e.stderr.decode()
                if isinstance(e.stderr, bytes)
                else (e.stderr or f"Container command timed out after {timeout} seconds.")
            )
            return CommandResult(
                command=cmd_str,
                exit_code=124,
                stdout=out_str,
                stderr=err_str,
                duration_seconds=round(duration, 3),
                timed_out=True,
            )
        except Exception as e:
            duration = time.time() - start_time
            return CommandResult(
                command=cmd_str,
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_seconds=round(duration, 3),
                timed_out=False,
            )

    def create_snapshot(self, label: str) -> str:
        return self.worktree_manager.create_snapshot(label)

    def restore_snapshot(self, snapshot_id: str) -> bool:
        return self.worktree_manager.restore_snapshot(snapshot_id)

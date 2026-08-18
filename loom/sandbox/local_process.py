import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loom.sandbox.base import BaseSandbox, CommandResult
from loom.sandbox.worktree import WorktreeManager


class LocalProcessSandbox(BaseSandbox):
    """Executes commands locally with resource timeouts, repo scoping, and egress enforcement."""

    def __init__(self, repo_path: str):
        from loom.sandbox.tiers import EgressEnforcer

        self.repo_path = Path(repo_path).resolve()
        self.worktree_manager = WorktreeManager(str(self.repo_path))
        self.egress_enforcer = EgressEnforcer()

    def run_command(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        from loom.sandbox.tiers import SandboxTier

        exec_cwd = Path(cwd).resolve() if cwd else self.repo_path
        if not exec_cwd.is_relative_to(self.repo_path) and exec_cwd != self.repo_path:
            exec_cwd = self.repo_path

        allowed_roots = os.getenv("ALLOWED_REPO_ROOTS")
        if allowed_roots:
            roots = [Path(r.strip()).resolve() for r in allowed_roots.split(",") if r.strip()]
            roots.append((Path.home() / ".loom").resolve())
            if roots and not any(exec_cwd == r or exec_cwd.is_relative_to(r) for r in roots):
                return CommandResult(
                    command=str(cmd),
                    exit_code=126,
                    stdout="",
                    stderr=f"Sandbox policy: working directory {exec_cwd} is outside ALLOWED_REPO_ROOTS",
                    duration_seconds=0.0,
                    timed_out=False,
                )

        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        if isinstance(cmd, str):
            cmd_args = shlex.split(cmd)
            cmd_str = cmd
        else:
            cmd_args = cmd
            cmd_str = " ".join(cmd)

        blocked_targets = self.egress_enforcer.check_command_egress(cmd_str, SandboxTier.A_GIT_WORKTREE)
        if blocked_targets:
            return CommandResult(
                command=cmd_str,
                exit_code=126,
                stdout="",
                stderr="Sandbox egress policy blocked the command",
                duration_seconds=0.0,
                timed_out=False,
            )

        start_time = time.time()
        try:
            run_kwargs: Dict[str, Any] = {
                "shell": False,
                "cwd": str(exec_cwd),
                "capture_output": True,
                "text": True,
                "timeout": timeout,
                "env": full_env,
                "stdin": subprocess.DEVNULL,
            }
            if os.name == "posix":
                run_kwargs["start_new_session"] = True

            res = subprocess.run(cmd_args, **run_kwargs)
            return CommandResult(
                command=cmd_str,
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                duration_seconds=round(time.time() - start_time, 3),
                timed_out=False,
            )
        except subprocess.TimeoutExpired as e:
            out_str = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err_str = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or f"Command timed out after {timeout} seconds.")
            return CommandResult(
                command=cmd_str,
                exit_code=124,
                stdout=out_str,
                stderr=err_str,
                duration_seconds=round(time.time() - start_time, 3),
                timed_out=True,
            )
        except Exception as e:
            return CommandResult(
                command=cmd_str,
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_seconds=round(time.time() - start_time, 3),
                timed_out=False,
            )

    def execute(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Backward-compatible alias for run_command()."""
        return self.run_command(cmd, cwd=cwd, timeout=timeout, env=env)

    async def arun_command(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Asynchronously run a command without blocking the event loop."""
        import asyncio
        return await asyncio.to_thread(self.run_command, cmd, cwd, timeout, env)

    async def aexecute(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Alias for arun_command."""
        return await self.arun_command(cmd, cwd=cwd, timeout=timeout, env=env)


    def create_snapshot(self, label: str) -> str:
        return self.worktree_manager.create_snapshot(label)

    def create_worktree(self, label: str) -> str:
        """Backward-compatible alias for create_snapshot()."""
        return self.create_snapshot(label)

    def restore_snapshot(self, snapshot_id: str) -> bool:
        return self.worktree_manager.restore_snapshot(snapshot_id)

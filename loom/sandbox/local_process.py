import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from loom.sandbox.base import BaseSandbox, CommandResult
from loom.sandbox.worktree import WorktreeManager


class LocalProcessSandbox(BaseSandbox):
    """Executes commands locally with strict resource timeouts, working directory scoping, and worktree snapshots."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.worktree_manager = WorktreeManager(str(self.repo_path))

    def run_command(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        exec_cwd = Path(cwd).resolve() if cwd else self.repo_path

        # Ensure command executes within repo boundary
        if not exec_cwd.is_relative_to(self.repo_path) and exec_cwd != self.repo_path:
            exec_cwd = self.repo_path

        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        # PRD-005: Parse command list to avoid shell=True security vulnerabilities
        if isinstance(cmd, str):
            cmd_args = shlex.split(cmd)
            cmd_str = cmd
        else:
            cmd_args = cmd
            cmd_str = " ".join(cmd)

        start_time = time.time()
        try:
            res = subprocess.run(
                cmd_args,
                shell=False,
                cwd=str(exec_cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=full_env,
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
                else (e.stderr or f"Command timed out after {timeout} seconds.")
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

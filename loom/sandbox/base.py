from abc import ABC, abstractmethod
from typing import Dict, Optional

from pydantic import BaseModel


class CommandResult(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


class BaseSandbox(ABC):
    @abstractmethod
    def run_command(
        self, cmd: str, cwd: Optional[str] = None, timeout: int = 60, env: Optional[Dict[str, str]] = None
    ) -> CommandResult:
        """Run a command inside the sandbox."""
        pass

    def execute(
        self, cmd: str, cwd: Optional[str] = None, timeout: int = 60, env: Optional[Dict[str, str]] = None
    ) -> CommandResult:
        """Alias for run_command."""
        return self.run_command(cmd, cwd=cwd, timeout=timeout, env=env)

    async def arun_command(
        self, cmd: str, cwd: Optional[str] = None, timeout: int = 60, env: Optional[Dict[str, str]] = None
    ) -> CommandResult:
        """Asynchronously run a command inside the sandbox without blocking the event loop."""
        import asyncio
        return await asyncio.to_thread(self.run_command, cmd, cwd, timeout, env)

    async def aexecute(
        self, cmd: str, cwd: Optional[str] = None, timeout: int = 60, env: Optional[Dict[str, str]] = None
    ) -> CommandResult:
        """Alias for arun_command."""
        return await self.arun_command(cmd, cwd=cwd, timeout=timeout, env=env)


    @abstractmethod
    def create_snapshot(self, label: str) -> str:
        """Create a filesystem / Git snapshot."""
        pass

    @abstractmethod
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore workspace state from a snapshot."""
        pass

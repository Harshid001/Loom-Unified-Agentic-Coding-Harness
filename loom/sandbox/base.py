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

    @abstractmethod
    def create_snapshot(self, label: str) -> str:
        """Create a filesystem / Git snapshot."""
        pass

    @abstractmethod
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore workspace state from a snapshot."""
        pass

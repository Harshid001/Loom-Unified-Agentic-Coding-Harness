"""Client-side sandbox adapter for the isolated Loom sandbox worker."""

from typing import Dict, List, Optional, Union

import httpx

from loom.sandbox.base import BaseSandbox, CommandResult


class RemoteDockerSandbox(BaseSandbox):
    """Delegate sandbox execution to the dedicated sandbox-worker service."""

    def __init__(self, worker_url: str, worker_token: str, repo_path: str, timeout: int = 90):
        self.worker_url = worker_url.rstrip("/")
        self.worker_token = worker_token
        self.repo_path = repo_path
        self.request_timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.worker_token}"}

    def _request(self, method: str, path: str, payload: Dict[str, object]) -> dict:
        with httpx.Client(timeout=self.request_timeout) as client:
            response = client.request(method, f"{self.worker_url}{path}", json=payload, headers=self._headers())
            response.raise_for_status()
            return response.json()

    def run_command(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[str] = None,
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        data = self._request(
            "POST",
            "/execute",
            {
                "repo_path": self.repo_path,
                "cmd": cmd,
                "cwd": cwd,
                "timeout": timeout,
                "env": env or {},
            },
        )
        return CommandResult(**data)

    def create_snapshot(self, label: str) -> str:
        data = self._request("POST", "/snapshot", {"repo_path": self.repo_path, "label": label})
        return str(data["snapshot_id"])

    def restore_snapshot(self, snapshot_id: str) -> bool:
        data = self._request(
            "POST",
            "/restore",
            {"repo_path": self.repo_path, "snapshot_id": snapshot_id},
        )
        return bool(data.get("restored"))

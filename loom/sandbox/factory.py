"""Central sandbox factory used by orchestration agents."""

import os
from typing import Any

from loom.sandbox.base import BaseSandbox
from loom.sandbox.docker_sandbox import DockerSandbox
from loom.sandbox.firecracker_sandbox import FirecrackerSandbox
from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.remote import RemoteDockerSandbox
from loom.sandbox.tiers import SandboxTier


def _remote_worker(repo_path: str) -> BaseSandbox | None:
    worker_url = os.getenv("LOOM_SANDBOX_WORKER_URL")
    worker_token = os.getenv("SANDBOX_WORKER_TOKEN")
    if worker_url and worker_token:
        return RemoteDockerSandbox(worker_url, worker_token, repo_path)
    return None


def sandbox_for_state(state: Any) -> BaseSandbox:
    """Construct the sandbox selected for the current run.

    Tier A remains local only for explicit development/low-risk workflows. Tier B
    uses the dedicated Docker worker in production. Tier C requires a configured
    Firecracker provider and never silently downgrades to Docker.
    """
    tier_value = str(state.shared_data.get("sandbox_tier", SandboxTier.A_GIT_WORKTREE.value)).upper()
    repo_path = state.repo_path
    production = os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}

    if tier_value == SandboxTier.B_DOCKER_CONTAINER.value:
        if production:
            remote = _remote_worker(repo_path)
            if remote is None:
                raise RuntimeError(
                    "Production Tier B execution requires LOOM_SANDBOX_WORKER_URL and SANDBOX_WORKER_TOKEN"
                )
            return remote
        return DockerSandbox(repo_path, cpu_limit=2.0, memory_mb=4096, allow_local_fallback=True)

    if tier_value == SandboxTier.C_FIRECRACKER_MICROVM.value:
        if not os.getenv("LOOM_FIRECRACKER_WORKER_SOCKET") or not os.getenv("LOOM_FIRECRACKER_WORKER_CMD"):
            raise RuntimeError(
                "Production Tier C requires a configured Firecracker worker; refusing Docker/local fallback"
            )
        return FirecrackerSandbox(repo_path)

    if production:
        raise RuntimeError(
            "Production Tier A host execution is disabled. Select Tier B with an approved sandbox worker or Tier C with Firecracker."
        )

    return LocalProcessSandbox(repo_path)


def production_sandbox_required() -> bool:
    return os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}

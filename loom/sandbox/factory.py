"""Central sandbox factory used by orchestration agents."""

import os
from typing import Any

from loom.sandbox.base import BaseSandbox
from loom.sandbox.firecracker_sandbox import FirecrackerSandbox
from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.tiers import SandboxTier


def sandbox_for_state(state: Any) -> BaseSandbox:
    """Construct the sandbox selected for the current run.

    Tier A remains local only for explicit development/low-risk workflows. Tier B
    and Tier C use the authenticated Firecracker worker in production and never
    silently downgrade to host execution.
    """
    tier_value = str(state.shared_data.get("sandbox_tier", SandboxTier.A_GIT_WORKTREE.value)).upper()
    repo_path = state.repo_path
    production = os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}
    is_mock = bool(state.shared_data.get("mock_mode"))

    if tier_value in {SandboxTier.B_FIRECRACKER_MICROVM.value, SandboxTier.C_FIRECRACKER_MICROVM.value}:
        worker_url = os.getenv("LOOM_FIRECRACKER_WORKER_URL")
        worker_token = os.getenv("LOOM_FIRECRACKER_WORKER_TOKEN") or os.getenv("SANDBOX_WORKER_TOKEN")
        if not worker_url or not worker_token:
            raise RuntimeError(
                "Firecracker execution requires LOOM_FIRECRACKER_WORKER_URL and LOOM_FIRECRACKER_WORKER_TOKEN; "
                "refusing Docker/local fallback"
            )
        return FirecrackerSandbox(repo_path, worker_url=worker_url, worker_token=worker_token)

    if production and not is_mock:
        raise RuntimeError(
            "Production Tier A host execution is disabled. Select Tier B or Tier C with Firecracker."
        )

    return LocalProcessSandbox(repo_path)


def production_sandbox_required() -> bool:
    return os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}

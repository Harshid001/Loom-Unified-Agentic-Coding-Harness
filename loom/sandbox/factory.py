"""Central sandbox factory used by orchestration agents.

Keeping sandbox construction in one place prevents individual agents from
silently bypassing the selected sandbox tier and executing target code on the
host process in production.
"""

import os
from typing import Any

from loom.sandbox.base import BaseSandbox
from loom.sandbox.docker_sandbox import DockerSandbox
from loom.sandbox.local_process import LocalProcessSandbox
from loom.sandbox.tiers import SandboxTier


def sandbox_for_state(state: Any) -> BaseSandbox:
    """Construct the sandbox selected for the current run.

    Tier A is intentionally host-local for development/low-risk runs. Tiers B/C
    use Docker and fail closed in production when Docker is unavailable.
    """
    tier_value = str(state.shared_data.get("sandbox_tier", SandboxTier.A_GIT_WORKTREE.value)).upper()
    repo_path = state.repo_path

    if tier_value == SandboxTier.B_DOCKER_CONTAINER.value:
        return DockerSandbox(repo_path, cpu_limit=2.0, memory_mb=4096)

    if tier_value == SandboxTier.C_FIRECRACKER_MICROVM.value:
        # Tier C currently uses the hardened Docker backend as a temporary
        # compatibility implementation. A real Firecracker backend remains a
        # separate infrastructure milestone and must not be implied by this
        # factory.
        return DockerSandbox(
            repo_path,
            cpu_limit=4.0,
            memory_mb=8192,
            read_only_root=True,
        )

    # Explicitly preserve Tier A semantics for development and Solo workflows.
    return LocalProcessSandbox(repo_path)


def production_sandbox_required() -> bool:
    return os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from loom.business.audit_log import AuditLogger
from loom.business.models import AuditAction, OrgTier
from loom.sandbox.base import BaseSandbox
from loom.sandbox.docker_sandbox import DockerSandbox
from loom.sandbox.local_process import LocalProcessSandbox


class SandboxTier(str, Enum):
    A_GIT_WORKTREE = "A"
    B_DOCKER_CONTAINER = "B"
    C_FIRECRACKER_MICROVM = "C"


class RunClassification(str, Enum):
    QUICK_FIX = "quick_fix"
    STANDARD = "standard"
    HIGH_RISK = "high_risk"


TIER_A_RESOURCE_LIMITS = {
    "cpu_cores": 1,
    "memory_mb": 2048,
    "timeout_minutes": 45,
}

TIER_B_RESOURCE_LIMITS = {
    "cpu_cores": 2,
    "memory_mb": 4096,
    "timeout_minutes": 45,
}

TIER_C_RESOURCE_LIMITS = {
    "cpu_cores": 4,
    "memory_mb": 8192,
    "timeout_minutes": 45,
}

TIER_RESOURCE_MAP: Dict[SandboxTier, Dict[str, int]] = {
    SandboxTier.A_GIT_WORKTREE: TIER_A_RESOURCE_LIMITS,
    SandboxTier.B_DOCKER_CONTAINER: TIER_B_RESOURCE_LIMITS,
    SandboxTier.C_FIRECRACKER_MICROVM: TIER_C_RESOURCE_LIMITS,
}

DEFAULT_EGRESS_ALLOWLIST: Set[str] = {
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "github.com",
    "gitlab.com",
    "proxy.golang.org",
    "crates.io",
    "static.crates.io",
    "repo1.maven.org",
    "plugins.gradle.org",
}


@dataclass
class SandboxContext:
    org_tier: OrgTier
    has_untrusted_native_deps: bool = False
    classification: RunClassification = RunClassification.STANDARD
    requires_dependency_install: bool = False
    repo_sensitivity_flag: bool = False
    patch_risk_high: bool = False
    touched_files: List[str] = field(default_factory=list)
    egress_allowlist: Optional[Set[str]] = None
    sandbox_tier: SandboxTier = SandboxTier.A_GIT_WORKTREE
    resource_limits: Dict[str, int] = field(default_factory=lambda: dict(TIER_A_RESOURCE_LIMITS))


@dataclass
class EgressViolation:
    target: str
    command: str
    tier: SandboxTier


class EgressEnforcer:
    def __init__(self, allowlist: Optional[Set[str]] = None, audit_logger: Optional[AuditLogger] = None):
        self.allowlist = allowlist or DEFAULT_EGRESS_ALLOWLIST.copy()
        self.violations: List[EgressViolation] = []
        self.audit_logger = audit_logger

    def check_egress(self, target: str, command: str, tier: SandboxTier) -> bool:
        target_normalized = target.lower().strip()
        for allowed in self.allowlist:
            if allowed in target_normalized:
                return True

        violation = EgressViolation(target=target, command=command, tier=tier)
        self.violations.append(violation)
        if self.audit_logger is not None:
            self.audit_logger.record(
                org_id="unknown",
                action=AuditAction.SANDBOX_EGRESS_BLOCKED,
                actor_id="sandbox_egress_enforcer",
                target=target,
                metadata={"command": command, "tier": tier.value},
            )
        return False

    def check_command_egress(self, command: str, tier: SandboxTier) -> List[str]:
        blocked: List[str] = []
        import re

        url_pattern = re.compile(r'https?://([^\s/"\'<>]+)')
        for match in url_pattern.finditer(command):
            target = match.group(1)
            if not self.check_egress(target, command, tier):
                blocked.append(target)
        return blocked

    @property
    def violation_count(self) -> int:
        return len(self.violations)


class SandboxTierSelector:
    def __init__(self, enforcer: Optional[EgressEnforcer] = None):
        self.enforcer = enforcer or EgressEnforcer()

    def select_tier(self, ctx: SandboxContext) -> SandboxTier:
        if not ctx.has_untrusted_native_deps and ctx.classification == RunClassification.QUICK_FIX:
            return SandboxTier.A_GIT_WORKTREE

        if ctx.org_tier in (OrgTier.TEAM, OrgTier.ENTERPRISE) and ctx.requires_dependency_install:
            return SandboxTier.B_DOCKER_CONTAINER

        if ctx.org_tier == OrgTier.ENTERPRISE and (ctx.repo_sensitivity_flag or ctx.patch_risk_high):
            return SandboxTier.C_FIRECRACKER_MICROVM

        if ctx.org_tier in (OrgTier.TEAM, OrgTier.ENTERPRISE):
            return SandboxTier.B_DOCKER_CONTAINER

        return SandboxTier.A_GIT_WORKTREE

    def select_with_resources(self, ctx: SandboxContext) -> SandboxContext:
        tier = self.select_tier(ctx)
        ctx.sandbox_tier = tier
        ctx.resource_limits = dict(TIER_RESOURCE_MAP.get(tier, TIER_A_RESOURCE_LIMITS))

        if ctx.egress_allowlist is None:
            ctx.egress_allowlist = DEFAULT_EGRESS_ALLOWLIST.copy()

        return ctx

    def create_sandbox(self, ctx: SandboxContext, repo_path: str) -> BaseSandbox:
        tier = ctx.sandbox_tier
        if tier == SandboxTier.A_GIT_WORKTREE:
            return LocalProcessSandbox(repo_path)
        if tier == SandboxTier.B_DOCKER_CONTAINER:
            cpu = float(ctx.resource_limits.get("cpu_cores", 2))
            mem = int(ctx.resource_limits.get("memory_mb", 4096))
            return DockerSandbox(repo_path, cpu_limit=cpu, memory_mb=mem)
        if tier == SandboxTier.C_FIRECRACKER_MICROVM:
            cpu = float(ctx.resource_limits.get("cpu_cores", 4))
            mem = int(ctx.resource_limits.get("memory_mb", 8192))
            return DockerSandbox(repo_path, cpu_limit=cpu, memory_mb=mem, read_only_root=True)
        return LocalProcessSandbox(repo_path)

    def enforce_egress_policy(
        self,
        command: str,
        ctx: SandboxContext,
        on_violation: Optional[Callable[[EgressViolation], None]] = None,
    ) -> bool:
        blocked = self.enforcer.check_command_egress(command, ctx.sandbox_tier)
        if blocked:
            for target in blocked:
                violation = EgressViolation(
                    target=target,
                    command=command,
                    tier=ctx.sandbox_tier,
                )
                if on_violation:
                    on_violation(violation)
            return False
        return True

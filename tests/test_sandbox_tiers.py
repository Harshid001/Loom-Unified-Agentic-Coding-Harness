from loom.business.audit_log import AuditLogger
from loom.business.models import AuditAction, OrgTier
from loom.sandbox.tiers import EgressEnforcer, RunClassification, SandboxContext, SandboxTier, SandboxTierSelector


def test_team_dependency_install_returns_tier_b():
    ctx = SandboxContext(org_tier=OrgTier.TEAM, requires_dependency_install=True)
    assert SandboxTierSelector().select_tier(ctx) == SandboxTier.B_FIRECRACKER_MICROVM


def test_enterprise_sensitive_returns_tier_c():
    ctx = SandboxContext(org_tier=OrgTier.ENTERPRISE, repo_sensitivity_flag=True)
    assert SandboxTierSelector().select_tier(ctx) == SandboxTier.C_FIRECRACKER_MICROVM


def test_enterprise_standard_returns_tier_b():
    ctx = SandboxContext(org_tier=OrgTier.ENTERPRISE)
    assert SandboxTierSelector().select_tier(ctx) == SandboxTier.B_FIRECRACKER_MICROVM


def test_quick_fix_stays_tier_a():
    ctx = SandboxContext(org_tier=OrgTier.TEAM, classification=RunClassification.QUICK_FIX)
    assert SandboxTierSelector().select_tier(ctx) == SandboxTier.A_GIT_WORKTREE


def test_select_with_resources_for_tier_b():
    ctx = SandboxContext(org_tier=OrgTier.TEAM, requires_dependency_install=True)
    result = SandboxTierSelector().select_with_resources(ctx)
    assert result.sandbox_tier == SandboxTier.B_FIRECRACKER_MICROVM
    assert result.resource_limits["cpu_cores"] == 2
    assert result.resource_limits["memory_mb"] == 4096


def test_egress_allowlist_blocks_unknown_domain():
    enforcer = EgressEnforcer()
    assert enforcer.check_egress("pypi.org", "pip install", SandboxTier.B_FIRECRACKER_MICROVM)
    assert not enforcer.check_egress("evil.example", "curl", SandboxTier.B_FIRECRACKER_MICROVM)
    assert enforcer.violation_count == 1


def test_blocked_egress_is_audited(tmp_path):
    audit = AuditLogger(storage_dir=str(tmp_path))
    enforcer = EgressEnforcer(audit_logger=audit)
    assert not enforcer.check_egress("evil.example", "curl", SandboxTier.B_FIRECRACKER_MICROVM)
    entries = audit.get_entries(org_id="unknown", action=AuditAction.SANDBOX_EGRESS_BLOCKED)
    assert len(entries) == 1
    assert entries[0].metadata["tier"] == "B"

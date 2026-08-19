import logging
from typing import Dict, List, Optional

from loom.business.models import (
    TIER_FEATURE_MATRIX,
    TIER_QUOTA_MAP,
    FeatureKey,
    HardStopPolicy,
    Membership,
    MembershipRole,
    Organization,
    OrgTier,
    OrgUsageSnapshot,
    Quota,
)

logger = logging.getLogger("loom.business.entitlements")


class EntitlementCheckResult:
    def __init__(self, allowed: bool, reason: Optional[str] = None):
        self.allowed = allowed
        self.reason = reason

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"EntitlementCheckResult(allowed={self.allowed}, reason={self.reason!r})"


class EntitlementService:
    def __init__(self, org_store: Optional[Dict[str, Organization]] = None):
        self._orgs: Dict[str, Organization] = org_store or {}
        self._memberships: Dict[str, Dict[str, Membership]] = {}

    def register_org(self, org: Organization) -> None:
        self._orgs[org.id] = org

    def get_org(self, org_id: str) -> Optional[Organization]:
        return self._orgs.get(org_id)

    def check(self, org_id: str, feature_key: FeatureKey) -> EntitlementCheckResult:
        org = self._orgs.get(org_id)
        if org is None:
            return EntitlementCheckResult(False, f"Organization {org_id} not found")

        tier_features = TIER_FEATURE_MATRIX.get(org.tier, {})
        allowed = tier_features.get(feature_key, False)

        if allowed:
            return EntitlementCheckResult(True)

        return EntitlementCheckResult(
            False,
            f"Feature '{feature_key.value}' requires {self._required_tier_for_feature(feature_key)} tier, "
            f"current tier is {org.tier.value}",
        )

    def get_quota(self, org_id: str) -> Quota:
        org = self._orgs.get(org_id)
        if org is None:
            return Quota(org_id=org_id, runs_per_month=0)
        return TIER_QUOTA_MAP.get(org.tier, TIER_QUOTA_MAP[OrgTier.SOLO])

    def list_org_ids(self) -> List[str]:
        return list(self._orgs.keys())

    def quota_usage_percent(self, org_id: str, snapshot: OrgUsageSnapshot) -> float:
        quota = self.get_quota(org_id)
        runs_pct = (snapshot.runs_consumed / quota.runs_per_month) * 100 if quota.runs_per_month > 0 else 100
        tokens_pct = (
            (snapshot.tokens_consumed / (quota.runs_per_month * quota.tokens_per_run)) * 100
            if quota.runs_per_month > 0
            else 100
        )
        sandbox_ms_quota = quota.sandbox_minutes_per_run * 60_000 * quota.runs_per_month
        sandbox_pct = (snapshot.sandbox_ms_consumed / sandbox_ms_quota) * 100 if sandbox_ms_quota > 0 else 100
        return max(runs_pct, tokens_pct, sandbox_pct)

    def evaluate_quota(
        self,
        org_id: str,
        snapshot: OrgUsageSnapshot,
    ) -> tuple[bool, str]:
        org = self._orgs.get(org_id)
        if org is None:
            return False, "Organization not found"

        quota = self.get_quota(org_id)

        runs_pct = (snapshot.runs_consumed / quota.runs_per_month) * 100 if quota.runs_per_month > 0 else 100
        tokens_pct = (
            (snapshot.tokens_consumed / (quota.runs_per_month * quota.tokens_per_run)) * 100
            if quota.runs_per_month > 0
            else 100
        )
        sandbox_ms_quota = quota.sandbox_minutes_per_run * 60_000 * quota.runs_per_month
        sandbox_pct = (snapshot.sandbox_ms_consumed / sandbox_ms_quota) * 100 if sandbox_ms_quota > 0 else 100

        max_pct = max(runs_pct, tokens_pct, sandbox_pct)

        if runs_pct >= 80 or tokens_pct >= 80 or sandbox_pct >= 80:
            if runs_pct >= 100 or tokens_pct >= 100 or sandbox_pct >= 100:
                if org.hard_stop_policy == HardStopPolicy.BLOCK:
                    return False, (
                        f"Quota exhausted: runs={runs_pct:.0f}%, tokens={tokens_pct:.0f}%, "
                        f"sandbox={sandbox_pct:.0f}%"
                    )
                elif org.hard_stop_policy == HardStopPolicy.ALLOW_WITH_OVERAGE_BILLING:
                    burst_limit = 100 + org.burst_grace_pct
                    if runs_pct >= burst_limit or tokens_pct >= burst_limit or sandbox_pct >= burst_limit:
                        return False, f"Burst grace exhausted: {burst_limit:.0f}% limit exceeded"
                    return True, f"Over quota but within burst grace ({org.burst_grace_pct}% allowed)"
                elif org.hard_stop_policy == HardStopPolicy.REQUIRE_ADMIN_APPROVAL:
                    return False, "Admin approval required — quota exhausted"
            else:
                return True, f"Soft warning: {max_pct:.0f}% of quota consumed"

        return True, "Within quota"

    def add_membership(self, membership: Membership) -> None:
        if membership.org_id not in self._memberships:
            self._memberships[membership.org_id] = {}
        self._memberships[membership.org_id][membership.user_id] = membership

    def remove_membership(self, org_id: str, user_id: str) -> None:
        if org_id in self._memberships:
            self._memberships[org_id].pop(user_id, None)

    def memberships_dict(self) -> Dict[str, Dict[str, Membership]]:
        return self._memberships

    def get_membership(self, org_id: str, user_id: str) -> Optional[Membership]:
        return self._memberships.get(org_id, {}).get(user_id)

    def get_role(self, org_id: str, user_id: str) -> MembershipRole:
        """Resolve role for the given identity.

        Uses the explicit parameters for membership lookup so that callers
        (e.g. require_run_access) can resolve the authenticated principal's
        role regardless of the runtime security mode.  Falls back to the
        effective principal only when no user_id is supplied.
        """
        membership = self._memberships.get(org_id, {}).get(user_id)
        if membership is None:
            return MembershipRole.DEVELOPER
        return membership.role

    def _required_tier_for_feature(self, feature_key: FeatureKey) -> OrgTier:
        for tier in [OrgTier.SELF_HOSTED, OrgTier.ENTERPRISE, OrgTier.TEAM, OrgTier.SOLO]:
            if TIER_FEATURE_MATRIX.get(tier, {}).get(feature_key, False):
                return tier
        return OrgTier.ENTERPRISE

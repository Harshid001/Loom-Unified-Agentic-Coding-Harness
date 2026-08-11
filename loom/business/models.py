import hashlib
import time
import uuid
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class OrgTier(str, Enum):
    SOLO = "solo"
    TEAM = "team"
    ENTERPRISE = "enterprise"

class HardStopPolicy(str, Enum):
    BLOCK = "block"
    ALLOW_WITH_OVERAGE_BILLING = "allow_with_overage_billing"
    REQUIRE_ADMIN_APPROVAL = "require_admin_approval"

class MembershipRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    BILLING_ADMIN = "billing_admin"
    AUDITOR = "auditor"

class Organization(BaseModel):
    id: str = Field(default_factory=lambda: f"org_{uuid.uuid4().hex[:12]}")
    name: str
    tier: OrgTier = OrgTier.SOLO
    hard_stop_policy: HardStopPolicy = HardStopPolicy.BLOCK
    data_residency_region: str = "us-east-1"
    auto_merge_threshold: float = 0.95
    burst_grace_pct: float = 20.0
    burst_grace_hours: int = 48
    post_merge_monitor_timeout_seconds: int = 3600
    router_weights: Dict[str, float] = Field(default_factory=lambda: {
        "w1_cost": 0.25,
        "w2_latency": 0.15,
        "w3_success_rate": 0.35,
        "w4_capability": 0.25,
    })
    sensitive_path_globs: List[str] = Field(default_factory=lambda: [
        "**/auth/**",
        "**/billing/**",
        "**/migrations/**",
    ])
    created_at: float = Field(default_factory=time.time)

class Membership(BaseModel):
    user_id: str
    org_id: str
    role: MembershipRole = MembershipRole.DEVELOPER
    joined_at: float = Field(default_factory=time.time)

class Quota(BaseModel):
    org_id: str
    runs_per_month: int = 50
    tokens_per_run: int = 400_000
    sandbox_minutes_per_run: int = 45
    repos_connected: int = 1
    seats: int = 1
    overage_token_margin_pct: float = 15.0

class OrgUsageSnapshot(BaseModel):
    org_id: str
    month_start: str
    runs_consumed: int = 0
    tokens_consumed: int = 0
    sandbox_ms_consumed: int = 0
    cost_usd_accrued: float = 0.0
    snapshot_at: float = Field(default_factory=time.time)

class FeatureKey(str, Enum):
    SANDBOX_TIER_B_CONTAINER = "sandbox.tier_b_container"
    SANDBOX_TIER_C_MICROVM = "sandbox.tier_c_microvm"
    MEMORY_TEAM_SYNC = "memory.team_sync"
    ROUTER_CONSENSUS_VERIFICATION = "router.consensus_verification"
    GOVERNANCE_SSO_SCIM = "governance.sso_scim"
    GOVERNANCE_SOC2_AUDIT_EXPORT = "governance.soc2_audit_export"
    INTEGRATIONS_CI_BOT = "integrations.ci_bot"
    INTEGRATIONS_IDE_PLUGINS = "integrations.ide_plugins"

TIER_FEATURE_MATRIX: Dict[OrgTier, Dict[FeatureKey, bool]] = {
    OrgTier.SOLO: {
        FeatureKey.SANDBOX_TIER_B_CONTAINER: False,
        FeatureKey.SANDBOX_TIER_C_MICROVM: False,
        FeatureKey.MEMORY_TEAM_SYNC: False,
        FeatureKey.ROUTER_CONSENSUS_VERIFICATION: False,
        FeatureKey.GOVERNANCE_SSO_SCIM: False,
        FeatureKey.GOVERNANCE_SOC2_AUDIT_EXPORT: False,
        FeatureKey.INTEGRATIONS_CI_BOT: False,
        FeatureKey.INTEGRATIONS_IDE_PLUGINS: True,
    },
    OrgTier.TEAM: {
        FeatureKey.SANDBOX_TIER_B_CONTAINER: True,
        FeatureKey.SANDBOX_TIER_C_MICROVM: False,
        FeatureKey.MEMORY_TEAM_SYNC: True,
        FeatureKey.ROUTER_CONSENSUS_VERIFICATION: False,
        FeatureKey.GOVERNANCE_SSO_SCIM: False,
        FeatureKey.GOVERNANCE_SOC2_AUDIT_EXPORT: False,
        FeatureKey.INTEGRATIONS_CI_BOT: True,
        FeatureKey.INTEGRATIONS_IDE_PLUGINS: True,
    },
    OrgTier.ENTERPRISE: {
        FeatureKey.SANDBOX_TIER_B_CONTAINER: True,
        FeatureKey.SANDBOX_TIER_C_MICROVM: True,
        FeatureKey.MEMORY_TEAM_SYNC: True,
        FeatureKey.ROUTER_CONSENSUS_VERIFICATION: True,
        FeatureKey.GOVERNANCE_SSO_SCIM: True,
        FeatureKey.GOVERNANCE_SOC2_AUDIT_EXPORT: True,
        FeatureKey.INTEGRATIONS_CI_BOT: True,
        FeatureKey.INTEGRATIONS_IDE_PLUGINS: True,
    },
}

TIER_QUOTA_MAP: Dict[OrgTier, Quota] = {
    OrgTier.SOLO: Quota(org_id="", runs_per_month=50, repos_connected=1, seats=1),
    OrgTier.TEAM: Quota(org_id="", runs_per_month=500, repos_connected=20, seats=15),
    OrgTier.ENTERPRISE: Quota(org_id="", runs_per_month=10_000, repos_connected=100, seats=500),
}


class UsageEvent(BaseModel):
    run_id: str
    org_id: str
    step_id: str
    attempt_number: int
    tokens_in: int = 0
    tokens_out: int = 0
    model_id: str = "unknown"
    sandbox_tier: str = "A"
    wall_clock_ms: int = 0
    cost_usd: float = 0.0
    input_context_hash: str = ""

    @property
    def dedup_key(self) -> str:
        raw = f"{self.run_id}|{self.step_id}|{self.attempt_number}|{self.input_context_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()


class UsageLedgerEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"ledge_{uuid.uuid4().hex[:12]}")
    dedup_key: str
    org_id: str
    run_id: str
    step_id: str
    attempt_number: int
    tokens_in: int
    tokens_out: int
    model_id: str
    sandbox_tier: str
    wall_clock_ms: int
    cost_usd: float
    billed_flag: bool = False
    recorded_at: float = Field(default_factory=time.time)


class AuditAction(str, Enum):
    RUN_TRIGGERED = "run.triggered"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_ROLLED_BACK = "run.rolled_back"
    ENTITLEMENT_CHECK = "entitlement.check"
    ENTITLEMENT_DENIED = "entitlement.denied"
    QUOTA_SOFT_WARN = "quota.soft_warn"
    QUOTA_EXCEEDED = "quota.exceeded"
    MEMBER_INVITED = "member.invited"
    MEMBER_REMOVED = "member.removed"
    MEMBER_DEPROVISIONED = "member.deprovisioned"
    EVIDENCE_EXPORTED = "evidence.exported"
    SANDBOX_EGRESS_BLOCKED = "sandbox.egress_blocked"
    CONFIG_CHANGED = "config.changed"


class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"audit_{uuid.uuid4().hex[:16]}")
    org_id: str
    actor_id: str
    action: AuditAction
    target: str = ""
    ip: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)

import httpx
import pytest

from loom.api.webhooks import WebhookEngine, WebhookEventType, WebhookSubscription
from loom.business.audit_log import AuditLogger
from loom.business.entitlements import EntitlementService
from loom.business.models import AuditAction, Organization, OrgTier, UsageEvent
from loom.business.rollup import UsageRollupJob
from loom.business.usage_ledger import UsageLedger


class FakeAsyncClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, content=None, headers=None, timeout=None):
        self.calls.append({"url": url, "content": content, "headers": headers})
        return httpx.Response(200, text="ok")

    async def aclose(self):
        pass


def _ledger_with_runs(tmp_path, org_id: str, run_count: int) -> UsageLedger:
    ledger = UsageLedger(storage_dir=str(tmp_path / "ledger"))
    for i in range(run_count):
        ledger.record(
            UsageEvent(
                run_id=f"run_{i:04d}",
                org_id=org_id,
                step_id="step_onboarding",
                attempt_number=1,
                tokens_in=100,
                tokens_out=100,
                cost_usd=0.01,
                input_context_hash=f"ctx_{i}",
            )
        )
    return ledger


def _rollup_job(tmp_path, ledger: UsageLedger, org: Organization) -> UsageRollupJob:
    svc = EntitlementService()
    svc.register_org(org)

    engine = WebhookEngine(storage_dir=str(tmp_path / "webhooks"))
    engine._http = FakeAsyncClient()
    engine.register(
        WebhookSubscription(
            id="sub_quota",
            org_id=org.id,
            url="https://example.com/hook",
            events={WebhookEventType.USAGE_QUOTA_WARNING, WebhookEventType.USAGE_QUOTA_EXCEEDED},
            max_retries=1,
            retry_backoff_base_seconds=0.01,
        )
    )

    audit = AuditLogger(storage_dir=str(tmp_path / "audit"))
    return UsageRollupJob(
        entitlements=svc,
        ledger=ledger,
        webhooks=engine,
        audit_logger=audit,
        storage_dir=str(tmp_path / "rollup"),
    )


@pytest.mark.asyncio
async def test_rollup_soft_warns_at_80_percent(tmp_path):
    org = Organization(name="Solo", tier=OrgTier.SOLO)
    ledger = _ledger_with_runs(tmp_path, org.id, 40)
    job = _rollup_job(tmp_path, ledger, org)

    outcomes = await job.run_once()
    assert len(outcomes) == 1
    assert outcomes[0].quota_pct == 80.0
    assert "soft_warn" in outcomes[0].actions

    audit = AuditLogger(storage_dir=str(tmp_path / "audit"))
    assert len(audit.get_entries(org_id=org.id, action=AuditAction.QUOTA_SOFT_WARN)) == 1


@pytest.mark.asyncio
async def test_rollup_emits_exceeded_at_100_percent(tmp_path):
    org = Organization(name="Solo", tier=OrgTier.SOLO)
    ledger = _ledger_with_runs(tmp_path, org.id, 50)
    job = _rollup_job(tmp_path, ledger, org)

    outcomes = await job.run_once()
    assert len(outcomes) == 1
    assert "soft_warn" in outcomes[0].actions
    assert "quota_exceeded" in outcomes[0].actions
    assert outcomes[0].allowed is False

    audit = AuditLogger(storage_dir=str(tmp_path / "audit"))
    assert len(audit.get_entries(org_id=org.id, action=AuditAction.QUOTA_SOFT_WARN)) == 1
    assert len(audit.get_entries(org_id=org.id, action=AuditAction.QUOTA_EXCEEDED)) == 1


@pytest.mark.asyncio
async def test_rollup_replay_is_idempotent(tmp_path):
    org = Organization(name="Solo", tier=OrgTier.SOLO)
    ledger = _ledger_with_runs(tmp_path, org.id, 50)
    job = _rollup_job(tmp_path, ledger, org)

    first = await job.run_once()
    second = await job.run_once()

    assert len(second) == 1
    assert second[0].actions == []
    for key in ["soft_warn", "quota_exceeded"]:
        assert first[0].actions.count(key) == 1

    audit = AuditLogger(storage_dir=str(tmp_path / "audit"))
    assert len(audit.get_entries(org_id=org.id, action=AuditAction.QUOTA_EXCEEDED)) == 1

    deliverable_files = list((tmp_path / "webhooks" / "webhook_deliveries").glob("*.json"))
    assert len(deliverable_files) == 2


@pytest.mark.asyncio
async def test_rollup_skips_orgs_without_usage(tmp_path):
    org = Organization(name="Solo", tier=OrgTier.SOLO)
    ledger = UsageLedger(storage_dir=str(tmp_path / "ledger"))
    job = _rollup_job(tmp_path, ledger, org)

    outcomes = await job.run_once()
    assert outcomes == []


@pytest.mark.asyncio
async def test_rollup_within_quota_no_events(tmp_path):
    org = Organization(name="Solo", tier=OrgTier.SOLO)
    ledger = _ledger_with_runs(tmp_path, org.id, 10)
    job = _rollup_job(tmp_path, ledger, org)

    outcomes = await job.run_once()
    assert len(outcomes) == 1
    assert outcomes[0].actions == []
    assert outcomes[0].allowed is True

    audit = AuditLogger(storage_dir=str(tmp_path / "audit"))
    assert audit.count() == 0

from pathlib import Path

import pytest

from loom.business.billing_provider import (
    BillingEvent,
    BillingProviderError,
    apply_billing_event,
    settle_pending_plan_change,
)
from loom.business.models import BillingStatus, Organization, OrgTier
from loom.control_plane.tokens import TokenPrincipal, _check_admin
from loom.memory.vector_sync import MemoryRecord, merge_records
from loom.runtime.run_state_store import (
    InvalidRunTransition,
    RunState,
    RunStateRecord,
    heartbeat,
    transition,
)
from loom.sandbox.firecracker_sandbox import FirecrackerSandbox


def test_run_state_transitions_and_version_guard():
    record = RunStateRecord(run_id="r1", org_id="org1")
    transition(record, RunState.RUNNING, expected_version=0)
    assert record.version == 1
    with pytest.raises(InvalidRunTransition):
        transition(record, RunState.RUNNING, expected_version=0)
    heartbeat(record, "worker-1")
    assert record.worker_id == "worker-1"


def test_cross_org_memory_merge_is_rejected():
    local = [MemoryRecord.make("m1", "org1", "a", 1)]
    remote = [MemoryRecord.make("m1", "org2", "b", 2)]
    with pytest.raises(ValueError, match="cross-organization"):
        merge_records(local, remote)


def test_billing_payment_failure_enters_grace_and_plan_can_settle():
    org = Organization(id="org1", name="Acme", tier=OrgTier.TEAM)
    event = BillingEvent("evt1", "invoice.payment_failed", "org1", 100.0, {})
    apply_billing_event(org, event)
    assert org.billing_status == BillingStatus.GRACE
    org.pending_tier = OrgTier.SOLO
    org.pending_tier_effective_at = 200.0
    assert settle_pending_plan_change(org, 199.0) is False
    assert settle_pending_plan_change(org, 200.0) is True
    assert org.tier == OrgTier.SOLO


def test_billing_event_cannot_cross_org():
    org = Organization(id="org1", name="Acme")
    event = BillingEvent("evt1", "invoice.paid", "org2", 100.0, {})
    with pytest.raises(BillingProviderError):
        apply_billing_event(org, event)


def test_control_plane_admin_guard():
    with pytest.raises(PermissionError):
        _check_admin(TokenPrincipal(user_id="u", org_id="o", is_admin=False))


def test_firecracker_fails_closed_without_worker(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_SOCKET", raising=False)
    monkeypatch.delenv("LOOM_FIRECRACKER_WORKER_CMD", raising=False)
    result = FirecrackerSandbox(str(tmp_path)).run_command(["python", "-c", "print(1)"])
    assert result.exit_code == 125

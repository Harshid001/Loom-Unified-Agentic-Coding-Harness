from loom.business.models import OrgTier, UsageEvent
from loom.business.usage_ledger import UsageLedger


def _event(run_id: str, step_id: str = "verifier") -> UsageEvent:
    return UsageEvent(
        run_id=run_id,
        org_id="org_restart",
        step_id=step_id,
        attempt_number=1,
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.12,
        input_context_hash=f"ctx-{run_id}-{step_id}",
    )


def test_usage_ledger_restores_entries_and_dedup_keys(tmp_path):
    first = UsageLedger(storage_dir=str(tmp_path))
    entry = first.record(_event("run_restart"))
    assert entry is not None

    restarted = UsageLedger(storage_dir=str(tmp_path))
    snapshot = restarted.build_snapshot("org_restart", OrgTier.TEAM)

    assert snapshot.runs_consumed == 1
    assert snapshot.tokens_consumed == 150
    assert snapshot.cost_usd_accrued == 0.12
    assert restarted.get_dedup_key_count() == 1
    assert restarted.record(_event("run_restart")) is None

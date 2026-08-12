import time
from datetime import date

import pytest

from loom.business.billing import (
    RUN_CREDIT_MAX_SANDBOX_SECONDS,
    RUN_CREDIT_MAX_TOKENS,
    build_invoice,
    credits_for_ledger_entries,
    credits_for_run,
    org_quota_runs,
    overage_run_cap,
    plan_change_effective_date,
    prorated_credit_for_plan_change,
    tier_after_payment_grace,
    token_overage_cost_usd,
)
from loom.business.models import (
    Organization,
    OrgTier,
    OrgUsageSnapshot,
    UsageEvent,
    UsageLedgerEntry,
)

SOLO = Organization(id="org_solo", name="Solo Org", tier=OrgTier.SOLO)
TEAM = Organization(id="org_team", name="Team Org", tier=OrgTier.TEAM)


def _event(run_id, step="step_a", attempt=1, tokens_in=100, tokens_out=100, wall_ms=60_000):
    return UsageEvent(
        run_id=run_id,
        org_id="org_solo",
        step_id=step,
        attempt_number=attempt,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        wall_clock_ms=wall_ms,
        input_context_hash=f"ctx_{run_id}_{step}_{attempt}",
    )


def _entry(run_id, step="step_a", attempt=1, tokens_in=100, tokens_out=100, wall_ms=60_000):
    return UsageLedgerEntry(
        dedup_key=f"dk_{run_id}_{step}_{attempt}",
        org_id="org_solo",
        run_id=run_id,
        step_id=step,
        attempt_number=attempt,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model_id="test-model",
        sandbox_tier="A",
        wall_clock_ms=wall_ms,
        cost_usd=0.01,
    )


def _snapshot(runs=0, tokens=0, cost=0.0) -> OrgUsageSnapshot:
    return OrgUsageSnapshot(org_id="org_solo", month_start="2026-01-01", runs_consumed=runs, tokens_consumed=tokens, cost_usd_accrued=cost)


class TestRunCredits:
    def test_baseline_run_is_one_credit(self):
        assert credits_for_run([_event("r1")]) == 1

    def test_retry_blowout_adds_credit(self):
        events = [_event("r1", attempt=1), _event("r1", attempt=2), _event("r1", attempt=3), _event("r1", attempt=4)]
        assert credits_for_run(events) == 2

    def test_retries_within_envelope_are_free(self):
        events = [_event("r1", attempt=1), _event("r1", attempt=2), _event("r1", attempt=3)]
        assert credits_for_run(events) == 1

    def test_token_blocks_add_credits(self):
        tokens = RUN_CREDIT_MAX_TOKENS * 3
        assert credits_for_run([_event("r1", tokens_in=tokens)]) == 1 + 3

    def test_sandbox_blocks_add_credits(self):
        wall_ms = RUN_CREDIT_MAX_SANDBOX_SECONDS * 1000 * 2
        assert credits_for_run([_event("r1", wall_ms=wall_ms)]) == 1 + 2

    def test_ledger_entries_grouped_by_run(self):
        entries = [
            _entry("r_a", step="s1"),
            _entry("r_a", step="s2"),
            _entry("r_b", step="s1", tokens_in=800_000),
        ]
        assert credits_for_ledger_entries(entries) == {"r_a": 1, "r_b": 3}


class TestInvoices:
    def test_solo_within_quota_is_included_only(self):
        invoice = build_invoice(SOLO, _snapshot(runs=10, tokens=1_000_000, cost=2.0))
        assert invoice["total_usd"] == 0.0
        assert invoice["overage_run_credits"] == 0
        assert invoice["hard_stop_exceeded"] is False
        assert [item["label"] for item in invoice["lines"]] == ["included_run_credits"]

    def test_overage_credits_billed_at_overage_price(self):
        entries = [_entry(f"r_{i:03d}") for i in range(120)]
        invoice = build_invoice(SOLO, _snapshot(runs=120), ledger_entries=entries)
        included = org_quota_runs(SOLO)
        assert invoice["included_run_credits"] == included
        assert invoice["overage_run_credits"] == 120 - included
        cap = overage_run_cap(SOLO)
        assert invoice["overage_cap_run_credits"] == cap - included
        assert invoice["hard_stop_exceeded"] is True
        overage_line = [item for item in invoice["lines"] if item["label"] == "overage_run_credits"][0]
        assert overage_line["quantity"] == cap - included
        assert invoice["total_usd"] == (cap - included) * 0.80

    def test_token_margin_line_only_when_tokens_exceed_quota(self):
        quota_tokens = org_quota_runs(SOLO) * 400_000
        invoice = build_invoice(
            SOLO,
            _snapshot(runs=60, tokens=quota_tokens + 250_000, cost=100.0),
            ledger_entries=[_entry("r_001")],
        )
        labels = {item["label"] for item in invoice["lines"]}
        assert "token_margin_15pct" in labels
        assert invoice["total_usd"] == 15.0

    def test_no_token_margin_within_token_quota(self):
        invoice = build_invoice(SOLO, _snapshot(runs=10, tokens=100_000, cost=50.0))
        labels = {item["label"] for item in invoice["lines"]}
        assert "token_margin_15pct" not in labels
        assert invoice["total_usd"] == 0.0


class TestPlanChanges:
    def test_prorated_credit_mix(self):
        assert prorated_credit_for_plan_change(old_included_credits=50, new_included_credits=500, days_elapsed=10, days_in_cycle=30) == (50 * 10 + 500 * 20) // 30

    def test_prorated_credit_clamps_elapsed(self):
        assert prorated_credit_for_plan_change(50, 500, days_elapsed=99, days_in_cycle=30) == (50 * 30) // 30

    def test_prorated_credit_rejects_bad_cycle(self):
        with pytest.raises(ValueError):
            prorated_credit_for_plan_change(50, 500, days_elapsed=10, days_in_cycle=0)

    def test_upgrade_applies_immediately(self):
        from datetime import date

        assert plan_change_effective_date("upgrade", date(2026, 1, 15), date(2026, 2, 1)) == date(2026, 1, 15)

    def test_downgrade_waits_for_cycle_boundary(self):
        from datetime import date

        assert plan_change_effective_date("downgrade", date(2026, 1, 15), date(2026, 2, 1)) == date(2026, 2, 1)

    def test_downgrade_past_boundary_moves_to_next(self):
        from datetime import date

        assert plan_change_effective_date("downgrade", date(2026, 2, 1), date(2026, 2, 1)) == date(2026, 3, 3)


class TestPaymentGrace:
    def test_no_failed_payment_keeps_tier(self):
        assert tier_after_payment_grace(SOLO) == OrgTier.SOLO

    def test_within_grace_keeps_tier(self):
        from datetime import date

        org = SOLO.model_copy(update={"last_payment_failed_at": time.time() - 2 * 86400})
        assert tier_after_payment_grace(org, now=date.today()) == OrgTier.SOLO

    def test_grace_expired_downgrades_to_solo(self):
        org = TEAM.model_copy(update={"last_payment_failed_at": time.time() - 10 * 86400})
        assert tier_after_payment_grace(org, now=date.today()) == OrgTier.SOLO

    def test_token_overage_margin(self):
        assert token_overage_cost_usd(1.0) == 1.15

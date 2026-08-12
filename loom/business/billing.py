"""Metered billing internals for the Run Credit economy (spec §1.3).

All Stripe-facing work is downstream of this module; everything here is
pure, deterministic logic over the UsageLedger so it can be unit-tested
without external services. The pricing contract:

- One Run Credit = one DAG execution up to 8 agent-steps (≤2 self-healing
  retries per step), 400K tokens, and 45 minutes of sandbox wall-clock.
- Token overage within a run is billed at provider-passthrough cost + 15% margin.
- Run-count overage is capped by an org-configurable hard stop (default 2x included quota).
- Upgrades apply immediately with prorated credit for unused days of the
  prior plan; downgrades apply at the next billing cycle boundary.
- Failed payment → 7-day grace period at the current tier → auto-downgrade to Solo.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional

from loom.business.models import (
    Organization,
    OrgTier,
    OrgUsageSnapshot,
    UsageEvent,
    UsageLedgerEntry,
)

RUN_CREDIT_MAX_AGENT_STEPS = 8
RUN_CREDIT_MAX_RETRIES_PER_STEP = 2
RUN_CREDIT_MAX_TOKENS = 400_000
RUN_CREDIT_MAX_SANDBOX_SECONDS = 45 * 60
TOKEN_OVERAGE_MARGIN_PCT = 0.15
DEFAULT_OVERAGE_RUN_CAP_MULTIPLIER = 2.0
PAYMENT_GRACE_DAYS = 7

TEAM_OVERAGE_RUN_PRICE_USD = 0.80
SOLO_DOWNGRADE_TIER = OrgTier.SOLO


def _run_tokens(events: List[UsageEvent]) -> int:
    return sum(e.tokens_in + e.tokens_out for e in events)


def _run_sandbox_seconds(events: List[UsageEvent]) -> int:
    return sum(e.wall_clock_ms for e in events) // 1000


def _run_max_retries_exceeded(events: List[UsageEvent]) -> bool:
    attempts: Dict[str, int] = {}
    for e in events:
        attempts[e.step_id] = max(attempts.get(e.step_id, 0), e.attempt_number)
    return any(a > 1 + RUN_CREDIT_MAX_RETRIES_PER_STEP for a in attempts.values())


def credits_for_run(events: List[UsageEvent]) -> int:
    """Run Credits consumed by one DAG execution (spec §1.3 unit of sale).

    Base cost is 1 credit; an additional credit is consumed for each
    dimension that exceeds the Run Credit envelope (retry blowout, token
    blocks, sandbox-minute blocks). Deterministic heuristic, documented for
    the nightly billing sync.
    """
    credits = 1
    if _run_max_retries_exceeded(events):
        credits += 1
    tokens = _run_tokens(events)
    if tokens > RUN_CREDIT_MAX_TOKENS:
        credits += tokens // RUN_CREDIT_MAX_TOKENS
    sandbox_seconds = _run_sandbox_seconds(events)
    if sandbox_seconds > RUN_CREDIT_MAX_SANDBOX_SECONDS:
        credits += sandbox_seconds // RUN_CREDIT_MAX_SANDBOX_SECONDS
    return credits


def credits_for_ledger_entries(entries: List[UsageLedgerEntry]) -> Dict[str, int]:
    """Map run_id → credits consumed, from raw ledger rows."""
    runs: Dict[str, List[UsageEvent]] = {}
    for entry in entries:
        runs.setdefault(entry.run_id, []).append(
            UsageEvent(
                run_id=entry.run_id,
                org_id=entry.org_id,
                step_id=entry.step_id,
                attempt_number=entry.attempt_number,
                tokens_in=entry.tokens_in,
                tokens_out=entry.tokens_out,
                model_id=entry.model_id,
                sandbox_tier=entry.sandbox_tier,
                wall_clock_ms=entry.wall_clock_ms,
                cost_usd=entry.cost_usd,
            )
        )
    return {run_id: credits_for_run(events) for run_id, events in runs.items()}


def token_overage_cost_usd(provider_cost_usd: float) -> float:
    """Provider-passthrough cost + 15% margin (spec §1.3 overage rules)."""
    return round(provider_cost_usd * (1.0 + TOKEN_OVERAGE_MARGIN_PCT), 6)


def overage_run_cap(org: Organization) -> int:
    multiplier = org.overage_run_cap_multiplier or DEFAULT_OVERAGE_RUN_CAP_MULTIPLIER
    return int(org_quota_runs(org) * multiplier)


def org_quota_runs(org: Organization) -> int:
    from loom.business.models import TIER_QUOTA_MAP

    return TIER_QUOTA_MAP[org.tier].runs_per_month


class InvoiceLine:
    __slots__ = ("label", "amount_usd", "quantity", "detail")

    def __init__(self, label: str, amount_usd: float, quantity: float = 1.0, detail: str = ""):
        self.label = label
        self.amount_usd = round(float(amount_usd), 6)
        self.quantity = quantity
        self.detail = detail

    def as_dict(self) -> Dict[str, object]:
        return {"label": self.label, "amount_usd": self.amount_usd, "quantity": self.quantity, "detail": self.detail}


def build_invoice(
    org: Organization,
    snapshot: OrgUsageSnapshot,
    ledger_entries: Optional[List[UsageLedgerEntry]] = None,
    overage_run_price_usd: float = TEAM_OVERAGE_RUN_PRICE_USD,
) -> Dict[str, object]:
    """Compose an itemized monthly invoice from the org's usage snapshot.

    Included quota (run credits) comes from the plan; overage is itemized by
    run credits and token margin. The org-configurable hard stop caps how
    many overage credits can be billed (default 2x included quota).
    """
    included = org_quota_runs(org)
    consumed_credits = 0
    if ledger_entries:
        consumed_credits = sum(credits_for_ledger_entries(ledger_entries).values())

    overage_credits = max(0, consumed_credits - included)
    cap = overage_run_cap(org)
    hard_stop_exceeded = overage_credits > max(0, cap - included)
    billable_overage = min(overage_credits, max(0, cap - included))

    lines: List[InvoiceLine] = [
        InvoiceLine(
            "included_run_credits",
            0.0,
            included,
            f"{org.tier.value} plan included quota (snapshot runs_consumed={snapshot.runs_consumed})",
        )
    ]
    if billable_overage > 0:
        lines.append(InvoiceLine("overage_run_credits", billable_overage * overage_run_price_usd, billable_overage))
    token_margin = round(snapshot.cost_usd_accrued * TOKEN_OVERAGE_MARGIN_PCT, 6)
    if snapshot.tokens_consumed > org_quota_tokens(org) and token_margin > 0:
        lines.append(InvoiceLine("token_margin_15pct", token_margin, detail="provider-passthrough cost + 15% margin"))

    total = round(sum(line.amount_usd for line in lines), 6)
    return {
        "org_id": org.id,
        "month": snapshot.month_start,
        "included_run_credits": included,
        "consumed_run_credits": consumed_credits,
        "overage_run_credits": overage_credits,
        "overage_cap_run_credits": max(0, cap - included),
        "hard_stop_exceeded": hard_stop_exceeded,
        "lines": [line.as_dict() for line in lines],
        "total_usd": total,
    }


def org_quota_tokens(org: Organization) -> int:
    from loom.business.models import TIER_QUOTA_MAP

    return TIER_QUOTA_MAP[org.tier].tokens_per_run * org_quota_runs(org)


def prorated_credit_for_plan_change(
    old_included_credits: int,
    new_included_credits: int,
    days_elapsed: int,
    days_in_cycle: int,
) -> int:
    """Prorated credits when a plan changes mid-cycle (spec §1.3).

    The user keeps the prior plan's credit for elapsed days and receives the
    new plan's credit for the remaining days.
    """
    if days_in_cycle <= 0:
        raise ValueError("days_in_cycle must be positive")
    elapsed = max(0, min(days_elapsed, days_in_cycle))
    remaining = days_in_cycle - elapsed
    return (old_included_credits * elapsed + new_included_credits * remaining) // days_in_cycle


def plan_change_effective_date(change_type: str, today: date, cycle_boundary: date) -> date:
    """Upgrades apply immediately; downgrades at the next billing cycle boundary."""
    if change_type.lower() in ("upgrade", "plan_change_upgrade"):
        return today
    if change_type.lower() in ("downgrade", "plan_change_downgrade"):
        if today >= cycle_boundary:
            return cycle_boundary + timedelta(days=30)
        return cycle_boundary
    return today


def tier_after_payment_grace(org: Organization, now: Optional[date] = None) -> OrgTier:
    """7-day grace at current tier, then auto-downgrade to Solo (no account lock)."""
    if org.last_payment_failed_at is None:
        return org.tier
    today = now or date.today()
    failed = date.fromtimestamp(org.last_payment_failed_at)
    if (today - failed).days < PAYMENT_GRACE_DAYS:
        return org.tier
    return SOLO_DOWNGRADE_TIER

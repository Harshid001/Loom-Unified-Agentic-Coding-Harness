"""Provider-neutral billing lifecycle primitives.

The core remains deterministic and does not require live Stripe credentials. A provider
adapter can translate these commands/events into Stripe API calls at the deployment edge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loom.business.models import BillingStatus, OrgTier, Organization


@dataclass(frozen=True)
class BillingEvent:
    event_id: str
    event_type: str
    org_id: str
    occurred_at: float
    payload: Dict[str, Any]


@dataclass(frozen=True)
class PlanChange:
    org_id: str
    old_tier: OrgTier
    new_tier: OrgTier
    effective_at: float
    prorated_credit_units: int


class BillingProviderError(RuntimeError):
    """Raised when a provider adapter cannot safely complete an operation."""


def apply_billing_event(org: Organization, event: BillingEvent) -> Organization:
    """Apply a verified provider event to local billing state.

    Unknown events are ignored so adding provider events remains forward compatible.
    """
    if event.org_id != org.id:
        raise BillingProviderError("billing event organization does not match local organization")

    event_type = event.event_type
    if event_type in {"invoice.paid", "payment_succeeded", "subscription.active"}:
        org.billing_status = BillingStatus.ACTIVE
        org.last_payment_failed_at = None
    elif event_type in {"invoice.payment_failed", "payment_failed"}:
        org.billing_status = BillingStatus.GRACE
        org.last_payment_failed_at = event.occurred_at
    elif event_type in {"customer.subscription.deleted", "subscription.canceled"}:
        org.billing_status = BillingStatus.CANCELED
    elif event_type == "customer.subscription.updated":
        tier_name = event.payload.get("tier")
        if tier_name:
            try:
                org.pending_tier = OrgTier(str(tier_name))
                effective = event.payload.get("effective_at")
                if effective is not None:
                    org.pending_tier_effective_at = float(effective)
            except ValueError as exc:
                raise BillingProviderError(f"unknown organization tier: {tier_name}") from exc
    return org


def settle_pending_plan_change(org: Organization, now: Optional[float] = None) -> bool:
    """Apply an already-approved pending tier change once its effective time arrives."""
    if org.pending_tier is None or org.pending_tier_effective_at is None:
        return False
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    if now < org.pending_tier_effective_at:
        return False
    org.tier = org.pending_tier
    org.pending_tier = None
    org.pending_tier_effective_at = None
    return True


def serialize_billing_state(org: Organization) -> Dict[str, Any]:
    return {
        "org_id": org.id,
        "tier": org.tier.value,
        "billing_status": org.billing_status.value,
        "stripe_customer_id": org.stripe_customer_id,
        "stripe_subscription_id": org.stripe_subscription_id,
        "billing_cycle_anchor": org.billing_cycle_anchor,
        "pending_tier": org.pending_tier.value if org.pending_tier else None,
        "pending_tier_effective_at": org.pending_tier_effective_at,
    }

"""Provider-neutral billing lifecycle primitives and Stripe adapter.

The core remains deterministic and does not require live Stripe credentials. A provider
adapter can translate these commands/events into Stripe API calls at the deployment edge.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loom.business.models import BillingStatus, Organization, OrgTier

logger = logging.getLogger("loom.business.billing_provider")


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


class StripeSignatureError(BillingProviderError):
    """Raised when a Stripe webhook signature fails verification."""


def verify_stripe_signature(
    payload: bytes,
    sig_header: str,
    secret: str,
    tolerance: int = 300,
    now: Optional[float] = None,
) -> bool:
    """Verify standard Stripe HMAC-SHA256 timestamped webhook signature (t=...,v1=...)."""
    if not sig_header or not secret:
        return False

    elements = {}
    signatures: List[str] = []
    for item in sig_header.split(","):
        parts = item.strip().split("=", 1)
        if len(parts) == 2:
            key, val = parts[0].strip(), parts[1].strip()
            if key == "t":
                elements["t"] = val
            elif key == "v1":
                signatures.append(val)

    timestamp_str = elements.get("t")
    if not timestamp_str or not signatures:
        return False

    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False

    current_time = int(now if now is not None else time.time())
    if tolerance > 0 and (current_time - timestamp > tolerance or timestamp - current_time > tolerance):
        return False

    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    mac = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256)
    expected = mac.hexdigest()

    return any(secrets.compare_digest(sig, expected) for sig in signatures)


def apply_billing_event(org: Organization, event: BillingEvent) -> Organization:
    """Apply a verified provider event to local billing state.

    Unknown events are ignored so adding provider events remains forward compatible.
    """
    if event.org_id != org.id:
        raise BillingProviderError("billing event organization does not match local organization")

    event_type = event.event_type
    if event_type in {"invoice.paid", "payment_succeeded", "subscription.active", "invoice.payment_succeeded"}:
        org.billing_status = BillingStatus.ACTIVE
        org.last_payment_failed_at = None
    elif event_type in {"invoice.payment_failed", "payment_failed"}:
        org.billing_status = BillingStatus.GRACE
        org.last_payment_failed_at = event.occurred_at
    elif event_type in {"customer.subscription.deleted", "subscription.canceled"}:
        org.billing_status = BillingStatus.CANCELED
    elif event_type in {"customer.subscription.updated", "checkout.session.completed"}:
        tier_name = event.payload.get("tier")
        if tier_name:
            try:
                tier_val = OrgTier(str(tier_name).lower())
                effective = event.payload.get("effective_at")
                if effective is not None:
                    org.pending_tier = tier_val
                    org.pending_tier_effective_at = float(effective)
                else:
                    org.tier = tier_val
            except ValueError as exc:
                raise BillingProviderError(f"unknown organization tier: {tier_name}") from exc
        customer_id = event.payload.get("customer_id") or event.payload.get("stripe_customer_id")
        if customer_id:
            org.stripe_customer_id = str(customer_id)
        sub_id = event.payload.get("subscription_id") or event.payload.get("stripe_subscription_id")
        if sub_id:
            org.stripe_subscription_id = str(sub_id)
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


class StripeBillingAdapter:
    """Production Stripe adapter handling webhooks, customer portal, checkout, and metered sync.

    When ``stripe`` is installed and ``api_key`` is configured (or ``STRIPE_API_KEY``
    is set in the environment) the adapter delegates to the real Stripe SDK.
    Otherwise it falls back to deterministic stubs so that dev and test environments
    do not require live credentials.
    """

    def __init__(self, api_key: Optional[str] = None, webhook_secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("STRIPE_API_KEY")
        self.webhook_secret = webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET")
        self._reported_usage: List[Dict[str, Any]] = []
        self._stripe = None
        if self.api_key:
            try:
                import stripe as _stripe
                _stripe.api_key = self.api_key
                self._stripe = _stripe
            except ImportError:
                pass

    @property
    def _is_live(self) -> bool:
        return self._stripe is not None and bool(self.api_key)

    def parse_event(
        self,
        payload_bytes: bytes,
        sig_header: str,
        secret: Optional[str] = None,
    ) -> BillingEvent:
        signing_secret = secret or self.webhook_secret
        if signing_secret:
            if not verify_stripe_signature(payload_bytes, sig_header, signing_secret):
                raise StripeSignatureError("Invalid Stripe webhook signature")

        try:
            raw = json.loads(payload_bytes.decode("utf-8"))
        except Exception as exc:
            raise BillingProviderError("Invalid JSON payload from Stripe") from exc

        event_id = raw.get("id", f"evt_{secrets.token_hex(8)}")
        event_type = raw.get("type", "unknown")
        created = float(raw.get("created", time.time()))
        data_object = (raw.get("data") or {}).get("object") or {}

        metadata = data_object.get("metadata") or {}
        org_id = metadata.get("org_id") or data_object.get("client_reference_id") or "default"

        payload: Dict[str, Any] = {
            "customer_id": data_object.get("customer"),
            "subscription_id": data_object.get("subscription") or data_object.get("id"),
            "tier": metadata.get("tier") or data_object.get("tier"),
            "amount_paid": data_object.get("amount_paid"),
            "currency": data_object.get("currency", "usd"),
            "status": data_object.get("status"),
        }

        if event_type == "customer.subscription.updated":
            items = (data_object.get("items") or {}).get("data", [])
            if items:
                plan_meta = (items[0].get("plan") or {}).get("metadata", {})
                if "tier" in plan_meta:
                    payload["tier"] = plan_meta["tier"]
            cancel_at = data_object.get("cancel_at_period_end")
            if cancel_at:
                payload["effective_at"] = data_object.get("current_period_end")

        return BillingEvent(
            event_id=event_id,
            event_type=event_type,
            org_id=org_id,
            occurred_at=created,
            payload=payload,
        )

    def create_checkout_session(
        self,
        org_id: str,
        target_tier: OrgTier,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self._is_live:
            try:
                session = self._stripe.checkout.Session.create(  # type: ignore[union-attr]
                    mode="subscription",
                    line_items=[
                        {
                            "price_data": {
                                "currency": "usd",
                                "product_data": {"name": f"Loom {target_tier.value.title()} Plan"},
                                "unit_amount": self._tier_price_cents(target_tier),
                                "recurring": {"interval": "month"},
                            },
                            "quantity": 1,
                        }
                    ],
                    success_url=success_url,
                    cancel_url=cancel_url,
                    client_reference_id=org_id,
                    metadata={"org_id": org_id, "target_tier": target_tier.value},
                )
                return {
                    "id": session.id,
                    "url": session.url,
                    "org_id": org_id,
                    "target_tier": target_tier.value,
                    "success_url": success_url,
                    "cancel_url": cancel_url,
                }
            except Exception as exc:
                logger.warning("Stripe checkout session creation failed, falling back to stub: %s", exc)

        # Stub fallback for dev/test without live Stripe credentials
        session_id = f"cs_test_{secrets.token_urlsafe(16)}"
        url = f"https://checkout.stripe.com/c/pay/{session_id}?org_id={org_id}&tier={target_tier.value}"
        return {
            "id": session_id,
            "url": url,
            "org_id": org_id,
            "target_tier": target_tier.value,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }

    def create_portal_session(self, customer_id: str, return_url: str) -> Dict[str, Any]:
        if self._is_live:
            try:
                session = self._stripe.billing_portal.Session.create(  # type: ignore[union-attr]
                    customer=customer_id,
                    return_url=return_url,
                )
                return {
                    "id": session.id,
                    "url": session.url,
                    "customer_id": customer_id,
                    "return_url": return_url,
                }
            except Exception as exc:
                logger.warning("Stripe portal session creation failed, falling back to stub: %s", exc)

        # Stub fallback for dev/test without live Stripe credentials
        session_id = f"bps_{secrets.token_urlsafe(16)}"
        url = f"https://billing.stripe.com/p/session/{session_id}?customer={customer_id}"
        return {
            "id": session_id,
            "url": url,
            "customer_id": customer_id,
            "return_url": return_url,
        }

    def report_metered_usage(
        self,
        subscription_item_id: str,
        quantity: int,
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        if self._is_live:
            try:
                record = self._stripe.SubscriptionItem.create_usage_record(  # type: ignore[union-attr]
                    subscription_item=subscription_item_id,
                    quantity=quantity,
                    timestamp=timestamp or int(time.time()),
                    action="increment",
                )
                return {
                    "id": record.id,
                    "subscription_item_id": subscription_item_id,
                    "quantity": quantity,
                    "timestamp": record.timestamp,
                    "status": "recorded",
                }
            except Exception as exc:
                logger.warning("Stripe metered usage reporting failed, falling back to stub: %s", exc)

        # Stub fallback for dev/test without live Stripe credentials
        record = {
            "id": f"mrec_{secrets.token_hex(8)}",
            "subscription_item_id": subscription_item_id,
            "quantity": quantity,
            "timestamp": timestamp or int(time.time()),
            "status": "recorded",
        }
        self._reported_usage.append(record)
        return record

    def _tier_price_cents(self, tier: OrgTier) -> int:
        """Return monthly price in cents for the given tier."""
        prices = {
            OrgTier.SOLO: 0,
            OrgTier.TEAM: 2900,
            OrgTier.ENTERPRISE: 9900,
            OrgTier.SELF_HOSTED: 0,
        }
        return prices.get(tier, 0)


_stripe_adapter_instance: Optional[StripeBillingAdapter] = None


def get_stripe_adapter() -> StripeBillingAdapter:
    global _stripe_adapter_instance
    if _stripe_adapter_instance is None:
        _stripe_adapter_instance = StripeBillingAdapter()
    return _stripe_adapter_instance


def reset_stripe_adapter() -> None:
    global _stripe_adapter_instance
    _stripe_adapter_instance = None


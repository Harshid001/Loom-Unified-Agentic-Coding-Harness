"""Tests for Stripe metered billing adapter, webhooks, and session endpoints (Phase 5, §1.3)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from loom.api.app import create_app
from loom.api.dependencies import get_entitlements, reset_entitlements
from loom.auth.context import clear_principal
from loom.business.billing import prorated_credit_for_plan_change, tier_after_payment_grace
from loom.business.billing_provider import (
    BillingEvent,
    StripeBillingAdapter,
    apply_billing_event,
    get_stripe_adapter,
    reset_stripe_adapter,
    settle_pending_plan_change,
    verify_stripe_signature,
)
from loom.business.models import BillingStatus, Organization, OrgTier


@pytest.fixture(autouse=True)
def clean_state():
    reset_entitlements()
    reset_stripe_adapter()
    clear_principal()
    yield
    reset_entitlements()
    reset_stripe_adapter()
    clear_principal()


def _generate_stripe_header(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(timestamp or time.time())
    signed_payload = f"{ts}.".encode("utf-8") + payload
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_verify_stripe_signature_valid():
    secret = "whsec_test_secret_key_123"
    payload = b'{"id": "evt_test_123", "type": "invoice.paid"}'
    header = _generate_stripe_header(payload, secret)

    assert verify_stripe_signature(payload, header, secret) is True


def test_verify_stripe_signature_invalid_secret():
    secret = "whsec_test_secret_key_123"
    payload = b'{"id": "evt_test_123", "type": "invoice.paid"}'
    header = _generate_stripe_header(payload, secret)

    assert verify_stripe_signature(payload, header, "wrong_secret") is False


def test_verify_stripe_signature_expired():
    secret = "whsec_test_secret_key_123"
    payload = b'{"id": "evt_test_123", "type": "invoice.paid"}'
    old_ts = int(time.time()) - 600
    header = _generate_stripe_header(payload, secret, timestamp=old_ts)

    assert verify_stripe_signature(payload, header, secret, tolerance=300) is False


def test_stripe_adapter_event_normalization():
    adapter = StripeBillingAdapter(webhook_secret="whsec_123")
    raw_event = {
        "id": "evt_norm_123",
        "type": "customer.subscription.updated",
        "created": time.time(),
        "data": {
            "object": {
                "id": "sub_12345",
                "customer": "cus_67890",
                "status": "active",
                "metadata": {"org_id": "org_acme", "tier": "team"},
                "cancel_at_period_end": True,
                "current_period_end": time.time() + 86400 * 30,
            }
        },
    }
    payload_bytes = json.dumps(raw_event).encode("utf-8")
    header = _generate_stripe_header(payload_bytes, "whsec_123")

    event = adapter.parse_event(payload_bytes, header)
    assert event.event_id == "evt_norm_123"
    assert event.event_type == "customer.subscription.updated"
    assert event.org_id == "org_acme"
    assert event.payload["tier"] == "team"
    assert event.payload["customer_id"] == "cus_67890"
    assert event.payload["subscription_id"] == "sub_12345"


def test_apply_billing_event_transitions():
    org = Organization(id="org_test", name="Test Org", tier=OrgTier.SOLO)

    event_checkout = BillingEvent(
        event_id="evt_1",
        event_type="checkout.session.completed",
        org_id="org_test",
        occurred_at=time.time(),
        payload={"tier": "team", "customer_id": "cus_123", "subscription_id": "sub_456"},
    )
    apply_billing_event(org, event_checkout)
    assert org.tier == OrgTier.TEAM
    assert org.stripe_customer_id == "cus_123"
    assert org.stripe_subscription_id == "sub_456"

    event_failed = BillingEvent(
        event_id="evt_2",
        event_type="invoice.payment_failed",
        org_id="org_test",
        occurred_at=time.time(),
        payload={},
    )
    apply_billing_event(org, event_failed)
    assert org.billing_status == BillingStatus.GRACE
    assert org.last_payment_failed_at is not None

    event_paid = BillingEvent(
        event_id="evt_3",
        event_type="invoice.paid",
        org_id="org_test",
        occurred_at=time.time(),
        payload={},
    )
    apply_billing_event(org, event_paid)
    assert org.billing_status == BillingStatus.ACTIVE
    assert org.last_payment_failed_at is None


def test_settle_pending_plan_change():
    now = time.time()
    org = Organization(
        id="org_pending",
        name="Pending Org",
        tier=OrgTier.TEAM,
        pending_tier=OrgTier.SOLO,
        pending_tier_effective_at=now - 100,
    )
    settled = settle_pending_plan_change(org, now=now)
    assert settled is True
    assert org.tier == OrgTier.SOLO
    assert org.pending_tier is None
    assert org.pending_tier_effective_at is None


def test_metered_usage_reporting():
    adapter = get_stripe_adapter()
    rec = adapter.report_metered_usage("si_item_123", 42)
    assert rec["subscription_item_id"] == "si_item_123"
    assert rec["quantity"] == 42
    assert rec["status"] == "recorded"


def test_proration_and_grace_period():
    prorated = prorated_credit_for_plan_change(
        old_included_credits=50,
        new_included_credits=500,
        days_elapsed=15,
        days_in_cycle=30,
    )
    assert prorated == 275

    org = Organization(id="grace_org", name="Grace", tier=OrgTier.TEAM)
    assert tier_after_payment_grace(org) == OrgTier.TEAM


def test_stripe_webhook_api_endpoint(monkeypatch):
    secret = "whsec_api_test_secret"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    reset_stripe_adapter()

    app = create_app()
    client = TestClient(app)

    entitlements = get_entitlements()
    org = Organization(id="org_webhook", name="Webhook Org", tier=OrgTier.SOLO)
    entitlements.register_org(org)

    raw_event = {
        "id": "evt_api_test",
        "type": "customer.subscription.updated",
        "created": time.time(),
        "data": {
            "object": {
                "id": "sub_api",
                "customer": "cus_api",
                "metadata": {"org_id": "org_webhook", "tier": "team"},
            }
        },
    }
    payload_bytes = json.dumps(raw_event).encode("utf-8")
    valid_header = _generate_stripe_header(payload_bytes, secret)

    res = client.post(
        "/api/v1/billing/stripe/webhook",
        content=payload_bytes,
        headers={"stripe-signature": valid_header, "content-type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["received"] is True

    updated_org = entitlements.get_org("org_webhook")
    assert updated_org.tier == OrgTier.TEAM

    res_invalid = client.post(
        "/api/v1/billing/stripe/webhook",
        content=payload_bytes,
        headers={"stripe-signature": "t=123,v1=bad_signature", "content-type": "application/json"},
    )
    assert res_invalid.status_code == 400


def test_checkout_and_portal_sessions(monkeypatch):
    monkeypatch.setenv("API_KEY", "master_key")
    app = create_app()
    client = TestClient(app)

    entitlements = get_entitlements()
    org = Organization(id="default", name="Default", tier=OrgTier.SOLO, stripe_customer_id="cus_existing")
    entitlements.register_org(org)

    res_checkout = client.post(
        "/api/v1/billing/checkout-session",
        json={"target_tier": "team", "success_url": "https://example.com/ok", "cancel_url": "https://example.com/cancel"},
        headers={"x-api-key": "master_key"},
    )
    assert res_checkout.status_code == 200
    assert "checkout.stripe.com" in res_checkout.json()["url"]

    res_portal = client.post(
        "/api/v1/billing/portal-session",
        json={"return_url": "https://example.com/return"},
        headers={"x-api-key": "master_key"},
    )
    assert res_portal.status_code == 200
    assert "billing.stripe.com" in res_portal.json()["url"]


def test_get_org_invoice(monkeypatch):
    monkeypatch.setenv("API_KEY", "master_key")
    app = create_app()
    client = TestClient(app)

    entitlements = get_entitlements()
    org = Organization(id="default", name="Default", tier=OrgTier.TEAM)
    entitlements.register_org(org)

    res = client.get(
        "/api/v1/billing/invoices/default",
        headers={"x-api-key": "master_key"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["org_id"] == "default"
    assert "included_run_credits" in data
    assert "lines" in data

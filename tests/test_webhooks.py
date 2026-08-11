import asyncio
import hashlib
import hmac

import httpx
import pytest

from loom.api.webhooks import (
    WebhookDeliveryStatus,
    WebhookEngine,
    WebhookEventType,
    WebhookPayload,
    WebhookSubscription,
)


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


class FakeAsyncClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    async def post(self, url, content=None, headers=None, timeout=None):
        self.calls.append({"url": url, "content": content, "headers": headers, "timeout": timeout})
        key = url
        response = self.responses.get(key, self.responses.get("__default__", FakeResponse()))
        return response

    async def aclose(self):
        pass


@pytest.fixture
def engine(tmp_path):
    eng = WebhookEngine(storage_dir=str(tmp_path / "webhooks"))
    eng._http = FakeAsyncClient()
    return eng


@pytest.fixture
def subscription():
    return WebhookSubscription(
        id="sub_001",
        org_id="org_test",
        url="https://example.com/webhook",
        events={WebhookEventType.RUN_COMPLETED, WebhookEventType.RUN_FAILED},
        secret="secret123",
        max_retries=2,
        retry_backoff_base_seconds=0.01,
    )


class TestWebhookSubscription:
    def test_register_and_retrieve(self, engine, subscription):
        engine.register(subscription)
        subs = engine.get_subscriptions(org_id="org_test")
        assert len(subs) == 1
        assert subs[0].id == "sub_001"

    def test_unregister(self, engine, subscription):
        engine.register(subscription)
        assert engine.unregister("sub_001") is True
        assert engine.unregister("sub_001") is False

    def test_matching_subscriptions_filters_by_event(self, engine, subscription):
        subscription.events = {WebhookEventType.PATCH_AUTO_MERGED}
        engine.register(subscription)
        matches = engine.matching_subscriptions(WebhookEventType.RUN_COMPLETED, "org_test")
        assert len(matches) == 0
        matches = engine.matching_subscriptions(WebhookEventType.PATCH_AUTO_MERGED, "org_test")
        assert len(matches) == 1

    def test_inactive_subscription_skipped(self, engine, subscription):
        subscription.active = False
        engine.register(subscription)
        matches = engine.matching_subscriptions(WebhookEventType.RUN_COMPLETED, "org_test")
        assert len(matches) == 0

    def test_get_subscriptions_all(self, engine):
        s1 = WebhookSubscription(id="s1", org_id="a", url="https://a.com", events=set())
        s2 = WebhookSubscription(id="s2", org_id="b", url="https://b.com", events=set())
        engine.register(s1)
        engine.register(s2)
        assert len(engine.get_subscriptions()) == 2
        assert len(engine.get_subscriptions(org_id="a")) == 1


class TestWebhookDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_success(self, engine, subscription):
        engine._http.responses["https://example.com/webhook"] = FakeResponse(200)
        engine.register(subscription)

        deliveries = await engine.dispatch(
            WebhookEventType.RUN_COMPLETED, "run_abc", {"verification_passed": True},
            org_id="org_test",
        )
        assert len(deliveries) == 1
        assert deliveries[0].status == WebhookDeliveryStatus.DELIVERED

    @pytest.mark.asyncio
    async def test_dispatch_retry_on_failure(self, engine, subscription):
        subscription.max_retries = 3
        subscription.retry_backoff_base_seconds = 0.001
        engine._http.responses["https://example.com/webhook"] = FakeResponse(500)
        engine.register(subscription)

        deliveries = await engine.dispatch(
            WebhookEventType.RUN_COMPLETED, "run_abc", {"verification_passed": True},
            org_id="org_test",
        )
        assert deliveries[0].status == WebhookDeliveryStatus.FAILED
        assert deliveries[0].attempt_number == 3

    @pytest.mark.asyncio
    async def test_dispatch_no_subscriptions_returns_empty(self, engine):
        deliveries = await engine.dispatch(
            WebhookEventType.RUN_COMPLETED, "run_abc", {}, org_id="nonexistent",
        )
        assert deliveries == []

    @pytest.mark.asyncio
    async def test_dispatch_hmac_signature_header(self, engine, subscription):
        engine._http.responses["https://example.com/webhook"] = FakeResponse(200)
        engine.register(subscription)

        await engine.dispatch(
            WebhookEventType.RUN_COMPLETED, "run_abc", {"key": "value"},
            org_id="org_test",
        )
        call = engine._http.calls[0]
        assert "X-Loom-Signature-256" in call["headers"]
        sig = call["headers"]["X-Loom-Signature-256"]
        assert sig.startswith("sha256=")

        body = call["content"]
        expected_mac = hmac.new(
            b"secret123", body, hashlib.sha256
        ).hexdigest()
        assert sig == f"sha256={expected_mac}"

    @pytest.mark.asyncio
    async def test_dispatch_headers_include_event_and_delivery_id(self, engine, subscription):
        engine._http.responses["https://example.com/webhook"] = FakeResponse(200)
        engine.register(subscription)

        await engine.dispatch(
            WebhookEventType.RUN_COMPLETED, "run_abc", {},
            org_id="org_test",
        )
        headers = engine._http.calls[0]["headers"]
        assert headers["X-Loom-Event"] == "run.completed"
        assert headers["X-Loom-Delivery-ID"].startswith("wh_")

    @pytest.mark.asyncio
    async def test_dispatch_handles_timeout(self, engine, subscription):
        subscription.max_retries = 1
        subscription.retry_backoff_base_seconds = 0.001

        class TimeoutClient(FakeAsyncClient):
            async def post(self, url, content=None, headers=None, timeout=None):
                raise httpx.TimeoutException("timed out")

        engine._http = TimeoutClient()
        engine.register(subscription)

        deliveries = await engine.dispatch(
            WebhookEventType.RUN_COMPLETED, "run_abc", {},
            org_id="org_test",
        )
        assert deliveries[0].status == WebhookDeliveryStatus.FAILED
        assert "timed out" in deliveries[0].last_error


class TestWebhookPayload:
    def test_payload_model(self):
        payload = WebhookPayload(
            event=WebhookEventType.PATCH_AUTO_MERGED,
            run_id="run_001",
            data={"patch": "+x = 1"},
            delivery_id="wh_abc",
        )
        d = payload.model_dump()
        assert d["event"] == "patch.auto_merged"
        assert d["run_id"] == "run_001"
        assert d["data"]["patch"] == "+x = 1"


class TestDeliveryPersistence:
    def test_get_delivery_by_id(self, engine, subscription, tmp_path):
        engine._http.responses["https://example.com/webhook"] = FakeResponse(200)
        engine.register(subscription)
        deliveries = asyncio.run(
            engine.dispatch(WebhookEventType.RUN_COMPLETED, "run_abc", {}, org_id="org_test")
        )
        d_id = deliveries[0].id
        retrieved = engine.get_delivery(d_id)
        assert retrieved is not None
        assert retrieved.id == d_id

    def test_dead_letter_queue(self, engine, subscription, tmp_path):
        subscription.max_retries = 1
        subscription.retry_backoff_base_seconds = 0.001
        engine._http.responses["https://example.com/webhook"] = FakeResponse(500)
        engine.register(subscription)

        asyncio.run(
            engine.dispatch(WebhookEventType.RUN_COMPLETED, "run_abc", {}, org_id="org_test")
        )
        dead = engine.get_dead_letters()
        assert len(dead) >= 1
        assert dead[0].event_type == WebhookEventType.RUN_COMPLETED


class TestDispatchSync:
    @pytest.mark.asyncio
    async def test_dispatch_sync_succeeds(self, engine, subscription):
        engine._http.responses["https://example.com/webhook"] = FakeResponse(200)
        engine.register(subscription)
        deliveries = await engine.dispatch(
            WebhookEventType.RUN_COMPLETED, "run_sync", {"hash": "abc123"},
            org_id="org_test",
        )
        assert len(deliveries) == 1
        assert deliveries[0].status == WebhookDeliveryStatus.DELIVERED

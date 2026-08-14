import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("loom.api.webhooks")


class WebhookEventType(str, Enum):
    RUN_QUEUED = "run.queued"
    RUN_STARTED = "run.started"
    RUN_STEP_PROGRESS = "run.step_progress"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_SECURITY_HOLD = "run.security_hold"
    RUN_ROLLED_BACK = "run.rolled_back"
    PATCH_PROPOSED = "patch.proposed"
    PATCH_AUTO_MERGED = "patch.auto_merged"
    EVIDENCE_READY = "evidence.ready"
    EVIDENCE_EXPORTED = "evidence.exported"
    USAGE_QUOTA_WARNING = "usage.quota_warning"
    USAGE_QUOTA_EXCEEDED = "usage.quota_exceeded"
    QUOTA_WARNING = "quota.warning"
    QUOTA_EXCEEDED = "quota.exceeded"
    SANDBOX_EGRESS_BLOCKED = "sandbox.egress_blocked"
    EVIDENCE_CHAIN_VIOLATION = "evidence.chain_violation"


class WebhookDeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


class WebhookSubscription(BaseModel):
    id: str
    org_id: str
    url: str
    events: Set[WebhookEventType] = Field(default_factory=lambda: set(WebhookEventType))
    secret: Optional[str] = None
    active: bool = True
    max_retries: int = 5
    retry_backoff_base_seconds: float = 2.0
    timeout_seconds: float = 10.0
    created_at: float = Field(default_factory=time.time)


class WebhookDelivery(BaseModel):
    id: str
    subscription_id: str
    event_type: WebhookEventType
    payload: Dict[str, Any]
    status: WebhookDeliveryStatus = WebhookDeliveryStatus.PENDING
    attempt_number: int = 0
    last_attempt_at: Optional[float] = None
    last_status_code: Optional[int] = None
    last_error: Optional[str] = None
    delivered_at: Optional[float] = None
    created_at: float = Field(default_factory=time.time)


class WebhookPayload(BaseModel):
    event: WebhookEventType
    run_id: str
    timestamp: float = Field(default_factory=time.time)
    data: Dict[str, Any] = Field(default_factory=dict)
    delivery_id: Optional[str] = None


class WebhookEngine:
    """
    Outbound webhook dispatch engine with HMAC signing, exponential backoff
    retry, dead-letter queue persistence, and idempotency guarantees (PRD §5).
    """

    DELIVERY_DIR_NAME = "webhook_deliveries"
    DEAD_LETTER_FILE = "dead_letter_queue.jsonl"

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        http_client: Optional[Any] = None,
    ):
        base = Path(storage_dir or str(Path.home() / ".loom" / "webhooks"))
        self._dir = base
        self._dir.mkdir(parents=True, exist_ok=True)
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._deliveries: Dict[str, WebhookDelivery] = {}
        self._http: Optional[Any] = http_client
        self._load_subscriptions()

    async def _ensure_client(self):
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    async def close(self):
        if self._http:
            await self._http.aclose()
            self._http = None

    def _subs_file(self) -> Path:
        return self._dir / "subscriptions.json"

    def _deliveries_dir(self) -> Path:
        return self._dir / self.DELIVERY_DIR_NAME

    def _dead_letter_file(self) -> Path:
        return self._dir / self.DEAD_LETTER_FILE

    def _encrypt_secret(self, secret: Optional[str]) -> Optional[str]:
        if not secret or secret.startswith("enc:"):
            return secret
        key = os.getenv("LOOM_WEBHOOK_SECRET_KEY")
        if not key:
            return secret
        try:
            from cryptography.fernet import Fernet
            fernet = Fernet(key.encode() if isinstance(key, str) else key)
            return "enc:" + fernet.encrypt(secret.encode()).decode()
        except Exception:
            return secret

    def _decrypt_secret(self, secret: Optional[str]) -> Optional[str]:
        if not secret or not secret.startswith("enc:"):
            return secret
        key = os.getenv("LOOM_WEBHOOK_SECRET_KEY")
        if not key:
            return secret
        try:
            from cryptography.fernet import Fernet
            fernet = Fernet(key.encode() if isinstance(key, str) else key)
            return fernet.decrypt(secret[4:].encode()).decode()
        except Exception:
            return secret

    def _load_subscriptions(self):
        path = self._subs_file()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for s in raw:
                if s.get("secret"):
                    s["secret"] = self._decrypt_secret(s.get("secret"))
                sub = WebhookSubscription(**s)
                self._subscriptions[sub.id] = sub
        except Exception as exc:
            logger.warning("Failed to load webhook subscriptions: %s", exc)

    def _save_subscriptions(self):
        path = self._subs_file()
        dumped = []
        for s in self._subscriptions.values():
            d = s.model_dump(exclude={"events"}) | {"events": [e.value for e in s.events]}
            if d.get("secret"):
                d["secret"] = self._encrypt_secret(d["secret"])
            dumped.append(d)
        path.write_text(
            json.dumps(dumped, indent=2),
            encoding="utf-8",
        )

    def register(self, subscription: WebhookSubscription) -> WebhookSubscription:
        self._subscriptions[subscription.id] = subscription
        self._save_subscriptions()
        return subscription

    def unregister(self, subscription_id: str) -> bool:
        if subscription_id in self._subscriptions:
            del self._subscriptions[subscription_id]
            self._save_subscriptions()
            return True
        return False

    def get_subscriptions(self, org_id: Optional[str] = None) -> List[WebhookSubscription]:
        if org_id:
            return [s for s in self._subscriptions.values() if s.org_id == org_id]
        return list(self._subscriptions.values())

    def matching_subscriptions(
        self, event_type: WebhookEventType, org_id: Optional[str] = None
    ) -> List[WebhookSubscription]:
        results = []
        for sub in self._subscriptions.values():
            if not sub.active:
                continue
            if org_id and sub.org_id != org_id:
                continue
            if WebhookEventType.RUN_STARTED in sub.events or event_type in sub.events:
                results.append(sub)
        return results

    def _sign_payload(self, payload: bytes, secret: str) -> str:
        mac = hmac.new(secret.encode(), payload, hashlib.sha256)
        return f"sha256={mac.hexdigest()}"

    def _delivery_path(self, delivery_id: str) -> Path:
        return self._deliveries_dir() / f"{delivery_id}.json"

    def _save_delivery(self, delivery: WebhookDelivery):
        path = self._delivery_path(delivery.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(delivery.model_dump(), indent=2), encoding="utf-8")

    def _append_dead_letter(self, delivery: WebhookDelivery):
        dlq = self._dead_letter_file()
        dlq.parent.mkdir(parents=True, exist_ok=True)
        with dlq.open("a", encoding="utf-8") as f:
            f.write(json.dumps(delivery.model_dump(), default=str) + "\n")

    async def _deliver_one(
        self,
        subscription: WebhookSubscription,
        delivery: WebhookDelivery,
    ) -> WebhookDelivery:
        await self._ensure_client()
        assert self._http is not None

        delivery.attempt_number += 1
        delivery.last_attempt_at = time.time()
        delivery.status = WebhookDeliveryStatus.RETRYING

        body = json.dumps(delivery.payload).encode("utf-8")
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "X-Loom-Event": delivery.event_type.value,
            "X-Loom-Delivery-ID": delivery.id,
            "X-Loom-Run-ID": delivery.payload.get("run_id", ""),
        }

        if subscription.secret:
            headers["X-Loom-Signature-256"] = self._sign_payload(body, subscription.secret)

        try:
            response = await self._http.post(
                subscription.url,
                content=body,
                headers=headers,
                timeout=subscription.timeout_seconds,
            )
            delivery.last_status_code = response.status_code
            if 200 <= response.status_code < 300:
                delivery.status = WebhookDeliveryStatus.DELIVERED
                delivery.delivered_at = time.time()
            else:
                delivery.last_error = f"HTTP {response.status_code}: {response.text[:500]}"
                delivery.status = WebhookDeliveryStatus.FAILED
        except httpx.TimeoutException:
            delivery.last_error = "Request timed out"
            delivery.status = WebhookDeliveryStatus.FAILED
        except Exception as exc:
            delivery.last_error = str(exc)[:500]
            delivery.status = WebhookDeliveryStatus.FAILED

        self._save_delivery(delivery)
        return delivery

    async def _retry_delivery(
        self,
        subscription: WebhookSubscription,
        delivery: WebhookDelivery,
    ) -> WebhookDelivery:
        for attempt in range(subscription.max_retries):
            delay = subscription.retry_backoff_base_seconds * (2**attempt)
            await asyncio.sleep(delay)
            delivery = await self._deliver_one(subscription, delivery)
            if delivery.status == WebhookDeliveryStatus.DELIVERED:
                return delivery
            if delivery.attempt_number >= subscription.max_retries:
                break

        self._append_dead_letter(delivery)
        return delivery

    async def dispatch(
        self,
        event_type: WebhookEventType,
        run_id: str,
        data: Dict[str, Any],
        org_id: Optional[str] = None,
    ) -> List[WebhookDelivery]:
        subscriptions = self.matching_subscriptions(event_type, org_id)
        if not subscriptions:
            return []

        deliveries: List[WebhookDelivery] = []
        tasks = []

        for sub in subscriptions:
            import uuid

            delivery_id = f"wh_{uuid.uuid4().hex[:16]}"
            payload = WebhookPayload(
                event=event_type,
                run_id=run_id,
                data=data,
                delivery_id=delivery_id,
            )

            delivery = WebhookDelivery(
                id=delivery_id,
                subscription_id=sub.id,
                event_type=event_type,
                payload=payload.model_dump(),
            )

            self._deliveries[delivery_id] = delivery
            self._save_delivery(delivery)
            deliveries.append(delivery)

            async def _attempt(sub=sub, d=delivery):
                result = await self._deliver_one(sub, d)
                if result.status != WebhookDeliveryStatus.DELIVERED:
                    result = await self._retry_delivery(sub, result)
                self._deliveries[result.id] = result
                return result

            tasks.append(_attempt())

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    deliveries[i].last_error = str(r)[:500]
                    deliveries[i].status = WebhookDeliveryStatus.FAILED

        return deliveries

    def dispatch_sync(
        self,
        event_type: WebhookEventType,
        run_id: str,
        data: Dict[str, Any],
        org_id: Optional[str] = None,
    ) -> List[WebhookDelivery]:
        return asyncio.run(self.dispatch(event_type, run_id, data, org_id))

    def get_delivery(self, delivery_id: str) -> Optional[WebhookDelivery]:
        if delivery_id in self._deliveries:
            return self._deliveries[delivery_id]
        path = self._delivery_path(delivery_id)
        if path.exists():
            try:
                return WebhookDelivery(**json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return None

    def get_dead_letters(self, limit: int = 100) -> List[WebhookDelivery]:
        dlq = self._dead_letter_file()
        if not dlq.exists():
            return []
        results = []
        for line in dlq.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                results.append(WebhookDelivery(**json.loads(line)))
            except Exception:
                continue
        return results[-limit:]

    def replay_dead_letters(
        self,
        on_progress: Optional[Callable[[WebhookDelivery, WebhookDelivery], Any]] = None,
    ) -> List[WebhookDelivery]:
        dead = self.get_dead_letters()
        results = []
        for d in dead:
            sub = self._subscriptions.get(d.subscription_id)
            if not sub or not sub.active:
                continue
            try:
                result = asyncio.run(self._deliver_one(sub, d))
                if on_progress:
                    on_progress(d, result)
                results.append(result)
            except Exception as exc:
                logger.warning("Dead letter replay failed for %s: %s", d.id, exc)
        return results


_webhook_engine_instance: Optional[WebhookEngine] = None


def get_webhook_engine(storage_dir: Optional[str] = None) -> WebhookEngine:
    global _webhook_engine_instance
    if _webhook_engine_instance is None:
        _webhook_engine_instance = WebhookEngine(storage_dir=storage_dir)
    return _webhook_engine_instance


def reset_webhook_engine() -> None:
    global _webhook_engine_instance
    _webhook_engine_instance = None

"""Outbound webhook subscriptions and delivery engine."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("loom.api.webhooks")


class WebhookEventType(str, Enum):
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_ROLLED_BACK = "run_rolled_back"
    SECURITY_HOLD = "security_hold"


class WebhookDeliveryStatus(str, Enum):
    PENDING = "pending"
    RETRYING = "retrying"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class WebhookSubscription(BaseModel):
    id: str
    org_id: str
    url: str
    events: set[WebhookEventType] = Field(default_factory=set)
    secret: Optional[str] = None
    active: bool = True
    timeout_seconds: int = 10


class WebhookDelivery(BaseModel):
    id: str
    subscription_id: str
    event_type: WebhookEventType
    payload: Dict[str, Any]
    status: WebhookDeliveryStatus = WebhookDeliveryStatus.PENDING
    attempt_number: int = 0
    last_attempt_at: Optional[float] = None
    delivered_at: Optional[float] = None
    last_error: Optional[str] = None


class WebhookEngine:
    DELIVERY_DIR_NAME = "deliveries"
    DEAD_LETTER_FILE = "dead_letter.jsonl"
    MAX_ATTEMPTS = 5

    def __init__(self, storage_dir: Optional[str] = None):
        self._dir = Path(storage_dir or (Path.home() / ".loom" / "webhooks"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._http: Optional[httpx.AsyncClient] = None
        self._load_subscriptions()

    async def _ensure_client(self):
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=False)

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

    def _load_subscriptions(self):
        path = self._subs_file()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for s in raw:
                sub = WebhookSubscription(**s)
                self._subscriptions[sub.id] = sub
        except Exception as exc:
            logger.warning("Failed to load webhook subscriptions: %s", exc)

    def _save_subscriptions(self):
        path = self._subs_file()
        path.write_text(
            json.dumps(
                [
                    s.model_dump(exclude={"events"}) | {"events": [e.value for e in s.events]}
                    for s in self._subscriptions.values()
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

    def register(self, subscription: WebhookSubscription) -> WebhookSubscription:
        if os.getenv("LOOM_ENV", "").lower() in {"prod", "production"} and subscription.secret:
            if not (os.getenv("LOOM_WEBHOOK_SECRET_KEY") or os.getenv("LOOM_BACKUP_ENCRYPTION_KEY")):
                raise RuntimeError("Webhook secret encryption key is required in production")
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

    def matching_subscriptions(self, event_type: WebhookEventType, org_id: Optional[str] = None) -> List[WebhookSubscription]:
        results = []
        for sub in self._subscriptions.values():
            if not sub.active:
                continue
            if org_id and sub.org_id != org_id:
                continue
            if event_type in sub.events:
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

    async def _deliver_one(self, subscription: WebhookSubscription, delivery: WebhookDelivery) -> WebhookDelivery:
        await self._ensure_client()
        assert self._http is not None
        delivery.attempt_number += 1
        delivery.last_attempt_at = time.time()
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
            response = await self._http.post(subscription.url, content=body, headers=headers, timeout=subscription.timeout_seconds)
            if 200 <= response.status_code < 300:
                delivery.status = WebhookDeliveryStatus.DELIVERED
                delivery.delivered_at = time.time()
                delivery.last_error = None
            else:
                raise RuntimeError(f"Webhook endpoint returned HTTP {response.status_code}")
        except Exception as exc:
            delivery.last_error = "delivery failed"
            if delivery.attempt_number >= self.MAX_ATTEMPTS:
                delivery.status = WebhookDeliveryStatus.DEAD_LETTER
                self._append_dead_letter(delivery)
            else:
                delivery.status = WebhookDeliveryStatus.RETRYING
        self._save_delivery(delivery)
        return delivery

    async def emit(self, event_type: WebhookEventType, payload: Dict[str, Any], org_id: Optional[str] = None) -> List[WebhookDelivery]:
        deliveries: List[WebhookDelivery] = []
        for sub in self.matching_subscriptions(event_type, org_id):
            delivery = WebhookDelivery(
                id=f"wh_del_{uuid.uuid4().hex[:12]}",
                subscription_id=sub.id,
                event_type=event_type,
                payload=payload,
            )
            deliveries.append(await self._deliver_one(sub, delivery))
        return deliveries


_webhook_engine: Optional[WebhookEngine] = None


def get_webhook_engine() -> WebhookEngine:
    global _webhook_engine
    if _webhook_engine is None:
        _webhook_engine = WebhookEngine()
    return _webhook_engine


def reset_webhook_engine() -> None:
    global _webhook_engine
    _webhook_engine = None

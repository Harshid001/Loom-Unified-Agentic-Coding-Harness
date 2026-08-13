"""Production distributed coordination primitives.

The API keeps an in-process execution cache for backward compatibility, while
Redis becomes the shared source for rate limits, run metadata, event history,
and cross-replica control commands in production.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover - dependency is installed in production
    Redis = None  # type: ignore[assignment,misc]


EVENT_TTL_SECONDS = int(os.getenv("LOOM_RUN_EVENT_TTL_SECONDS", "86400"))
RUN_TTL_SECONDS = int(os.getenv("LOOM_RUN_TTL_SECONDS", "604800"))


class DistributedInfraError(RuntimeError):
    """Raised when required production distributed infrastructure is unavailable."""


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    org_id: str
    repo_path: str
    status: str
    sandbox_tier: str
    created_at: float


class RedisCoordinator:
    """Shared Redis coordination for horizontally scaled Loom API instances."""

    def __init__(self, url: Optional[str] = None):
        self.url = url or os.getenv("REDIS_URL")
        self._client: Optional[Redis] = None

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    @property
    def client(self) -> Redis:
        if Redis is None:
            raise DistributedInfraError("redis package is not installed")
        if not self.url:
            raise DistributedInfraError("REDIS_URL is not configured")
        if self._client is None:
            self._client = Redis.from_url(self.url, decode_responses=True)
        return self._client

    async def ping(self) -> bool:
        if not self.enabled:
            return False
        return bool(await self.client.ping())

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def register_run(self, metadata: RunMetadata) -> None:
        if not self.enabled:
            return
        key = f"loom:run:{metadata.run_id}"
        await self.client.hset(
            key,
            mapping={
                "run_id": metadata.run_id,
                "org_id": metadata.org_id,
                "repo_path": metadata.repo_path,
                "status": metadata.status,
                "sandbox_tier": metadata.sandbox_tier,
                "created_at": metadata.created_at,
            },
        )
        await self.client.expire(key, RUN_TTL_SECONDS)

    async def update_run_status(self, run_id: str, status: str) -> None:
        if not self.enabled:
            return
        key = f"loom:run:{run_id}"
        await self.client.hset(key, mapping={"status": status, "updated_at": time.time()})
        await self.client.expire(key, RUN_TTL_SECONDS)

    async def get_run(self, run_id: str) -> Optional[dict[str, str]]:
        if not self.enabled:
            return None
        data = await self.client.hgetall(f"loom:run:{run_id}")
        return data or None

    async def record_event(self, run_id: str, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        key = f"loom:run:{run_id}:events"
        payload = json.dumps(event, separators=(",", ":"), default=str)
        pipe = self.client.pipeline()
        pipe.rpush(key, payload)
        pipe.ltrim(key, -1000, -1)
        pipe.expire(key, EVENT_TTL_SECONDS)
        await pipe.execute()
        if event.get("type") == "status_change":
            status = event.get("data", {}).get("status")
            if status:
                await self.update_run_status(run_id, str(status))

    async def list_events(self, run_id: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        values = await self.client.lrange(f"loom:run:{run_id}:events", 0, -1)
        return [json.loads(value) for value in values]

    async def publish_control(self, run_id: str, action: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        message = json.dumps({"action": action, "payload": payload}, separators=(",", ":"), default=str)
        await self.client.publish(f"loom:run:{run_id}:control", message)

    async def control_stream(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        if not self.enabled:
            return
        pubsub = self.client.pubsub()
        await pubsub.subscribe(f"loom:run:{run_id}:control")
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(f"loom:run:{run_id}:control")
            await pubsub.aclose()


class RedisRateLimiter:
    """Atomic sliding-window rate limiter backed by a Redis sorted set."""

    def __init__(self, coordinator: RedisCoordinator):
        self.coordinator = coordinator
        self.limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        self.window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    async def allow(self, key: str) -> bool:
        if not self.coordinator.enabled:
            return True
        now = time.time()
        window_start = now - self.window_seconds
        redis = self.coordinator.client
        zkey = f"loom:ratelimit:{key}"
        member = f"{now:.6f}:{os.urandom(6).hex()}"
        pipe = redis.pipeline()
        pipe.zremrangebyscore(zkey, 0, window_start)
        pipe.zcard(zkey)
        pipe.zadd(zkey, {member: now})
        pipe.expire(zkey, self.window_seconds + 5)
        _, count, _, _ = await pipe.execute()
        if int(count) >= self.limit:
            await redis.zrem(zkey, member)
            return False
        return True

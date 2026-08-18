"""PRD-019 — Distributed Run State Store.

Replaces the process-local ACTIVE_RUNS dict with a Redis-backed store, enabling
multiple Loom API workers to share run state and SSE events.

Architecture:
  RedisRunStore      — stores run metadata (status, org_id, run_id) in Redis Hash
  RedisEventBus      — publishes/subscribes SSE events via Redis Pub/Sub channel
  LocalRunStore      — in-process fallback when Redis is unavailable (dev/test)
  get_run_store()    — factory: returns RedisRunStore if REDIS_URL set, else LocalRunStore

Usage in server.py:
    from loom.infra.run_state import get_run_store
    store = get_run_store()
    await store.set_run(run_id, {"status": "running", "org_id": org_id})
    async for event in store.event_bus.subscribe(run_id):
        yield event
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, AsyncIterator

logger = logging.getLogger("loom.infra.run_state")

# Redis key prefixes
_RUN_KEY = "loom:run:{run_id}"
_EVENT_CHANNEL = "loom:events:{run_id}"
_RUN_TTL = 86400 * 3  # 3 days


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class RunStore:
    """Abstract run metadata store."""

    async def set_run(self, run_id: str, metadata: dict[str, Any]) -> None:
        raise NotImplementedError

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def update_run(self, run_id: str, fields: dict[str, Any]) -> None:
        raise NotImplementedError

    async def delete_run(self, run_id: str) -> None:
        raise NotImplementedError

    async def publish_event(self, run_id: str, event: dict[str, Any]) -> None:
        raise NotImplementedError

    def subscribe_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Redis-backed store
# ---------------------------------------------------------------------------


class RedisRunStore(RunStore):
    """Redis-backed run store using hash for metadata and Pub/Sub for events.

    Requires redis[asyncio] to be installed and REDIS_URL to be set.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: Any = None
        self._loop: Any = None
        self._pubsub_client: Any = None

    async def _get_client(self) -> Any:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._client is None
            or (self._loop is not None and self._loop.is_closed())
            or (current_loop is not None and self._loop is not None and self._loop is not current_loop)
        ):
            try:
                from redis.asyncio import from_url
                self._client = from_url(self._redis_url, decode_responses=True)
                self._loop = current_loop
            except ImportError as exc:
                raise RuntimeError("redis[asyncio] is required for RedisRunStore") from exc
        elif self._loop is None and current_loop is not None:
            self._loop = current_loop
        return self._client

    async def set_run(self, run_id: str, metadata: dict[str, Any]) -> None:
        client = await self._get_client()
        key = _RUN_KEY.format(run_id=run_id)
        serialized = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in metadata.items()}
        await client.hset(key, mapping=serialized)
        await client.expire(key, _RUN_TTL)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        client = await self._get_client()
        key = _RUN_KEY.format(run_id=run_id)
        data = await client.hgetall(key)
        if not data:
            return None
        result: dict[str, Any] = {}
        for k, v in data.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result

    async def update_run(self, run_id: str, fields: dict[str, Any]) -> None:
        existing = await self.get_run(run_id)
        if existing is None:
            existing = {}
        existing.update(fields)
        await self.set_run(run_id, existing)

    async def delete_run(self, run_id: str) -> None:
        client = await self._get_client()
        await client.delete(_RUN_KEY.format(run_id=run_id))

    async def publish_event(self, run_id: str, event: dict[str, Any]) -> None:
        client = await self._get_client()
        channel = _EVENT_CHANNEL.format(run_id=run_id)
        await client.publish(channel, json.dumps(event))

    async def subscribe_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        from redis.asyncio import from_url
        sub_client = from_url(self._redis_url, decode_responses=True)
        pubsub = sub_client.pubsub()
        channel = _EVENT_CHANNEL.format(run_id=run_id)
        await pubsub.subscribe(channel)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
                if msg is not None and msg.get("type") == "message":
                    try:
                        event = json.loads(msg["data"])
                        yield event
                        if event.get("type") == "status_change" and event.get("data", {}).get("status") in (
                            "completed", "failed"
                        ):
                            break
                    except (json.JSONDecodeError, TypeError):
                        continue
                else:
                    # Yield a ping every 2 seconds when idle
                    yield {
                        "type": "ping",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "run_id": run_id,
                    }
        finally:
            await pubsub.unsubscribe(channel)
            await sub_client.aclose()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# In-process fallback store (used in dev / tests)
# ---------------------------------------------------------------------------


class LocalRunStore(RunStore):
    """In-process run store backed by a plain dict.

    Not suitable for multi-worker deployments.  Used when REDIS_URL is not set.
    """

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._queues: dict[str, list[asyncio.Queue]] = {}

    async def set_run(self, run_id: str, metadata: dict[str, Any]) -> None:
        self._runs[run_id] = dict(metadata)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return dict(self._runs[run_id]) if run_id in self._runs else None

    async def update_run(self, run_id: str, fields: dict[str, Any]) -> None:
        if run_id not in self._runs:
            self._runs[run_id] = {}
        self._runs[run_id].update(fields)

    async def delete_run(self, run_id: str) -> None:
        self._runs.pop(run_id, None)
        self._queues.pop(run_id, None)

    async def publish_event(self, run_id: str, event: dict[str, Any]) -> None:
        for q in list(self._queues.get(run_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._queues.setdefault(run_id, []).append(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield event
                    if event.get("type") == "status_change" and event.get("data", {}).get("status") in (
                        "completed", "failed"
                    ):
                        break
                except asyncio.TimeoutError:
                    yield {
                        "type": "ping",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "run_id": run_id,
                    }
        finally:
            queues = self._queues.get(run_id, [])
            if queue in queues:
                queues.remove(queue)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_store: RunStore | None = None


def get_run_store() -> RunStore:
    """Return the singleton RunStore.

    Uses RedisRunStore when REDIS_URL is set, otherwise LocalRunStore.
    """
    global _store
    if _store is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            logger.info("RunStore: using RedisRunStore at %s", redis_url)
            _store = RedisRunStore(redis_url)
        else:
            logger.info("RunStore: no REDIS_URL — using LocalRunStore (single-process only)")
            _store = LocalRunStore()
    return _store


def reset_run_store() -> None:
    """Test helper — reset the singleton."""
    global _store
    if _store is not None:
        # Best-effort sync close
        import asyncio as _aio
        try:
            loop = _aio.get_running_loop()
            if not loop.is_closed():
                loop.create_task(_store.close())
        except Exception:
            pass
    _store = None

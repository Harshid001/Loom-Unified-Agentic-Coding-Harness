"""PRD-019 — Integration Tests for Distributed Runtime State (Local and Redis).

Tests the RunStore abstraction (both LocalRunStore and RedisRunStore if Redis is available),
verifying:
  1. Setting, getting, updating, and deleting run metadata.
  2. Multi-worker / concurrent event publishing and subscription over SSE event bus.
  3. Proper fallback to LocalRunStore when REDIS_URL is not set.
  4. Cross-replica run state synchronization and event pub/sub when REDIS_URL is available.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loom.infra.run_state import (
    LocalRunStore,
    RedisRunStore,
    get_run_store,
    reset_run_store,
)


@pytest.mark.asyncio
async def test_local_run_store_lifecycle():
    store = LocalRunStore()
    run_id = "test_run_local_1"

    # 1. Set
    await store.set_run(run_id, {"status": "queued", "org_id": "org_123", "step": 1})
    data = await store.get_run(run_id)
    assert data is not None
    assert data["status"] == "queued"
    assert data["org_id"] == "org_123"

    # 2. Update
    await store.update_run(run_id, {"status": "running", "step": 2})
    data = await store.get_run(run_id)
    assert data["status"] == "running"
    assert data["step"] == 2
    assert data["org_id"] == "org_123"

    # 3. Delete
    await store.delete_run(run_id)
    data = await store.get_run(run_id)
    assert data is None


@pytest.mark.asyncio
async def test_local_run_store_event_bus():
    store = LocalRunStore()
    run_id = "test_run_events_1"
    received_events = []

    async def subscriber():
        async for evt in store.subscribe_events(run_id):
            if evt.get("type") == "ping":
                continue
            received_events.append(evt)
            if evt.get("type") == "status_change" and evt.get("data", {}).get("status") == "completed":
                break

    sub_task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.05)

    await store.publish_event(run_id, {"type": "step_progress", "data": {"step": "planner"}})
    await store.publish_event(run_id, {"type": "status_change", "data": {"status": "completed"}})

    await asyncio.wait_for(sub_task, timeout=2.0)
    assert len(received_events) == 2
    assert received_events[0]["type"] == "step_progress"
    assert received_events[1]["data"]["status"] == "completed"


def test_factory_fallback(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    reset_run_store()
    store = get_run_store()
    assert isinstance(store, LocalRunStore)
    reset_run_store()


def test_factory_selection_with_redis_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    reset_run_store()
    store = get_run_store()
    assert isinstance(store, RedisRunStore)
    reset_run_store()


@pytest.mark.asyncio
async def test_redis_run_store_unit_mocked():
    store = RedisRunStore("redis://localhost:6379/0")
    mock_redis = AsyncMock()
    mock_redis.hset = AsyncMock()
    mock_redis.expire = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={"status": '"running"', "org_id": "org_mock"})
    mock_redis.delete = AsyncMock()
    mock_redis.publish = AsyncMock()

    with patch.object(store, "_get_client", new=AsyncMock(return_value=mock_redis)):
        run_id = "run_redis_mock_1"
        await store.set_run(run_id, {"status": "running", "org_id": "org_mock"})
        assert mock_redis.hset.called
        assert mock_redis.expire.called

        data = await store.get_run(run_id)
        assert data is not None
        assert data["status"] == "running"
        assert data["org_id"] == "org_mock"

        await store.update_run(run_id, {"step": 3})
        assert mock_redis.hset.call_count == 2

        await store.delete_run(run_id)
        assert mock_redis.delete.called

        await store.publish_event(run_id, {"type": "step_progress", "data": {"step": "patcher"}})
        assert mock_redis.publish.called

        await store.close()


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="Requires live Redis instance via REDIS_URL")
@pytest.mark.asyncio
async def test_redis_run_store_lifecycle_live():
    redis_url = os.environ["REDIS_URL"]
    store = RedisRunStore(redis_url)
    run_id = f"test_run_redis_live_{int(asyncio.get_event_loop().time() * 1000)}"

    try:
        # 1. Set
        await store.set_run(run_id, {"status": "queued", "org_id": "org_redis_live", "step": 1})
        data = await store.get_run(run_id)
        assert data is not None
        assert data["status"] == "queued"
        assert data["org_id"] == "org_redis_live"

        # 2. Update
        await store.update_run(run_id, {"status": "running", "step": 2})
        data = await store.get_run(run_id)
        assert data["status"] == "running"
        assert data["step"] == 2
        assert data["org_id"] == "org_redis_live"

        # 3. Delete
        await store.delete_run(run_id)
        data = await store.get_run(run_id)
        assert data is None
    finally:
        await store.close()


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="Requires live Redis instance via REDIS_URL")
@pytest.mark.asyncio
async def test_redis_run_store_cross_replica_coordination_live():
    redis_url = os.environ["REDIS_URL"]
    # Simulate Replica A and Replica B
    replica_a = RedisRunStore(redis_url)
    replica_b = RedisRunStore(redis_url)
    run_id = f"test_run_replica_live_{int(asyncio.get_event_loop().time() * 1000)}"

    try:
        # Replica A creates the run
        await replica_a.set_run(run_id, {"status": "queued", "org_id": "org_replica", "step": 1})

        # Replica B reads the run created by Replica A
        data_b = await replica_b.get_run(run_id)
        assert data_b is not None
        assert data_b["status"] == "queued"

        # Replica B updates the status
        await replica_b.update_run(run_id, {"status": "running", "worker": "replica_b"})

        # Replica A reads the updated state from Replica B
        data_a = await replica_a.get_run(run_id)
        assert data_a["status"] == "running"
        assert data_a["worker"] == "replica_b"

        # Replica B subscribes to events while Replica A publishes
        received_events = []

        async def subscriber():
            async for evt in replica_b.subscribe_events(run_id):
                if evt.get("type") == "ping":
                    continue
                received_events.append(evt)
                if evt.get("type") == "status_change" and evt.get("data", {}).get("status") == "completed":
                    break

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        await replica_a.publish_event(run_id, {"type": "step_progress", "data": {"step": "patcher"}})
        await replica_a.publish_event(run_id, {"type": "status_change", "data": {"status": "completed"}})

        await asyncio.wait_for(sub_task, timeout=5.0)
        assert len(received_events) == 2
        assert received_events[0]["type"] == "step_progress"
        assert received_events[1]["data"]["status"] == "completed"

        # Cleanup
        await replica_a.delete_run(run_id)
    finally:
        await replica_a.close()
        await replica_b.close()


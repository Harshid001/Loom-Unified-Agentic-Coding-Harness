"""Tests for loom.infra.run_state."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from loom.infra.run_state import (
    LocalRunStore,
    RedisRunStore,
    get_run_store,
    reset_run_store,
)


@pytest.mark.asyncio
async def test_local_run_store_crud():
    store = LocalRunStore()
    run_id = "run_local_01"
    meta = {"status": "running", "org_id": "org_123", "model": "claude-3-7-sonnet"}

    # Set & Get
    await store.set_run(run_id, meta)
    res = await store.get_run(run_id)
    assert res is not None
    assert res["status"] == "running"
    assert res["org_id"] == "org_123"

    # Update
    await store.update_run(run_id, {"status": "completed", "duration": 42.0})
    updated = await store.get_run(run_id)
    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["duration"] == 42.0
    assert updated["org_id"] == "org_123"

    # Delete
    await store.delete_run(run_id)
    deleted = await store.get_run(run_id)
    assert deleted is None


@pytest.mark.asyncio
async def test_local_run_store_pubsub():
    store = LocalRunStore()
    run_id = "run_pubsub_01"

    received = []

    async def consumer():
        async for event in store.subscribe_events(run_id):
            received.append(event)
            if event.get("type") == "status_change":
                break

    consumer_task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)

    await store.publish_event(run_id, {"type": "log_entry", "msg": "step 1"})
    await store.publish_event(run_id, {"type": "status_change", "data": {"status": "completed"}})

    await asyncio.wait_for(consumer_task, timeout=2.0)
    assert len(received) >= 2
    assert received[0]["type"] == "log_entry"
    assert received[1]["type"] == "status_change"


@pytest.mark.asyncio
async def test_get_run_store_singleton(monkeypatch):
    reset_run_store()
    monkeypatch.delenv("REDIS_URL", raising=False)

    store1 = get_run_store()
    assert isinstance(store1, LocalRunStore)

    store2 = get_run_store()
    assert store1 is store2

    reset_run_store()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    store3 = get_run_store()
    assert isinstance(store3, RedisRunStore)
    reset_run_store()


@pytest.mark.asyncio
async def test_redis_run_store_mocked():
    store = RedisRunStore("redis://localhost:6379/0")

    mock_client = MagicMock()
    mock_client.hset = AsyncMock()
    mock_client.expire = AsyncMock()
    mock_client.hgetall = AsyncMock(return_value={"status": "running", "step_count": "5"})
    mock_client.delete = AsyncMock()
    mock_client.publish = AsyncMock()
    mock_client.aclose = AsyncMock()

    # _get_client() is async; preloading _client avoids an unnecessary patch and
    # preserves the real coroutine contract exercised by RedisRunStore.
    store._client = mock_client

    await store.set_run("run_mock_01", {"status": "running", "step_count": 5})
    mock_client.hset.assert_called_once()

    res = await store.get_run("run_mock_01")
    assert res is not None
    assert res["status"] == "running"
    assert res["step_count"] == 5

    await store.delete_run("run_mock_01")
    mock_client.delete.assert_called_once()

    await store.publish_event("run_mock_01", {"type": "ping"})
    mock_client.publish.assert_called_once()

    await store.close()
    mock_client.aclose.assert_called_once()

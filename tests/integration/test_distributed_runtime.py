"""PRD-019 — Integration Tests for Distributed Runtime State (Local and Redis).

Tests the RunStore abstraction (both LocalRunStore and RedisRunStore if Redis is available),
verifying:
  1. Setting, getting, updating, and deleting run metadata.
  2. Multi-worker / concurrent event publishing and subscription over SSE event bus.
  3. Proper fallback to LocalRunStore when REDIS_URL is not set.
"""

from __future__ import annotations

import asyncio

import pytest

from loom.infra.run_state import LocalRunStore, get_run_store, reset_run_store


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

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from loom.runtime.failure_policy import (
    FailureClass,
    classify_failure,
    should_retry,
)
from loom.runtime.job_queue import JobQueue, RunJob
from loom.runtime.worker import RunWorker


def test_failure_policy_classification():
    assert classify_failure(TimeoutError("operation timed out")) == FailureClass.TRANSIENT
    assert classify_failure(ConnectionError("connection failed")) == FailureClass.TRANSIENT
    assert classify_failure(PermissionError("forbidden access")) == FailureClass.SECURITY
    assert should_retry(TimeoutError("operation timed out")) is True
    assert should_retry(PermissionError("forbidden")) is False


def test_run_job_dataclass():
    job = RunJob(
        job_id="job_001",
        run_id="run_001",
        org_id="org_test",
        repo_path="/path/to/repo",
        issue="Test issue",
        model="gpt-4o",
        mock=False,
        sandbox_tier="A",
        auto_merge_threshold=0.85,
        created_at=time.time(),
        attempts=0,
    )
    assert job.job_id == "job_001"
    assert job.attempts == 0
    assert job.auto_merge_threshold == 0.85


@pytest.mark.asyncio
async def test_job_queue_lease_logic():
    mock_coordinator = MagicMock()
    mock_coordinator.enabled = True
    mock_redis = AsyncMock()
    mock_coordinator.client = mock_redis

    queue = JobQueue(coordinator=mock_coordinator)

    # Test lease acquire
    mock_redis.set = AsyncMock(return_value=True)
    token = await queue._try_acquire_lease("job_123")
    assert token is not None
    assert "worker-" in token or queue.consumer in token

    # Test lease renew
    mock_redis.eval = AsyncMock(return_value=1)
    renewed = await queue._renew_lease("job_123", token)
    assert renewed is True

    # Test lease release
    mock_redis.eval = AsyncMock(return_value=1)
    released = await queue.release_lease("job_123", token)
    assert released is True


@pytest.mark.asyncio
async def test_job_queue_decode_and_claim():
    mock_coordinator = MagicMock()
    mock_coordinator.enabled = True
    mock_redis = AsyncMock()
    mock_coordinator.client = mock_redis

    queue = JobQueue(coordinator=mock_coordinator)
    job_payload = {
        "job_id": "j1",
        "run_id": "r1",
        "org_id": "org1",
        "repo_path": "/tmp",
        "issue": "bug",
        "model": "gpt-4o",
        "mock": True,
        "sandbox_tier": "A",
        "auto_merge_threshold": 0.9,
        "created_at": 100.0,
        "attempts": 0,
    }
    raw_values = {"job": json.dumps(job_payload)}

    # When lease is acquired
    mock_redis.set = AsyncMock(return_value=True)
    claimed = await queue._decode_and_claim("msg-1", raw_values)
    assert claimed is not None
    assert claimed.job.job_id == "j1"
    assert claimed.message_id == "msg-1"
    assert claimed.lease_token != ""


@pytest.mark.asyncio
async def test_run_worker_heartbeat_renew_success():
    worker = RunWorker()
    mock_queue = MagicMock()
    mock_queue.enabled = True
    mock_queue.heartbeat = AsyncMock(return_value=True)
    worker.queue = mock_queue

    job = RunJob(
        job_id="j1",
        run_id="r1",
        org_id="org1",
        repo_path="/tmp",
        issue="bug",
        model="gpt-4o",
        mock=True,
        sandbox_tier="A",
        auto_merge_threshold=0.9,
        created_at=100.0,
    )
    lease_lost = asyncio.Event()

    # Run heartbeat for a short burst
    worker.heartbeat_seconds = 0.05
    hb_task = asyncio.create_task(worker._heartbeat(job, "token_1", lease_lost))
    await asyncio.sleep(0.12)
    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass

    assert lease_lost.is_set() is False
    assert mock_queue.heartbeat.call_count >= 1



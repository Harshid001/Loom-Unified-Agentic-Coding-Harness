"""Extended unit tests for loom.runtime.worker."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loom.runtime.job_queue import ClaimedJob, RunJob
from loom.runtime.worker import RunWorker, main


@pytest.fixture
def sample_job():
    return RunJob(
        job_id="job_test_001",
        run_id="run_test_001",
        org_id="org_test",
        repo_path="/workspace/test",
        issue="Test bug fix",
        model="gpt-4o",
        mock=True,
        sandbox_tier="A",
        auto_merge_threshold=0.85,
        created_at=1000.0,
        attempts=0,
    )


@pytest.mark.asyncio
async def test_worker_requires_redis():
    worker = RunWorker()
    worker.queue = MagicMock()
    worker.queue.enabled = False

    with pytest.raises(RuntimeError, match="Production worker requires REDIS_URL"):
        await worker.run_forever()


@pytest.mark.asyncio
async def test_worker_run_forever_success_flow(sample_job):
    worker = RunWorker()
    worker.poll_ms = 10
    worker.heartbeat_seconds = 1

    mock_queue = MagicMock()
    mock_queue.enabled = True
    mock_queue.consumer = "worker-test-1"
    mock_queue.ensure_group = AsyncMock()
    mock_queue.mark_worker_heartbeat = AsyncMock()
    mock_queue.mark_started = AsyncMock()
    mock_queue.mark_finished = AsyncMock()
    mock_queue.ack = AsyncMock()
    mock_queue.release_lease = AsyncMock()
    mock_queue.heartbeat = AsyncMock(return_value=True)

    claimed = ClaimedJob(message_id="msg-1", lease_token="lease-tok-1", job=sample_job)

    call_count = 0

    async def fake_claim(timeout_ms):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return claimed
        worker._stop = True
        return None

    mock_queue.claim = fake_claim
    worker.queue = mock_queue

    with patch("loom.runtime.worker.execute_run_job", new=AsyncMock(return_value=MagicMock())):
        await worker.run_forever()

    mock_queue.ensure_group.assert_awaited_once()
    mock_queue.mark_started.assert_awaited_once_with(sample_job, "lease-tok-1")
    mock_queue.mark_finished.assert_awaited_once_with(sample_job, "succeeded")
    mock_queue.ack.assert_awaited_once_with("msg-1")
    mock_queue.release_lease.assert_awaited_once_with("job_test_001", "lease-tok-1")


@pytest.mark.asyncio
async def test_worker_run_forever_transient_failure_retries(sample_job):
    worker = RunWorker()
    worker.poll_ms = 10
    worker.max_attempts = 3

    mock_queue = MagicMock()
    mock_queue.enabled = True
    mock_queue.consumer = "worker-test-1"
    mock_queue.ensure_group = AsyncMock()
    mock_queue.mark_worker_heartbeat = AsyncMock()
    mock_queue.mark_started = AsyncMock()
    mock_queue.mark_finished = AsyncMock()
    mock_queue.enqueue = AsyncMock()
    mock_queue.ack = AsyncMock()
    mock_queue.release_lease = AsyncMock()
    mock_queue.heartbeat = AsyncMock(return_value=True)

    claimed = ClaimedJob(message_id="msg-retry", lease_token="lease-tok-retry", job=sample_job)

    call_count = 0

    async def fake_claim(timeout_ms):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return claimed
        worker._stop = True
        return None

    mock_queue.claim = fake_claim
    worker.queue = mock_queue

    # Simulate a retryable transient error (TimeoutError)
    with patch("loom.runtime.worker.execute_run_job", side_effect=TimeoutError("network timeout")):
        await worker.run_forever()

    mock_queue.mark_finished.assert_awaited_once_with(sample_job, "retrying", "execution failed")
    mock_queue.enqueue.assert_awaited_once()
    retry_job = mock_queue.enqueue.call_args[0][0]
    assert retry_job.attempts == 1
    assert "retry:1" in retry_job.job_id
    mock_queue.ack.assert_awaited_once_with("msg-retry")


@pytest.mark.asyncio
async def test_worker_run_forever_dead_letter_on_max_attempts(sample_job):
    import dataclasses
    max_attempts_job = dataclasses.replace(sample_job, attempts=2)
    worker = RunWorker()
    worker.poll_ms = 10
    worker.max_attempts = 3

    mock_queue = MagicMock()
    mock_queue.enabled = True
    mock_queue.consumer = "worker-test-1"
    mock_queue.ensure_group = AsyncMock()
    mock_queue.mark_worker_heartbeat = AsyncMock()
    mock_queue.mark_started = AsyncMock()
    mock_queue.mark_finished = AsyncMock()
    mock_queue.dead_letter = AsyncMock()
    mock_queue.ack = AsyncMock()
    mock_queue.release_lease = AsyncMock()
    mock_queue.heartbeat = AsyncMock(return_value=True)

    claimed = ClaimedJob(message_id="msg-dlq", lease_token="lease-tok-dlq", job=max_attempts_job)

    call_count = 0

    async def fake_claim(timeout_ms):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return claimed
        worker._stop = True
        return None

    mock_queue.claim = fake_claim
    worker.queue = mock_queue

    with patch("loom.runtime.worker.execute_run_job", side_effect=TimeoutError("network timeout")):
        await worker.run_forever()

    mock_queue.mark_finished.assert_awaited_once_with(max_attempts_job, "dead_letter", "execution failed")
    mock_queue.dead_letter.assert_awaited_once()
    mock_queue.ack.assert_awaited_once_with("msg-dlq")


@pytest.mark.asyncio
async def test_worker_run_forever_dead_letter_on_non_retryable_fatal_error(sample_job):
    worker = RunWorker()
    worker.poll_ms = 10
    worker.max_attempts = 3

    mock_queue = MagicMock()
    mock_queue.enabled = True
    mock_queue.consumer = "worker-test-1"
    mock_queue.ensure_group = AsyncMock()
    mock_queue.mark_worker_heartbeat = AsyncMock()
    mock_queue.mark_started = AsyncMock()
    mock_queue.mark_finished = AsyncMock()
    mock_queue.dead_letter = AsyncMock()
    mock_queue.enqueue = AsyncMock()
    mock_queue.ack = AsyncMock()
    mock_queue.release_lease = AsyncMock()
    mock_queue.heartbeat = AsyncMock(return_value=True)

    claimed = ClaimedJob(message_id="msg-fatal", lease_token="lease-tok-fatal", job=sample_job)

    call_count = 0

    async def fake_claim(timeout_ms):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return claimed
        worker._stop = True
        return None

    mock_queue.claim = fake_claim
    worker.queue = mock_queue

    # Simulate non-retryable PermissionError (classified as SECURITY)
    with patch("loom.runtime.worker.execute_run_job", side_effect=PermissionError("access forbidden: invalid security token")):
        await worker.run_forever()

    mock_queue.mark_finished.assert_awaited_once_with(sample_job, "dead_letter", "execution failed")
    mock_queue.dead_letter.assert_awaited_once()
    mock_queue.ack.assert_awaited_once_with("msg-fatal")


@pytest.mark.asyncio
async def test_worker_lease_loss_triggers_lease_lost_and_cancels(sample_job):
    worker = RunWorker()
    worker.poll_ms = 10
    worker.heartbeat_seconds = 0.01

    mock_queue = MagicMock()
    mock_queue.enabled = True
    mock_queue.consumer = "worker-test-1"
    mock_queue.ensure_group = AsyncMock()
    mock_queue.mark_worker_heartbeat = AsyncMock()
    mock_queue.mark_started = AsyncMock()
    mock_queue.mark_finished = AsyncMock()
    mock_queue.dead_letter = AsyncMock()
    mock_queue.enqueue = AsyncMock()
    mock_queue.ack = AsyncMock()
    mock_queue.release_lease = AsyncMock()
    # Heartbeat returns False (lease lost to another worker)
    mock_queue.heartbeat = AsyncMock(return_value=False)

    claimed = ClaimedJob(message_id="msg-lease-lost", lease_token="lease-tok-lost", job=sample_job)

    call_count = 0

    async def fake_claim(timeout_ms):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return claimed
        worker._stop = True
        return None

    mock_queue.claim = fake_claim
    worker.queue = mock_queue

    async def slow_execution(job):
        await asyncio.sleep(5.0)

    with patch("loom.runtime.worker.execute_run_job", side_effect=slow_execution):
        await worker.run_forever()

    # Should have attempted to release lease or dead letter
    assert mock_queue.release_lease.called


@pytest.mark.asyncio
async def test_worker_main_entrypoint():
    with patch("loom.runtime.worker.RunWorker") as mock_worker_cls:
        mock_inst = MagicMock()
        mock_inst.run_forever = AsyncMock()
        mock_worker_cls.return_value = mock_inst
        await main()
        mock_inst.run_forever.assert_awaited_once()


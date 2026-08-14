import json

import pytest

from loom.runtime.job_queue import JobQueue, RunJob


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.streams = []

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def eval(self, script, numkeys, key, token, ttl=None):
        current = self.values.get(key)
        if current != token:
            return 0
        if "del" in script:
            del self.values[key]
            return 1
        return 1


class FakeCoordinator:
    enabled = True

    def __init__(self):
        self.client = FakeRedis()


@pytest.mark.asyncio
async def test_only_one_worker_can_acquire_job_lease():
    coordinator = FakeCoordinator()
    queue_a = JobQueue(coordinator=coordinator)
    queue_b = JobQueue(coordinator=coordinator)
    queue_a.consumer = "worker-a"
    queue_b.consumer = "worker-b"

    token_a = await queue_a._try_acquire_lease("job-1")
    token_b = await queue_b._try_acquire_lease("job-1")

    assert token_a is not None
    assert token_b is None


@pytest.mark.asyncio
async def test_lease_renewal_requires_current_token():
    coordinator = FakeCoordinator()
    queue = JobQueue(coordinator=coordinator)
    token = await queue._try_acquire_lease("job-2")
    assert token is not None
    assert await queue._renew_lease("job-2", token) is True
    assert await queue._renew_lease("job-2", "stale-token") is False


@pytest.mark.asyncio
async def test_dead_letter_is_written_to_dedicated_stream():
    class StreamRedis(FakeRedis):
        async def xadd(self, stream, values, **kwargs):
            self.streams.append((stream, values))
            return "1-0"

    coordinator = FakeCoordinator()
    coordinator.client = StreamRedis()
    queue = JobQueue(coordinator=coordinator)
    job = RunJob(
        job_id="job-3",
        run_id="run-3",
        org_id="org-1",
        repo_path="/repo",
        issue="issue",
        model=None,
        mock=False,
        sandbox_tier="A",
        auto_merge_threshold=0.9,
        created_at=1.0,
        attempts=2,
    )

    await queue.dead_letter(job, "failure")

    stream, values = coordinator.client.streams[0]
    assert stream == queue.DEAD_LETTER_STREAM
    payload = json.loads(values["job"])
    assert payload["job"]["run_id"] == "run-3"
    assert payload["reason"] == "failure"

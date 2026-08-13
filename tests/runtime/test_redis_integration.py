from __future__ import annotations

import os
import uuid

import pytest

from loom.infra.distributed import RedisCoordinator
from loom.runtime.job_queue import JobQueue, RunJob


pytestmark = pytest.mark.asyncio


async def test_redis_idempotency_and_job_queue_round_trip() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL is not configured")

    coordinator = RedisCoordinator(redis_url)
    assert await coordinator.ping()

    suffix = uuid.uuid4().hex[:12]
    org_id = f"ci-org-{suffix}"
    idempotency_key = f"ci-idempotency-{suffix}"
    run_id = f"run_ci_{suffix}"

    try:
        assert await coordinator.reserve_idempotency_key(org_id, idempotency_key, run_id)
        assert not await coordinator.reserve_idempotency_key(org_id, idempotency_key, f"run_other_{suffix}")
        assert await coordinator.get_idempotent_run(org_id, idempotency_key) == run_id

        queue = JobQueue(coordinator)
        await coordinator.client.delete(queue.STREAM)
        await queue.ensure_group()

        job = RunJob(
            job_id=f"job_ci_{suffix}",
            run_id=run_id,
            org_id=org_id,
            repo_path="/workspace/example",
            issue="integration-test",
            model="mock",
            mock=True,
            sandbox_tier="B",
            auto_merge_threshold=0.95,
            created_at=1.0,
        )

        await queue.enqueue(job)
        claimed = await queue.claim(block_ms=1000)
        assert claimed is not None
        assert claimed.job.run_id == run_id
        assert claimed.job.job_id == job.job_id

        await queue.mark_started(claimed.job)
        metadata = await coordinator.client.hgetall(f"loom:job:{job.job_id}")
        assert metadata["status"] == "running"

        await queue.ack(claimed.message_id)
        await queue.mark_finished(claimed.job, "succeeded")
        final_metadata = await coordinator.client.hgetall(f"loom:job:{job.job_id}")
        assert final_metadata["status"] == "succeeded"
    finally:
        await coordinator.client.delete(f"loom:idempotency:{org_id}:{idempotency_key}")
        await coordinator.client.delete(f"loom:job:{job.job_id}")
        await coordinator.client.delete(JobQueue.STREAM)
        await coordinator.close()

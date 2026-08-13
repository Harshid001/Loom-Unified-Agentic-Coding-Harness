"""Durable Redis-backed job queue for production run execution."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Optional

from loom.infra.distributed import RedisCoordinator


@dataclass(frozen=True)
class RunJob:
    job_id: str
    run_id: str
    org_id: str
    repo_path: str
    issue: str
    model: Optional[str]
    mock: bool
    sandbox_tier: str
    auto_merge_threshold: float
    created_at: float
    attempts: int = 0


@dataclass(frozen=True)
class ClaimedJob:
    job: RunJob
    message_id: str


class JobQueue:
    """Redis Streams queue with consumer groups and explicit job state."""

    STREAM = "loom:jobs"
    GROUP = "loom-workers"

    def __init__(self, coordinator: Optional[RedisCoordinator] = None) -> None:
        self.coordinator = coordinator or RedisCoordinator()
        self.consumer = os.getenv("LOOM_WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
        self.visibility_timeout = int(os.getenv("LOOM_JOB_VISIBILITY_TIMEOUT", "300"))

    @property
    def enabled(self) -> bool:
        return self.coordinator.enabled

    async def ensure_group(self) -> None:
        if not self.enabled:
            raise RuntimeError("Production job queue requires REDIS_URL")
        try:
            await self.coordinator.client.xgroup_create(self.STREAM, self.GROUP, id="0-0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(self, job: RunJob) -> str:
        await self.ensure_group()
        payload = json.dumps(asdict(job), separators=(",", ":"), default=str)
        await self.coordinator.client.xadd(self.STREAM, {"job": payload}, maxlen=100000, approximate=True)
        await self.coordinator.client.hset(
            f"loom:job:{job.job_id}",
            mapping={"run_id": job.run_id, "status": "queued", "attempts": job.attempts, "created_at": job.created_at},
        )
        await self.coordinator.client.expire(f"loom:job:{job.job_id}", 7 * 24 * 3600)
        return job.job_id

    async def claim(self, block_ms: int = 5000) -> Optional[ClaimedJob]:
        await self.ensure_group()
        result = await self.coordinator.client.xreadgroup(
            self.GROUP,
            self.consumer,
            {self.STREAM: ">"},
            count=1,
            block=block_ms,
        )
        if not result:
            return None
        _, messages = result[0]
        message_id, values = messages[0]
        raw = values.get("job")
        if not raw:
            await self.ack(message_id)
            return None
        data: dict[str, Any] = json.loads(raw)
        job = RunJob(**data)
        return ClaimedJob(job=job, message_id=message_id)

    async def ack(self, message_id: str) -> None:
        await self.coordinator.client.xack(self.STREAM, self.GROUP, message_id)

    async def mark_started(self, job: RunJob) -> None:
        key = f"loom:job:{job.job_id}"
        await self.coordinator.client.hset(
            key,
            mapping={
                "run_id": job.run_id,
                "status": "running",
                "worker_id": self.consumer,
                "attempts": job.attempts,
                "started_at": time.time(),
            },
        )
        await self.coordinator.client.expire(key, self.visibility_timeout)

    async def heartbeat(self, job: RunJob) -> None:
        key = f"loom:job:{job.job_id}"
        await self.coordinator.client.hset(key, "heartbeat_at", time.time())
        await self.coordinator.client.expire(key, self.visibility_timeout)

    async def mark_finished(self, job: RunJob, status: str, error: str = "") -> None:
        key = f"loom:job:{job.job_id}"
        await self.coordinator.client.hset(
            key,
            mapping={"status": status, "completed_at": time.time(), "error": error},
        )
        await self.coordinator.client.expire(key, 7 * 24 * 3600)

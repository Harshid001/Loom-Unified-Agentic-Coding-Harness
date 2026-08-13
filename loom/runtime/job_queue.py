"""Durable Redis-backed job queue for production run execution."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
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


class JobQueue:
    """Redis Streams queue with consumer-group delivery and explicit leases."""

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
        return job.job_id

    async def claim(self, block_ms: int = 5000) -> Optional[RunJob]:
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
        return RunJob(**data)

    async def ack(self, message_id: str) -> None:
        await self.coordinator.client.xack(self.STREAM, self.GROUP, message_id)

    async def heartbeat(self, job_id: str) -> None:
        await self.coordinator.client.hset(
            f"loom:job:{job_id}",
            mapping={"heartbeat_at": time.time(), "worker_id": self.consumer},
        )
        await self.coordinator.client.expire(f"loom:job:{job_id}", self.visibility_timeout)

    async def mark_started(self, job: RunJob) -> None:
        await self.coordinator.client.hset(
            f"loom:job:{job.job_id}",
            mapping={
                "run_id": job.run_id,
                "status": "running",
                "worker_id": self.consumer,
                "attempts": job.attempts,
                "started_at": time.time(),
            },
        )
        await self.coordinator.client.expire(f"loom:job:{job.job_id}", self.visibility_timeout)

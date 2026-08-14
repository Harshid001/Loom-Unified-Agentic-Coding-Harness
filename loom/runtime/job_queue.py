"""Durable Redis-backed job queue for production run execution."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Optional, cast

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
    lease_token: str = ""


class JobQueue:
    """Redis Streams queue with a renewable per-job lease and crash recovery."""

    STREAM = "loom:jobs"
    GROUP = "loom-workers"
    DEAD_LETTER_STREAM = "loom:jobs:dead-letter"
    LEASE_PREFIX = "loom:job-lease:"

    def __init__(self, coordinator: Optional[RedisCoordinator] = None) -> None:
        self.coordinator = coordinator or RedisCoordinator()
        self.consumer = os.getenv("LOOM_WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
        self.visibility_timeout = int(os.getenv("LOOM_JOB_VISIBILITY_TIMEOUT", "300"))
        self.lease_ttl = int(os.getenv("LOOM_JOB_LEASE_TTL", str(max(self.visibility_timeout, 120))))

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

    def _lease_key(self, job_id: str) -> str:
        return f"{self.LEASE_PREFIX}{job_id}"

    async def _try_acquire_lease(self, job_id: str) -> str | None:
        token = f"{self.consumer}:{uuid.uuid4().hex}"
        acquired = await self.coordinator.client.set(self._lease_key(job_id), token, nx=True, ex=self.lease_ttl)
        return token if acquired else None

    async def _renew_lease(self, job_id: str, token: str) -> bool:
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
        result = await self.coordinator.client.eval(script, 1, self._lease_key(job_id), token, str(self.lease_ttl))
        return bool(result)

    async def release_lease(self, job_id: str, token: str) -> bool:
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        result = await self.coordinator.client.eval(script, 1, self._lease_key(job_id), token)
        return bool(result)

    async def enqueue(self, job: RunJob) -> str:
        await self.ensure_group()
        payload = json.dumps(asdict(job), separators=(",", ":"), default=str)
        await self.coordinator.client.xadd(self.STREAM, {"job": payload}, maxlen=100000, approximate=True)
        key = f"loom:job:{job.job_id}"
        await self.coordinator.client.hset(key, mapping={"run_id": job.run_id, "status": "queued", "attempts": job.attempts, "created_at": job.created_at})
        await self.coordinator.client.expire(key, 7 * 24 * 3600)
        return job.job_id

    async def dead_letter(self, job: RunJob, reason: str) -> None:
        payload = json.dumps({"job": asdict(job), "reason": reason, "dead_lettered_at": time.time()}, default=str)
        await self.coordinator.client.xadd(self.DEAD_LETTER_STREAM, {"job": payload}, maxlen=10000, approximate=True)

    async def _decode_and_claim(self, message_id: str, values: Any) -> Optional[ClaimedJob]:
        raw = values.get("job") if isinstance(values, dict) else None
        if not raw:
            await self.ack(str(message_id))
            return None
        job = RunJob(**json.loads(str(raw)))
        lease_token = await self._try_acquire_lease(job.job_id)
        if lease_token is None:
            return None
        return ClaimedJob(job=job, message_id=str(message_id), lease_token=lease_token)

    async def claim(self, block_ms: int = 5000) -> Optional[ClaimedJob]:
        await self.ensure_group()
        try:
            claimed = cast(Any, await self.coordinator.client.xautoclaim(self.STREAM, self.GROUP, self.consumer, min_idle_time=self.visibility_timeout * 1000, start_id="0-0", count=10))
            messages = claimed[1] if isinstance(claimed, (list, tuple)) and len(claimed) > 1 else []
            for message_id, values in messages:
                result = await self._decode_and_claim(str(message_id), values)
                if result is not None:
                    return result
        except Exception:
            pass

        result = cast(Any, await self.coordinator.client.xreadgroup(self.GROUP, self.consumer, {self.STREAM: ">"}, count=1, block=block_ms))
        if not result:
            return None
        stream_messages = result[0]
        if not isinstance(stream_messages, (list, tuple)) or len(stream_messages) < 2:
            return None
        messages = stream_messages[1]
        if not isinstance(messages, (list, tuple)) or not messages:
            return None
        first_message = messages[0]
        if not isinstance(first_message, (list, tuple)) or len(first_message) < 2:
            return None
        return await self._decode_and_claim(str(first_message[0]), first_message[1])

    async def ack(self, message_id: str) -> None:
        await self.coordinator.client.xack(self.STREAM, self.GROUP, message_id)

    async def mark_worker_heartbeat(self) -> None:
        key = f"loom:worker:{self.consumer}"
        await self.coordinator.client.hset(key, mapping={"worker_id": self.consumer, "heartbeat_at": time.time()})
        await self.coordinator.client.expire(key, max(self.visibility_timeout, 120))

    async def mark_started(self, job: RunJob, lease_token: str = "") -> None:
        key = f"loom:job:{job.job_id}"
        await self.coordinator.client.hset(key, mapping={"run_id": job.run_id, "status": "running", "worker_id": self.consumer, "attempts": job.attempts, "started_at": time.time()})
        await self.coordinator.client.expire(key, 7 * 24 * 3600)
        if lease_token and not await self._renew_lease(job.job_id, lease_token):
            raise RuntimeError(f"Lost execution lease for job {job.job_id}")

    async def heartbeat(self, job: RunJob, lease_token: str = "") -> bool:
        key = f"loom:job:{job.job_id}"
        await self.coordinator.client.hset(key, "heartbeat_at", time.time())
        await self.coordinator.client.expire(key, 7 * 24 * 3600)
        await self.mark_worker_heartbeat()
        if not lease_token:
            return True
        return await self._renew_lease(job.job_id, lease_token)

    async def mark_finished(self, job: RunJob, status: str, error: str = "") -> None:
        key = f"loom:job:{job.job_id}"
        await self.coordinator.client.hset(key, mapping={"status": status, "completed_at": time.time(), "error": error})
        await self.coordinator.client.expire(key, 7 * 24 * 3600)

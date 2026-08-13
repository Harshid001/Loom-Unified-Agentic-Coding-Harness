"""Operational health endpoints for distributed Loom deployments."""

from __future__ import annotations

import time
from typing import Any

from fastapi import Depends, FastAPI

from loom.infra.distributed import RedisCoordinator
from loom.runtime.job_queue import JobQueue


def install_distributed_health(app: FastAPI, verify_auth: Any) -> None:
    coordinator = RedisCoordinator()

    @app.get("/api/v1/health/distributed", dependencies=[Depends(verify_auth)])
    async def distributed_health() -> dict[str, Any]:
        if not coordinator.enabled:
            return {"status": "degraded", "redis": "not_configured", "queue": "unavailable"}

        redis_ok = await coordinator.ping()
        if not redis_ok:
            return {"status": "unhealthy", "redis": "unreachable", "queue": "unavailable"}

        queue = JobQueue(coordinator)
        pending = await coordinator.client.xpending(queue.STREAM, queue.GROUP)
        queue_length = await coordinator.client.xlen(queue.STREAM)
        consumer_groups = await coordinator.client.xinfo_consumers(queue.STREAM, queue.GROUP)

        active_workers = 0
        now = time.time()
        async for key in coordinator.client.scan_iter(match="loom:worker:*"):
            heartbeat = await coordinator.client.hget(key, "heartbeat_at")
            if heartbeat and now - float(heartbeat) <= max(queue.visibility_timeout, 120):
                active_workers += 1

        status = "healthy" if active_workers > 0 else "degraded"
        return {
            "status": status,
            "redis": "ok",
            "queue": {
                "length": int(queue_length),
                "pending": int(pending[0]) if pending else 0,
                "consumers": len(consumer_groups),
                "active_workers": active_workers,
            },
        }

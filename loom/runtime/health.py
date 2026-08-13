"""Operational health endpoints for distributed Loom deployments."""

from __future__ import annotations

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

        return {
            "status": "healthy",
            "redis": "ok",
            "queue": {
                "length": int(queue_length),
                "pending": int(pending[0]) if pending else 0,
                "consumers": len(consumer_groups),
            },
        }

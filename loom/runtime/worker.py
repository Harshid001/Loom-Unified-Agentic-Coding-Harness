"""Durable production worker for queued Loom runs."""

from __future__ import annotations

import asyncio
import logging
import os

from loom.runtime.executor import execute_run_job
from loom.runtime.failure_policy import classify_failure, should_retry
from loom.runtime.job_queue import JobQueue, RunJob

logger = logging.getLogger("loom.runtime.worker")


class RunWorker:
    def __init__(self) -> None:
        self.queue = JobQueue()
        self.max_attempts = int(os.getenv("LOOM_JOB_MAX_ATTEMPTS", "3"))
        self.poll_ms = int(os.getenv("LOOM_JOB_POLL_MS", "5000"))
        self.heartbeat_seconds = int(os.getenv("LOOM_JOB_HEARTBEAT_SECONDS", "30"))
        self._stop = False

    async def run_forever(self) -> None:
        if not self.queue.enabled:
            raise RuntimeError("Production worker requires REDIS_URL")
        await self.queue.ensure_group()
        logger.info("Loom worker %s started", self.queue.consumer)
        idle_heartbeat = asyncio.create_task(self._idle_heartbeat())
        try:
            while not self._stop:
                claimed = await self.queue.claim(self.poll_ms)
                if claimed is None:
                    continue
                job = claimed.job
                heartbeat = asyncio.create_task(self._heartbeat(job, claimed.lease_token))
                try:
                    await self.queue.mark_started(job, claimed.lease_token)
                    await execute_run_job(job)
                    await self.queue.mark_finished(job, "succeeded")
                    await self.queue.ack(claimed.message_id)
                except Exception as exc:
                    failure_class = classify_failure(exc)
                    next_attempt = job.attempts + 1
                    logger.exception(
                        "Run %s failed on attempt %s with class %s",
                        job.run_id,
                        next_attempt,
                        failure_class.value,
                    )
                    if not should_retry(exc) or next_attempt >= self.max_attempts:
                        await self.queue.mark_finished(job, "dead_letter", str(exc))
                        await self.queue.ack(claimed.message_id)
                    else:
                        await self.queue.mark_finished(job, "retrying", str(exc))
                        await self.queue.enqueue(
                            RunJob(
                                job_id=f"{job.job_id}:retry:{next_attempt}",
                                run_id=job.run_id,
                                org_id=job.org_id,
                                repo_path=job.repo_path,
                                issue=job.issue,
                                model=job.model,
                                mock=job.mock,
                                sandbox_tier=job.sandbox_tier,
                                auto_merge_threshold=job.auto_merge_threshold,
                                created_at=job.created_at,
                                attempts=next_attempt,
                            )
                        )
                        await self.queue.ack(claimed.message_id)
                finally:
                    heartbeat.cancel()
                    try:
                        await heartbeat
                    except asyncio.CancelledError:
                        pass
                    await self.queue.release_lease(job.job_id, claimed.lease_token)
        finally:
            idle_heartbeat.cancel()
            try:
                await idle_heartbeat
            except asyncio.CancelledError:
                pass

    async def _idle_heartbeat(self) -> None:
        while True:
            await self.queue.mark_worker_heartbeat()
            await asyncio.sleep(self.heartbeat_seconds)

    async def _heartbeat(self, job: RunJob, lease_token: str) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            if not await self.queue._renew_lease(job.job_id, lease_token):
                logger.critical("Execution lease lost for run %s", job.run_id)
                return
            await self.queue.heartbeat(job, lease_token)


async def main() -> None:
    await RunWorker().run_forever()


if __name__ == "__main__":
    asyncio.run(main())

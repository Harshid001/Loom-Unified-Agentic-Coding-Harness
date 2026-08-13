"""Durable production worker for queued Loom runs."""

from __future__ import annotations

import asyncio
import logging
import os

from loom.runtime.executor import execute_run_job
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
        while not self._stop:
            claimed = await self.queue.claim(self.poll_ms)
            if claimed is None:
                continue
            job = claimed.job
            heartbeat = asyncio.create_task(self._heartbeat(job))
            await self.queue.mark_started(job)
            try:
                await execute_run_job(job)
                await self.queue.mark_finished(job, "succeeded")
                await self.queue.ack(claimed.message_id)
            except Exception as exc:
                next_attempt = job.attempts + 1
                logger.exception("Run %s failed on attempt %s", job.run_id, next_attempt)
                if next_attempt >= self.max_attempts:
                    await self.queue.mark_finished(job, "dead_letter", str(exc))
                    await self.queue.ack(claimed.message_id)
                else:
                    await self.queue.mark_finished(job, "retrying", str(exc))
                    await self.queue.enqueue(
                        RunJob(
                            job_id=job.job_id,
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

    async def _heartbeat(self, job: RunJob) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            await self.queue.heartbeat(job)


async def main() -> None:
    await RunWorker().run_forever()


if __name__ == "__main__":
    asyncio.run(main())

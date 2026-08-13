from dataclasses import asdict

import pytest

from loom.runtime.job_queue import RunJob


def test_run_job_round_trips_as_json_payload():
    job = RunJob(
        job_id="job_123",
        run_id="run_123",
        org_id="org_1",
        repo_path="/workspace/repo",
        issue="fix failing test",
        model="gpt-4o",
        mock=True,
        sandbox_tier="B",
        auto_merge_threshold=0.9,
        created_at=123.0,
        attempts=1,
    )
    assert asdict(job)["run_id"] == "run_123"
    assert asdict(job)["attempts"] == 1


def test_production_queue_requires_redis(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)

    from loom.runtime.job_queue import JobQueue

    queue = JobQueue()
    assert queue.enabled is False
    with pytest.raises(RuntimeError, match="requires REDIS_URL"):
        __import__("asyncio").run(queue.ensure_group())


def test_worker_module_imports_without_starting(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    from loom.runtime.worker import RunWorker

    worker = RunWorker()
    assert worker.max_attempts >= 1
    assert worker.queue.enabled is True

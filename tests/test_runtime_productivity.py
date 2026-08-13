from __future__ import annotations

from loom.runtime.budget import RunBudget
from loom.runtime.job_queue import RunJob


def test_run_budget_reads_explicit_environment(monkeypatch):
    monkeypatch.setenv("LOOM_MAX_RUN_COST_USD", "4.25")
    monkeypatch.setenv("LOOM_MAX_RUN_DURATION_SECONDS", "1200")
    monkeypatch.setenv("LOOM_MAX_RUN_TOKENS", "250000")

    budget = RunBudget.from_env()

    assert budget.max_cost_usd == 4.25
    assert budget.max_duration_seconds == 1200
    assert budget.max_tokens == 250000


def test_run_job_is_serializable():
    job = RunJob(
        job_id="job_test",
        run_id="run_test",
        org_id="org_test",
        repo_path="/workspace/repo",
        issue="fix test",
        model="mock/model",
        mock=True,
        sandbox_tier="B",
        auto_merge_threshold=0.95,
        created_at=123.0,
    )

    assert job.run_id == "run_test"
    assert job.sandbox_tier == "B"
    assert job.attempts == 0

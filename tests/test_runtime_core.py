from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loom.runtime.backup import upload_backup_to_object_storage
from loom.runtime.budget import BudgetExceeded, RunBudget, cost_from_summary, tokens_from_summary
from loom.runtime.failure_policy import FailureClass, classify_failure, should_retry
from loom.runtime.health import install_distributed_health
from loom.runtime.job_queue import RunJob
from loom.runtime.run_state_store import (
    InvalidRunTransition,
    RunState,
    RunStateRecord,
    heartbeat,
    transition,
)


def test_failure_policy_classification():
    assert classify_failure(RuntimeError("Rate limit exceeded (429)")) == FailureClass.RATE_LIMIT
    assert classify_failure(RuntimeError("Budget exceeded")) == FailureClass.BUDGET_EXCEEDED
    assert classify_failure(PermissionError("Forbidden security boundary")) == FailureClass.SECURITY
    assert classify_failure(ValueError("Configuration missing required key")) == FailureClass.CONFIGURATION
    assert classify_failure(ValueError("Invalid input parameter")) == FailureClass.INVALID_INPUT
    assert classify_failure(RuntimeError("Firecracker microvm sandbox crashed")) == FailureClass.SANDBOX
    assert classify_failure(RuntimeError("Git patch apply conflict detected")) == FailureClass.PATCH_CONFLICT
    assert classify_failure(TimeoutError("Connection timed out after 30s")) == FailureClass.TRANSIENT
    assert classify_failure(Exception("Something unexpected")) == FailureClass.UNKNOWN

    assert not should_retry(RuntimeError("Budget exceeded"))
    assert not should_retry(PermissionError("Forbidden security boundary"))
    assert not should_retry(ValueError("Configuration missing"))
    assert not should_retry(ValueError("Invalid input"))
    assert should_retry(TimeoutError("Connection timed out"))
    assert should_retry(RuntimeError("Rate limit exceeded"))


def test_budget_checks():
    budget = RunBudget(
        max_cost_usd=10.0,
        max_duration_seconds=100.0,
        max_tokens=5000,
        max_agent_steps=5,
    )

    # Valid limits
    budget.check_limits(cost_usd=5.0, elapsed_seconds=50.0, tokens_used=1000, agent_steps=2)

    with pytest.raises(BudgetExceeded, match="cost budget"):
        budget.check_limits(cost_usd=15.0)

    with pytest.raises(BudgetExceeded, match="duration budget"):
        budget.check_limits(elapsed_seconds=150.0)

    with pytest.raises(BudgetExceeded, match="token budget"):
        budget.check_limits(tokens_used=6000)

    with pytest.raises(BudgetExceeded, match="agent steps budget"):
        budget.check_limits(agent_steps=10)

    assert cost_from_summary({"total_cost_usd": 1.25}) == 1.25
    assert cost_from_summary(None) == 0.0
    assert tokens_from_summary({"total_tokens": 450}) == 450
    assert tokens_from_summary(None) == 0


def test_budget_from_env(monkeypatch):
    monkeypatch.setenv("LOOM_MAX_RUN_COST_USD", "25.5")
    monkeypatch.setenv("LOOM_MAX_RUN_DURATION_SECONDS", "1800")
    monkeypatch.setenv("LOOM_MAX_RUN_ATTEMPTS", "5")
    monkeypatch.setenv("LOOM_MAX_AGENT_STEPS", "12")
    monkeypatch.setenv("LOOM_MAX_RUN_TOKENS", "100000")

    budget = RunBudget.from_env()
    assert budget.max_cost_usd == 25.5
    assert budget.max_duration_seconds == 1800.0
    assert budget.max_attempts == 5
    assert budget.max_agent_steps == 12
    assert budget.max_tokens == 100000


def test_run_state_store_transitions():
    rec = RunStateRecord(run_id="run_1", org_id="org_1")
    assert rec.state == RunState.QUEUED

    # Valid transition to RUNNING
    transition(rec, RunState.RUNNING)
    assert rec.state == RunState.RUNNING
    assert rec.version == 1
    assert rec.heartbeat_at is not None

    # Heartbeat
    heartbeat(rec, "worker_1")
    assert rec.worker_id == "worker_1"

    # Valid transition to COMPLETED
    transition(rec, RunState.COMPLETED, expected_version=1)
    assert rec.state == RunState.COMPLETED
    assert rec.version == 2

    # Heartbeat on completed should fail
    with pytest.raises(InvalidRunTransition):
        heartbeat(rec, "worker_1")

    # Invalid transition from COMPLETED
    with pytest.raises(InvalidRunTransition):
        transition(rec, RunState.RUNNING)

    # Stale version check
    rec2 = RunStateRecord(run_id="run_2", org_id="org_1", state=RunState.QUEUED, version=5)
    with pytest.raises(InvalidRunTransition, match="stale"):
        transition(rec2, RunState.RUNNING, expected_version=3)


def test_backup_upload_production_error(monkeypatch, tmp_path):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("LOOM_BACKUP_S3_BUCKET", raising=False)

    archive = tmp_path / "test_backup.tar.gz.enc"
    archive.write_bytes(b"data")

    with pytest.raises(RuntimeError, match="LOOM_BACKUP_S3_BUCKET is required in production"):
        upload_backup_to_object_storage(archive)


def test_backup_upload_s3(monkeypatch, tmp_path):
    import sys
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("LOOM_BACKUP_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("LOOM_BACKUP_S3_PREFIX", "backups/prod")

    archive = tmp_path / "test_backup.tar.gz.enc"
    archive.write_bytes(b"data")
    checksum = tmp_path / "test_backup.tar.gz.enc.sha256"
    checksum.write_text("dummyhash")

    mock_client = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        upload_backup_to_object_storage(archive, checksum)
        assert mock_client.upload_file.call_count == 2


def test_distributed_health_endpoint():
    app = FastAPI()
    install_distributed_health(app, verify_auth=lambda: True)
    client = TestClient(app)

    # When Redis is not configured
    response = client.get("/api/v1/health/distributed")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") in {"degraded", "healthy", "unhealthy"}


def test_run_job_model():
    job = RunJob(
        job_id="job_123",
        run_id="run_123",
        org_id="org_default",
        repo_path="/workspace/repo",
        issue="Fix crash in reproduction",
        model="gpt-4o",
        mock=True,
        sandbox_tier="A",
        auto_merge_threshold=0.95,
        created_at=1000.0,
        attempts=1,
    )
    assert job.attempts == 1
    assert job.sandbox_tier == "A"


def test_evidence_bundler_idempotency_and_signing(tmp_path, monkeypatch):
    from loom.verification.bundle import EvidenceBundle, EvidenceBundler

    monkeypatch.setenv("LOOM_EVIDENCE_HMAC_KEY", "secret-key-123")
    bundler = EvidenceBundler(output_dir=str(tmp_path))

    bundle = EvidenceBundle(
        run_id="run_test_123",
        verified_patch="diff --git a/foo.py b/foo.py",
        verification_success=True,
        test_summary={"passed": True},
        cost_report={"total_cost_usd": 0.05},
        trace_events=[],
    )

    entry1 = bundler.export_bundle(bundle)
    assert entry1.signature is not None
    assert len(entry1.signature) > 0
    assert bundler.chain_length() == 1

    # Resume idempotency: export same run_id again should not append new entry to chain
    entry2 = bundler.export_bundle(bundle)
    assert entry2.run_id == entry1.run_id
    assert bundler.chain_length() == 1

    # Verify chain
    valid, err, tampered = bundler.verify_chain()
    assert valid is True
    assert err is None
    assert tampered == []


@pytest.mark.asyncio
async def test_async_verification_runner():
    from loom.sandbox.local_process import LocalProcessSandbox
    from loom.verification.runner import VerificationRunner

    sandbox = LocalProcessSandbox(repo_path=".")
    runner = VerificationRunner(sandbox)

    # Test arun_verification
    res = await runner.arun_verification(
        test_commands=["python -c \"print('test ok')\""],
    )
    assert res.overall_success is True
    assert res.tests_passed is True

    # Test evaluate_reproduction_async
    repro = await runner.evaluate_reproduction_async(
        repro_script="test",
        pre_patch_test_commands=["python -c \"import sys; sys.exit(1)\""],
        post_patch_test_commands=["python -c \"print('fixed')\""],
    )
    assert repro.flip_confirmed is True

    # Test full_verification_pipeline_async
    vres, rres = await runner.full_verification_pipeline_async(
        test_commands=["python -c \"print('test ok')\""],
        repro_script="test",
        pre_patch_test_commands=["python -c \"import sys; sys.exit(1)\""],
        post_patch_test_commands=["python -c \"print('fixed')\""],
        diff_text="+ # fix bug",
    )
    assert vres.overall_success is True
    assert rres.flip_confirmed is True


def test_metrics_backup_gauge(tmp_path, monkeypatch):
    import json

    from loom.api.server import BACKUP_LAST_STATUS, metrics

    status_file = tmp_path / "backup-status.json"
    status_file.write_text(json.dumps({"status": "success"}), encoding="utf-8")
    monkeypatch.setenv("LOOM_BACKUP_STATUS_FILE", str(status_file))

    res = metrics()
    assert res.status_code == 200
    assert BACKUP_LAST_STATUS._value.get() == 1.0 if hasattr(BACKUP_LAST_STATUS, "_value") else True



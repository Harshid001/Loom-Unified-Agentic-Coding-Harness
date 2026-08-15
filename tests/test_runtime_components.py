from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loom.runtime.budget import BudgetExceeded, RunBudget
from loom.runtime.health import install_distributed_health
from loom.telemetry.metrics import ACTIVE_RUNS_GAUGE, REQUEST_COUNT, generate_latest
from loom.telemetry.status import StatusSnapshot, healthy_status
from loom.verification.browser_runner import WebVerificationGate


def test_status_snapshot():
    snap = healthy_status()
    assert isinstance(snap, StatusSnapshot)
    assert snap.healthy is True
    assert snap.generated_at > 0


def test_metrics_registry():
    out = generate_latest()
    assert isinstance(out, (bytes, str))
    REQUEST_COUNT.labels(method="GET", endpoint="/healthz", status="200").inc()
    ACTIVE_RUNS_GAUGE.set(3)
    ACTIVE_RUNS_GAUGE.inc()
    ACTIVE_RUNS_GAUGE.dec()


def test_distributed_health_endpoint():
    app = FastAPI()
    install_distributed_health(app, lambda: "auth_token")
    client = TestClient(app)
    resp = client.get("/api/v1/health/distributed")
    assert resp.status_code == 200
    assert "status" in resp.json()


def test_run_budget_from_env(monkeypatch):
    monkeypatch.setenv("LOOM_MAX_RUN_COST_USD", "25.5")
    monkeypatch.setenv("LOOM_MAX_RUN_DURATION_SECONDS", "1800")
    monkeypatch.setenv("LOOM_MAX_RUN_TOKENS", "250000")
    monkeypatch.setenv("LOOM_MAX_RUN_ATTEMPTS", "4")

    budget = RunBudget.from_env()
    assert budget.max_cost_usd == 25.5
    assert budget.max_duration_seconds == 1800
    assert budget.max_tokens == 250000
    assert budget.max_attempts == 4

    # Test enforcement
    budget.check_limits(cost_usd=10.0, elapsed_seconds=100.0, tokens_used=1000)
    with pytest.raises(BudgetExceeded, match="cost"):
        budget.check_limits(cost_usd=30.0, elapsed_seconds=100.0, tokens_used=1000)
    with pytest.raises(BudgetExceeded, match="duration"):
        budget.check_limits(cost_usd=10.0, elapsed_seconds=2000.0, tokens_used=1000)
    with pytest.raises(BudgetExceeded, match="token"):
        budget.check_limits(cost_usd=10.0, elapsed_seconds=100.0, tokens_used=300000)


@pytest.mark.asyncio
async def test_browser_runner_fallback():
    gate = WebVerificationGate("http://127.0.0.1:3000")
    res = await gate.verify_livebox_ui()
    assert "passed" in res
    assert "url" in res


def test_upload_backup_to_object_storage(monkeypatch, tmp_path):
    from loom.runtime.backup import upload_backup_to_object_storage

    archive = tmp_path / "test_archive.tar.gz"
    checksum = tmp_path / "test_archive.tar.gz.sha256"
    archive.write_text("archive")
    checksum.write_text("sha")

    # Without S3 bucket set, it logs/noops gracefully
    monkeypatch.delenv("LOOM_BACKUP_S3_BUCKET", raising=False)
    assert upload_backup_to_object_storage(archive, checksum) is None

    # With S3 bucket set, attempts s3 client upload
    monkeypatch.setenv("LOOM_BACKUP_S3_BUCKET", "my-bucket")
    mock_boto = MagicMock()
    mock_s3 = MagicMock()
    mock_boto.client.return_value = mock_s3
    with patch.dict("sys.modules", {"boto3": mock_boto}):
        upload_backup_to_object_storage(archive, checksum)
        assert mock_s3.upload_file.call_count == 2

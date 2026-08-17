import pytest

from loom.runtime.bootstrap import validate_production_environment


def _set_required(monkeypatch, tmp_path):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.setenv("API_KEY", "api")
    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", "dashboard")
    monkeypatch.setenv("ALLOWED_REPO_ROOTS", str(tmp_path))
    monkeypatch.setenv("LOOM_BACKUP_ENCRYPTION_KEY", "dummy")
    monkeypatch.setenv("LOOM_SANDBOX_WORKER_URL", "http://sandbox-worker:8100")
    monkeypatch.setenv("SANDBOX_WORKER_TOKEN", "worker")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("LOOM_BACKUP_S3_BUCKET", "loom-backups")
    monkeypatch.setenv("LOOM_MAX_RUN_COST_USD", "10")
    monkeypatch.setenv("LOOM_MAX_RUN_DURATION_SECONDS", "3600")
    monkeypatch.setenv("LOOM_MAX_RUN_TOKENS", "100000")


def test_production_bootstrap_requires_security_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("DEV_MODE", raising=False)
    for name in (
        "API_KEY",
        "DASHBOARD_AUTH_TOKEN",
        "ALLOWED_REPO_ROOTS",
        "LOOM_BACKUP_ENCRYPTION_KEY",
        "LOOM_SANDBOX_WORKER_URL",
        "SANDBOX_WORKER_TOKEN",
        "REDIS_URL",
        "LOOM_BACKUP_S3_BUCKET",
        "LOOM_MAX_RUN_COST_USD",
        "LOOM_MAX_RUN_DURATION_SECONDS",
        "LOOM_MAX_RUN_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="missing required environment variables"):
        validate_production_environment()


def test_production_bootstrap_accepts_required_configuration(tmp_path, monkeypatch):
    _set_required(monkeypatch, tmp_path)
    monkeypatch.setenv("LOOM_TOKEN_ADMIN_ENABLED", "false")

    validate_production_environment()


def test_production_bootstrap_rejects_token_admin_api(monkeypatch, tmp_path):
    _set_required(monkeypatch, tmp_path)
    monkeypatch.setenv("LOOM_TOKEN_ADMIN_ENABLED", "true")

    with pytest.raises(RuntimeError, match="LOOM_TOKEN_ADMIN_ENABLED"):
        validate_production_environment()

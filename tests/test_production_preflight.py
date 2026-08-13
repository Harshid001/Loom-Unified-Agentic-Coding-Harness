from pathlib import Path

from scripts.production_preflight import validate_artifacts, validate_environment


def test_production_environment_rejects_missing_required_values(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    for name in (
        "API_KEY",
        "DASHBOARD_AUTH_TOKEN",
        "ALLOWED_REPO_ROOTS",
        "DATABASE_URL",
        "REDIS_URL",
        "LOOM_FIRECRACKER_WORKER_URL",
        "LOOM_FIRECRACKER_WORKER_TOKEN",
        "LOOM_BACKUP_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    errors = validate_environment()

    assert errors
    assert any("API_KEY" in error for error in errors)
    assert any("REDIS_URL" in error for error in errors)
    assert any("LOOM_FIRECRACKER_WORKER_URL" in error for error in errors)


def test_production_environment_rejects_insecure_flags(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    required = {
        "API_KEY": "real-api-key",
        "DASHBOARD_AUTH_TOKEN": "real-dashboard-token",
        "ALLOWED_REPO_ROOTS": "/var/repos",
        "DATABASE_URL": "postgresql://loom:secret@db/loom",
        "REDIS_URL": "redis://redis:6379/0",
        "LOOM_FIRECRACKER_WORKER_URL": "http://firecracker-worker:8101",
        "LOOM_FIRECRACKER_WORKER_TOKEN": "real-worker-token",
        "LOOM_BACKUP_ENCRYPTION_KEY": "real-backup-key",
    }
    for name, value in required.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LOOM_TOKEN_ADMIN_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "true")

    errors = validate_environment()

    assert any("LOOM_TOKEN_ADMIN_ENABLED" in error for error in errors)
    assert any("RATE_LIMIT_ALLOW_LOCAL_FALLBACK" in error for error in errors)


def test_production_environment_accepts_complete_configuration(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    required = {
        "API_KEY": "real-api-key",
        "DASHBOARD_AUTH_TOKEN": "real-dashboard-token",
        "ALLOWED_REPO_ROOTS": "/var/repos",
        "DATABASE_URL": "postgresql://loom:secret@db/loom",
        "REDIS_URL": "redis://redis:6379/0",
        "LOOM_FIRECRACKER_WORKER_URL": "http://firecracker-worker:8101",
        "LOOM_FIRECRACKER_WORKER_TOKEN": "real-worker-token",
        "LOOM_BACKUP_ENCRYPTION_KEY": "real-backup-key",
    }
    for name, value in required.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LOOM_TOKEN_ADMIN_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "false")

    assert validate_environment() == []


def test_required_repository_artifacts_exist(tmp_path: Path):
    for relative in (
        "pyproject.toml",
        "web/package.json",
        ".github/workflows/ci.yml",
        ".env.example",
        "docs/deployment.md",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    assert validate_artifacts(tmp_path) == []

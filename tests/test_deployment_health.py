import json
from pathlib import Path

import pytest

from scripts.postgres_healthcheck import check as check_postgres
from scripts.postgres_healthcheck import validate_database_url
from scripts.redis_healthcheck import validate_redis_url


def test_postgres_url_validation_rejects_non_postgresql_urls():
    with pytest.raises(RuntimeError, match="PostgreSQL URL"):
        validate_database_url("sqlite:///loom.db")


def test_redis_url_validation_rejects_non_redis_urls():
    with pytest.raises(RuntimeError, match="Redis URL"):
        validate_redis_url("postgresql://localhost/redis")


def test_postgres_health_evidence_contains_required_fields(monkeypatch):
    class FakeConnection:
        def execute(self, statement):
            sql = str(statement)
            if "current_database" in sql:
                return type("Result", (), {"mappings": lambda self: type("Mappings", (), {"one": lambda self: {"database_name": "loom", "server_version": "PostgreSQL test"}})()})()
            return type("Result", (), {"scalar_one": lambda self: 12})()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self):
            return None

    monkeypatch.setattr("scripts.postgres_healthcheck.create_engine", lambda *args, **kwargs: FakeEngine())
    evidence = check_postgres("postgresql://loom:secret@db/loom")

    assert evidence["status"] == "passed"
    assert evidence["migration_version"] == 12
    assert evidence["database_name"] == "loom"
    assert "connection_latency_ms" in evidence


def test_postgres_health_evidence_is_json_serializable(tmp_path: Path, monkeypatch):
    class FakeConnection:
        def execute(self, statement):
            sql = str(statement)
            if "current_database" in sql:
                return type("Result", (), {"mappings": lambda self: type("Mappings", (), {"one": lambda self: {"database_name": "loom", "server_version": "PostgreSQL test"}})()})()
            return type("Result", (), {"scalar_one": lambda self: 1})()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self):
            return None

    monkeypatch.setattr("scripts.postgres_healthcheck.create_engine", lambda *args, **kwargs: FakeEngine())
    evidence = check_postgres("postgresql://loom:secret@db/loom")
    path = tmp_path / "postgres.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "passed"

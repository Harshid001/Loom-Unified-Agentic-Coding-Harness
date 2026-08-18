import hashlib
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from loom.db.migration_runner import (
    _ensure_schema_migrations,
    _migration_files,
    apply_postgres_migrations,
    apply_sqlite_hardening,
    main,
    rollback_postgres_migration,
)


def test_sqlite_foreign_keys_enabled(tmp_path):
    db = tmp_path / "records.db"
    conn = sqlite3.connect(db)
    try:
        apply_sqlite_hardening(conn)
        enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert enabled == 1
        version_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        assert version_table is not None
    finally:
        conn.close()


def test_postgres_migration_files():
    files = _migration_files()
    assert len(files) >= 4
    filenames = [f.name for f in files]
    assert "001_initial.sql" in filenames
    assert "002_integrity.sql" in filenames
    assert "003_timestamptz.sql" in filenames
    assert "004_org_indexes.sql" in filenames


def test_ensure_schema_migrations_adds_missing_columns():
    conn = MagicMock()
    # Mock column check returning empty list
    conn.execute.return_value.scalars.return_value.all.return_value = []

    _ensure_schema_migrations(conn)

    # Verify CREATE TABLE and 2 ALTER TABLE calls were executed
    executed_sqls = [str(call.args[0].text if hasattr(call.args[0], "text") else call.args[0]) for call in conn.execute.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS schema_migrations" in s for s in executed_sqls)
    assert any("ADD COLUMN filename" in s for s in executed_sqls)
    assert any("ADD COLUMN checksum" in s for s in executed_sqls)


def test_apply_postgres_migrations_clean_run():
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn

    # Mock no columns missing
    conn.execute.return_value.scalars.return_value.all.return_value = ["filename", "checksum"]
    # Mock no previously applied migrations
    conn.execute.return_value.mappings.return_value.all.return_value = []

    apply_postgres_migrations(engine)

    # Verify advisory lock was acquired
    executed_sqls = [str(call.args[0].text if hasattr(call.args[0], "text") else call.args[0]) for call in conn.execute.call_args_list]
    assert any("pg_advisory_xact_lock" in s for s in executed_sqls)
    # Verify exec_driver_sql was called for each migration file
    assert conn.exec_driver_sql.call_count == len(_migration_files())


def test_apply_postgres_migrations_idempotent():
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn

    conn.execute.return_value.scalars.return_value.all.return_value = ["filename", "checksum"]

    # Build applied list with matching checksums
    files = _migration_files()
    applied_records = []
    for f in files:
        version = int(f.name[:3])
        sql = f.read_text(encoding="utf-8").strip()
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        applied_records.append({"version": version, "filename": f.name, "checksum": checksum})

    conn.execute.return_value.mappings.return_value.all.return_value = applied_records

    apply_postgres_migrations(engine)

    # Should not have executed any new SQL migrations since all match
    assert conn.exec_driver_sql.call_count == 0


def test_apply_postgres_migrations_checksum_mismatch():
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn

    conn.execute.return_value.scalars.return_value.all.return_value = ["filename", "checksum"]

    # Corrupt checksum for version 1
    applied_records = [{"version": 1, "filename": "001_initial.sql", "checksum": "tampered_checksum_value"}]
    conn.execute.return_value.mappings.return_value.all.return_value = applied_records

    with pytest.raises(RuntimeError, match="Migration 1 checksum/name mismatch"):
        apply_postgres_migrations(engine)


def test_apply_postgres_migrations_legacy_checksum_upgrade():
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn

    conn.execute.return_value.scalars.return_value.all.return_value = ["filename", "checksum"]

    # Version 1 has legacy checksum
    files = _migration_files()
    applied_records = [{"version": 1, "filename": files[0].name, "checksum": "legacy"}]
    for f in files[1:]:
        version = int(f.name[:3])
        sql = f.read_text(encoding="utf-8").strip()
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        applied_records.append({"version": version, "filename": f.name, "checksum": checksum})

    conn.execute.return_value.mappings.return_value.all.return_value = applied_records

    apply_postgres_migrations(engine)

    # Should have updated the legacy checksum
    executed_sqls = [str(call.args[0].text if hasattr(call.args[0], "text") else call.args[0]) for call in conn.execute.call_args_list]
    assert any("UPDATE schema_migrations SET filename=:filename, checksum=:checksum" in s for s in executed_sqls)


def test_apply_postgres_migrations_no_files_raises(monkeypatch):
    monkeypatch.setattr("loom.db.migration_runner._migration_files", lambda: [])
    engine = MagicMock()

    with pytest.raises(RuntimeError, match="No PostgreSQL migration files found"):
        apply_postgres_migrations(engine)


def test_rollback_postgres_migration(tmp_path):
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn

    conn.execute.return_value.scalars.return_value.all.return_value = ["filename", "checksum"]
    conn.execute.return_value.mappings.return_value.all.return_value = [
        {"version": 5, "filename": "005_retention.sql"},
        {"version": 4, "filename": "004_org_indexes.sql"},
    ]

    rollback_postgres_migration(engine, target_version=3)

    # Should have deleted rows for versions 5 and 4
    executed_sqls = [str(call.args[0].text if hasattr(call.args[0], "text") else call.args[0]) for call in conn.execute.call_args_list]
    assert any("DELETE FROM schema_migrations WHERE version = :version" in s for s in executed_sqls)


def test_migration_runner_cli_main(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/loom_test")
    with patch("sqlalchemy.create_engine"):
        with patch("loom.db.migration_runner.apply_postgres_migrations") as mock_apply:
            with patch("sys.argv", ["migration_runner.py", "--up"]):
                main()
                assert mock_apply.called

        with patch("loom.db.migration_runner.rollback_postgres_migration") as mock_rollback:
            with patch("sys.argv", ["migration_runner.py", "--down", "--target", "2"]):
                main()
                assert mock_rollback.called
                assert mock_rollback.call_args[0][1] == 2


def test_migration_runner_cli_missing_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    with patch("sys.argv", ["migration_runner.py", "--up"]):
        with pytest.raises(ValueError, match="Database URL must be provided"):
            main()



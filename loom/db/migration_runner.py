"""Authoritative PostgreSQL migration runner.

The SQL files under migrations/postgres are the single source of truth. The
schema_migrations table records the version, filename, checksum and timestamp.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _migration_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "migrations" / "postgres"
    return sorted(root.glob("[0-9][0-9][0-9]_*.sql"))


def _ensure_schema_migrations(conn: Any) -> None:
    from sqlalchemy import text

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                filename VARCHAR(255),
                checksum VARCHAR(64),
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    columns = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'schema_migrations'")
    ).scalars().all()
    if "filename" not in columns:
        conn.execute(text("ALTER TABLE schema_migrations ADD COLUMN filename VARCHAR(255)"))
    if "checksum" not in columns:
        conn.execute(text("ALTER TABLE schema_migrations ADD COLUMN checksum VARCHAR(64)"))


def apply_postgres_migrations(engine: Any) -> None:
    from sqlalchemy import text

    files = _migration_files()
    if not files:
        raise RuntimeError("No PostgreSQL migration files found")

    with engine.begin() as conn:
        _ensure_schema_migrations(conn)
        rows = conn.execute(
            text("SELECT version, filename, checksum FROM schema_migrations ORDER BY version")
        ).mappings().all()
        applied = {int(row["version"]): dict(row) for row in rows}

        for path in files:
            version = int(path.name[:3])
            sql = path.read_text(encoding="utf-8").strip()
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            previous = applied.get(version)
            if previous is not None:
                old_checksum = previous.get("checksum") or ""
                if old_checksum in {"", "legacy", "programmatic"}:
                    conn.execute(
                        text("UPDATE schema_migrations SET filename=:filename, checksum=:checksum WHERE version=:version"),
                        {"filename": path.name, "checksum": checksum, "version": version},
                    )
                    continue
                if previous.get("filename") != path.name or old_checksum != checksum:
                    raise RuntimeError(f"Migration {version} checksum/name mismatch")
                continue

            conn.exec_driver_sql(sql)
            conn.execute(
                text(
                    "INSERT INTO schema_migrations(version, filename, checksum) VALUES (:version, :filename, :checksum)"
                ),
                {"version": version, "filename": path.name, "checksum": checksum},
            )


def apply_sqlite_hardening(conn: Any) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
    )

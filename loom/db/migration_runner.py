"""Versioned database migrations for production schema evolution.

The repository now uses the same schema_migrations contract as
scripts/postgres_migrate.py: version + filename + checksum + applied_at.
"""

from __future__ import annotations

import time
from typing import Any


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
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'schema_migrations'
            """
        )
    ).scalars().all()
    if "filename" not in columns:
        conn.execute(text("ALTER TABLE schema_migrations ADD COLUMN filename VARCHAR(255)"))
    if "checksum" not in columns:
        conn.execute(text("ALTER TABLE schema_migrations ADD COLUMN checksum VARCHAR(64)"))
    conn.execute(
        text("UPDATE schema_migrations SET filename = COALESCE(filename, 'legacy') WHERE filename IS NULL")
    )
    conn.execute(
        text("UPDATE schema_migrations SET checksum = COALESCE(checksum, 'legacy') WHERE checksum IS NULL")
    )


def apply_postgres_migrations(engine: Any) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        _ensure_schema_migrations(conn)
        current = int(conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")).scalar_one())

        if current < 1:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_org_started ON runs(org_id, started_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_steps_run_recorded ON agent_steps(run_id, recorded_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_verify_run_recorded ON verification_results(run_id, recorded_at)"))
            conn.execute(
                text(
                    "INSERT INTO schema_migrations(version, filename, checksum, applied_at) "
                    "VALUES (1, 'programmatic-001', 'programmatic', :ts)"
                ),
                {"ts": time.time()},
            )
            current = 1

        if current < 2:
            org_exists = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'organizations')")
            ).scalar_one()
            if org_exists:
                existing_fk = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.table_constraints "
                        "WHERE table_name='runs' AND constraint_name='fk_runs_org'"
                    )
                ).scalar_one_or_none()
                if existing_fk is None:
                    conn.execute(
                        text(
                            "ALTER TABLE runs ADD CONSTRAINT fk_runs_org "
                            "FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE"
                        )
                    )
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_org ON runs(org_id)"))
            conn.execute(
                text(
                    "INSERT INTO schema_migrations(version, filename, checksum, applied_at) "
                    "VALUES (2, 'programmatic-002', 'programmatic', :ts)"
                ),
                {"ts": time.time()},
            )


def apply_sqlite_hardening(conn: Any) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
    )

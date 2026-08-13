"""Versioned database migrations for production schema evolution."""

from __future__ import annotations

import time
from typing import Any


def apply_postgres_migrations(engine: Any) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at DOUBLE PRECISION NOT NULL
                )
                """
            )
        )
        current = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")).scalar_one()
        if int(current) < 1:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_org_started ON runs(org_id, started_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_steps_run_recorded ON agent_steps(run_id, recorded_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_verify_run_recorded ON verification_results(run_id, recorded_at)"))
            conn.execute(text("INSERT INTO schema_migrations(version, applied_at) VALUES (1, :ts)"), {"ts": time.time()})
            current = 1

        if int(current) < 2:
            # Add tenant FK constraints only when their parent tables exist. Existing
            # deployments may not yet have an organizations table, so this migration
            # intentionally fails safe and records the version only after inspection.
            org_exists = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'organizations')")
            ).scalar_one()
            if org_exists:
                conn.execute(
                    text(
                        "ALTER TABLE runs ADD CONSTRAINT fk_runs_org FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE"
                    )
                )
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_org ON runs(org_id)"))
            conn.execute(text("INSERT INTO schema_migrations(version, applied_at) VALUES (2, :ts)"), {"ts": time.time()})


def apply_sqlite_hardening(conn: Any) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
    )

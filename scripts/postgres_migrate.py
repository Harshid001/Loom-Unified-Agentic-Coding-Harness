#!/usr/bin/env python3
"""Apply versioned PostgreSQL migrations with an advisory lock and checksums."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

LOCK_KEY = 74291351


def migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def migration_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))


def parse_version(path: Path) -> int:
    return int(path.name[:3])


def validate_database_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")


def migrate(database_url: str, directory: Path, target: int | None = None) -> int:
    validate_database_url(database_url)
    files = migration_files(directory)
    if not files:
        raise RuntimeError(f"No PostgreSQL migrations found in {directory}")

    engine = create_engine(database_url, pool_pre_ping=True, pool_size=3, max_overflow=2)
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    checksum VARCHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        rows = conn.execute(text("SELECT version, filename, checksum FROM schema_migrations ORDER BY version")).mappings().all()
        applied = {int(row["version"]): dict(row) for row in rows}

        for path in files:
            version = parse_version(path)
            if target is not None and version > target:
                break
            sql = path.read_text(encoding="utf-8").strip()
            checksum = migration_checksum(sql)
            previous = applied.get(version)
            if previous is not None:
                if previous["checksum"] != checksum or previous["filename"] != path.name:
                    raise RuntimeError(f"Migration {version} checksum/name mismatch")
                continue
            conn.exec_driver_sql(sql)
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, filename, checksum) VALUES (:version, :filename, :checksum)"
                ),
                {"version": version, "filename": path.name, "checksum": checksum},
            )
            print(f"applied {version:03d} {path.name}")

        latest = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")).scalar_one()
        return int(latest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Loom PostgreSQL migrations")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--directory", default="migrations/postgres")
    parser.add_argument("--target", type=int, default=None)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    version = migrate(args.database_url, Path(args.directory).resolve(), args.target)
    print(f"schema_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

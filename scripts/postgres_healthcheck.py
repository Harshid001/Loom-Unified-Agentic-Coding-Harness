#!/usr/bin/env python3
"""Check PostgreSQL connectivity and emit deployment evidence."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text


def validate_database_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")


def check(database_url: str) -> dict[str, object]:
    validate_database_url(database_url)
    started = time.perf_counter()
    engine = create_engine(database_url, pool_pre_ping=True, pool_size=2, max_overflow=1)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT current_database() AS database_name, version() AS server_version")
        ).mappings().one()
        schema_version = conn.execute(
            text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
        ).scalar_one()
        latency_ms = (time.perf_counter() - started) * 1000
    engine.dispose()
    return {
        "schema_version": 1,
        "status": "passed",
        "database_name": row["database_name"],
        "server_version": row["server_version"],
        "migration_version": int(schema_version),
        "connection_latency_ms": round(latency_ms, 3),
        "timestamp": time.time(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify PostgreSQL deployment health")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--evidence", type=Path, default=Path("postgres-health-evidence.json"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    evidence = check(args.database_url)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

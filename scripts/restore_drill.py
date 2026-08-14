#!/usr/bin/env python3
"""Run a backup/restore drill against a disposable target and emit evidence."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.backup_restore import compute_sha256, create_backup, restore_backup


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Loom backup/restore drill")
    parser.add_argument("--backup-dir", default="./drill-backups")
    parser.add_argument("--restore-home", default="./drill-restore")
    parser.add_argument("--database-url", help="Disposable PostgreSQL target used only for this drill")
    parser.add_argument("--confirm-disposable", action="store_true", help="Explicitly confirm the database target is disposable")
    parser.add_argument("--report", default="./restore-drill-report.json")
    args = parser.parse_args()

    if args.database_url:
        live_url = os.getenv("DATABASE_URL")
        if not args.confirm_disposable:
            raise SystemExit("Refusing restore drill: --confirm-disposable is required for a database target")
        if live_url and args.database_url == live_url:
            raise SystemExit("Refusing restore drill: target DATABASE_URL matches the configured live DATABASE_URL")
        os.environ["DATABASE_URL"] = args.database_url

    backup_dir = Path(args.backup_dir).resolve()
    restore_home = Path(args.restore_home).resolve()
    report_path = Path(args.report).resolve()
    restore_home.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    backup = create_backup(backup_dir)
    backup_elapsed = time.monotonic() - started
    backup_mtime = backup.stat().st_mtime

    restore_started = time.monotonic()
    ok = restore_backup(backup, target_loom_home=restore_home)
    restore_elapsed = time.monotonic() - restore_started
    total_elapsed = time.monotonic() - started

    report = {
        "timestamp": utc_now(),
        "status": "passed" if ok else "failed",
        "backup": str(backup),
        "backup_sha256": compute_sha256(backup),
        "backup_duration_seconds": round(backup_elapsed, 3),
        "restore_duration_seconds": round(restore_elapsed, 3),
        "rto_seconds": round(total_elapsed, 3),
        "rpo_seconds": round(max(0.0, time.time() - backup_mtime), 3),
        "restore_home": str(restore_home),
        "database_target": args.database_url or "not-provided",
        "disposable_target_confirmed": bool(args.confirm_disposable),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

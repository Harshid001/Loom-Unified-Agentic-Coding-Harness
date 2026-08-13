"""Continuous production backup scheduler with optional S3-compatible off-site storage."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from loom.runtime.backup import upload_backup_to_object_storage
from scripts.backup_restore import create_backup


def _interval_seconds() -> int:
    return max(300, int(os.getenv("LOOM_BACKUP_INTERVAL_SECONDS", "3600")))


def _backup_directory() -> Path:
    return Path(os.getenv("LOOM_BACKUP_DIR", "/home/loomuser/.loom/backups"))


def _status_file() -> Path:
    return Path(
        os.getenv(
            "LOOM_BACKUP_STATUS_FILE",
            "/home/loomuser/.loom/backups/backup-status.json",
        )
    )


def _write_status(status: str, archive: Path | None = None, error: str | None = None) -> None:
    path = _status_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "timestamp": time.time(),
        "archive": str(archive) if archive else None,
        "error": error,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _retention_count() -> int:
    return max(2, int(os.getenv("LOOM_BACKUP_RETENTION_COUNT", "24")))


def prune_local_backups(directory: Path) -> None:
    archives = sorted(
        [p for p in directory.glob("loom_backup_*") if p.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    keep = _retention_count() * 2
    for path in archives[keep:]:
        try:
            path.unlink()
        except OSError:
            pass


def run_once() -> Path:
    directory = _backup_directory()
    directory.mkdir(parents=True, exist_ok=True)
    archive = create_backup(directory)
    checksum = Path(str(archive) + ".sha256")
    upload_backup_to_object_storage(archive, checksum)
    if not checksum.exists():
        raise RuntimeError(f"Backup checksum was not produced: {checksum}")
    prune_local_backups(directory)
    _write_status("success", archive=archive)
    return archive


def main() -> None:
    interval = _interval_seconds()
    while True:
        try:
            archive = run_once()
            print(f"[BACKUP] completed: {archive}", flush=True)
        except Exception as exc:
            _write_status("failed", error=str(exc)[:1000])
            print(f"[BACKUP] failed: {exc}", flush=True)
            if os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}:
                # Never busy-loop on a failing production backup job.
                time.sleep(min(interval, 300))
        time.sleep(interval)


if __name__ == "__main__":
    main()

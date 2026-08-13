#!/usr/bin/env python3
"""Loom Backup & Disaster Recovery CLI Tool (PRD-005 & PRD-006).

Provides automated backup creation, archive compression, SHA-256 checksum verification,
and disaster recovery restore procedures for SQLite/Postgres records databases and evidence bundles.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
from pathlib import Path
from typing import Optional


def compute_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_backup(backup_dir: Path) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    target_dir = backup_dir / f"loom_backup_{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=True)

    loom_home = Path.home() / ".loom"
    records_db = loom_home / "records.db"
    memory_db = loom_home / "memory.db"
    evidence_dir = os.getenv("LOOM_EVIDENCE_DIR") or (loom_home / "evidence")
    evidence_path = Path(evidence_dir)

    manifest = {
        "timestamp": timestamp,
        "backup_version": "1.0",
        "items": [],
    }

    if records_db.exists():
        shutil.copy2(records_db, target_dir / "records.db")
        manifest["items"].append("records.db")

    if memory_db.exists():
        shutil.copy2(memory_db, target_dir / "memory.db")
        manifest["items"].append("memory.db")

    if evidence_path.exists() and evidence_path.is_dir():
        shutil.copytree(evidence_path, target_dir / "evidence", dirs_exist_ok=True)
        manifest["items"].append("evidence")

    manifest_path = target_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    archive_path = backup_dir / f"loom_backup_{timestamp}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(target_dir, arcname=target_dir.name)

    shutil.rmtree(target_dir)

    checksum = compute_sha256(archive_path)
    checksum_file = backup_dir / f"loom_backup_{timestamp}.tar.gz.sha256"
    checksum_file.write_text(f"{checksum}  {archive_path.name}\n")

    print(f"[SUCCESS] Loom backup created successfully:")
    print(f"  Archive:  {archive_path}")
    print(f"  Checksum: {checksum_file} ({checksum[:12]}...)")
    return archive_path


def restore_backup(archive_path: Path, target_loom_home: Optional[Path] = None) -> bool:
    if not archive_path.exists():
        print(f"[ERROR] Archive file not found: {archive_path}")
        return False

    checksum_file = Path(str(archive_path) + ".sha256")
    if checksum_file.exists():
        expected_sha = checksum_file.read_text().split()[0]
        actual_sha = compute_sha256(archive_path)
        if expected_sha.lower() != actual_sha.lower():
            print(f"[ERROR] Checksum mismatch! Backup file may be corrupted.")
            print(f"  Expected: {expected_sha}")
            print(f"  Actual:   {actual_sha}")
            return False
        print("[INFO] SHA-256 Checksum verified cleanly.")

    dest_home = target_loom_home or (Path.home() / ".loom")
    dest_home.mkdir(parents=True, exist_ok=True)

    temp_extract = dest_home / "_restore_temp"
    temp_extract.mkdir(parents=True, exist_ok=True)

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=temp_extract)

        extracted_dirs = [d for d in temp_extract.iterdir() if d.is_dir()]
        if not extracted_dirs:
            print("[ERROR] Corrupted archive: no backup root directory found.")
            return False

        backup_root = extracted_dirs[0]

        if (backup_root / "records.db").exists():
            shutil.copy2(backup_root / "records.db", dest_home / "records.db")
            print(f"  Restored: {dest_home / 'records.db'}")

        if (backup_root / "memory.db").exists():
            shutil.copy2(backup_root / "memory.db", dest_home / "memory.db")
            print(f"  Restored: {dest_home / 'memory.db'}")

        if (backup_root / "evidence").exists():
            shutil.copytree(backup_root / "evidence", dest_home / "evidence", dirs_exist_ok=True)
            print(f"  Restored: {dest_home / 'evidence'}")

        print(f"[SUCCESS] Loom restore completed successfully to {dest_home}")
        return True
    finally:
        if temp_extract.exists():
            shutil.rmtree(temp_extract)


def main():
    parser = argparse.ArgumentParser(description="Loom Backup & Disaster Recovery Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("create", help="Create a compressed backup archive")
    backup_parser.add_argument("--dir", type=str, default="./backups", help="Target backup directory")

    restore_parser = subparsers.add_parser("restore", help="Restore from a compressed backup archive")
    restore_parser.add_argument("archive", type=str, help="Path to .tar.gz backup archive")
    restore_parser.add_argument("--loom-home", type=str, default=None, help="Target Loom home directory")

    args = parser.parse_args()

    if args.command == "create":
        backup_dir = Path(args.dir).resolve()
        create_backup(backup_dir)
    elif args.command == "restore":
        archive = Path(args.archive).resolve()
        loom_home = Path(args.loom_home).resolve() if args.loom_home else None
        success = restore_backup(archive, loom_home)
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Loom backup and disaster-recovery utility."""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


def compute_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with filepath.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _production() -> bool:
    return os.getenv("LOOM_ENV", "").lower() in {"prod", "production"}


def _loom_home() -> Path:
    override = os.getenv("LOOM_HOME")
    if override:
        return Path(override).expanduser()
    home_env = os.getenv("HOME")
    if home_env:
        return Path(home_env).expanduser() / ".loom"
    return Path.home() / ".loom"


def _database_args(env_url: str) -> tuple[list[str], dict[str, str]]:
    from urllib.parse import urlparse

    parsed = urlparse(env_url)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
    env = os.environ.copy()
    if parsed.password is not None:
        env["PGPASSWORD"] = parsed.password
    args = ["--host", parsed.hostname]
    if parsed.port:
        args += ["--port", str(parsed.port)]
    if parsed.username:
        args += ["--username", parsed.username]
    database = parsed.path.lstrip("/")
    if not database:
        raise RuntimeError("PostgreSQL URL must include a database name")
    args += ["--dbname", database]
    return args, env


def _fernet() -> Optional[Fernet]:
    key = os.getenv("LOOM_BACKUP_ENCRYPTION_KEY")
    if not key:
        if _production():
            raise RuntimeError("LOOM_BACKUP_ENCRYPTION_KEY is required in production")
        return None
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("LOOM_BACKUP_ENCRYPTION_KEY is not a valid Fernet key") from exc


def _safe_extract(tar: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in tar.getmembers():
        member_path = (destination / member.name).resolve()
        if member_path != destination and destination not in member_path.parents:
            raise ValueError(f"Unsafe archive member path: {member.name}")
        if member.issym() or member.islnk():
            link_target = (member_path.parent / member.linkname).resolve()
            if destination not in link_target.parents and link_target != destination:
                raise ValueError(f"Unsafe archive link target: {member.name} -> {member.linkname}")
    tar.extractall(path=destination)


def _sqlite_consistent_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source)
    destination_conn = sqlite3.connect(destination)
    try:
        try:
            source_conn.backup(destination_conn)
        except sqlite3.DatabaseError:
            destination_conn.close()
            source_conn.close()
            shutil.copy2(source, destination)
            return
    finally:
        try:
            destination_conn.close()
        except sqlite3.Error:
            pass
        try:
            source_conn.close()
        except sqlite3.Error:
            pass


def create_backup(backup_dir: Path) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    target_dir = backup_dir / f"loom_backup_{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=True)
    loom_home = _loom_home()
    records_db = loom_home / "records.db"
    memory_db = loom_home / "memory.db"
    evidence_path = Path(os.getenv("LOOM_EVIDENCE_DIR") or (loom_home / "evidence"))
    checkpoints_path = Path(os.getenv("LOOM_CHECKPOINT_DIR") or (loom_home / "checkpoints"))

    manifest = {
        "timestamp": timestamp,
        "backup_version": "3.0",
        "encrypted": bool(os.getenv("LOOM_BACKUP_ENCRYPTION_KEY")),
        "items": [],
    }
    if records_db.exists():
        _sqlite_consistent_copy(records_db, target_dir / "records.db")
        manifest["items"].append("records.db")
    if memory_db.exists():
        _sqlite_consistent_copy(memory_db, target_dir / "memory.db")
        manifest["items"].append("memory.db")
    for source_path, archive_name in ((evidence_path, "evidence"), (checkpoints_path, "checkpoints")):
        if source_path.exists() and source_path.is_dir():
            shutil.copytree(source_path, target_dir / archive_name, dirs_exist_ok=True, symlinks=False)
            manifest["items"].append(archive_name)

    if os.getenv("DATABASE_URL", "").startswith(("postgresql://", "postgres://")):
        dump_path = target_dir / "postgres.dump"
        args, env = _database_args(os.environ["DATABASE_URL"])
        result = subprocess.run(
            ["pg_dump", "--format=custom", "--file", str(dump_path), *args],
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError("pg_dump failed")
        manifest["items"].append("postgres.dump")

    (target_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    plain_archive = backup_dir / f"loom_backup_{timestamp}.tar.gz"
    with tarfile.open(plain_archive, "w:gz") as tar:
        tar.add(target_dir, arcname=target_dir.name)
    shutil.rmtree(target_dir)

    encryptor = _fernet()
    archive_path = plain_archive
    if encryptor is not None:
        encrypted_path = backup_dir / f"{plain_archive.name}.enc"
        encrypted_path.write_bytes(encryptor.encrypt(plain_archive.read_bytes()))
        plain_archive.unlink()
        archive_path = encrypted_path

    checksum = compute_sha256(archive_path)
    Path(str(archive_path) + ".sha256").write_text(
        f"{checksum}  {archive_path.name}\n", encoding="utf-8"
    )
    return archive_path


def restore_backup(
    archive_path: Path,
    target_loom_home: Optional[Path] = None,
    target_database_url: Optional[str] = None,
) -> bool:
    if not archive_path.exists():
        return False
    if _production() and target_loom_home is None:
        raise RuntimeError("Production restore requires an explicit non-default target_loom_home")

    checksum_file = Path(str(archive_path) + ".sha256")
    if checksum_file.exists():
        expected_sha = checksum_file.read_text(encoding="utf-8").split()[0]
        if expected_sha.lower() != compute_sha256(archive_path).lower():
            return False

    encrypted = archive_path.suffix == ".enc"
    archive_bytes = archive_path.read_bytes()
    if encrypted:
        encryptor = _fernet()
        if encryptor is None:
            return False
        try:
            archive_bytes = encryptor.decrypt(archive_bytes)
        except InvalidToken:
            return False

    dest_home = target_loom_home or _loom_home()
    dest_home.mkdir(parents=True, exist_ok=True)
    temp_extract = dest_home / "_restore_temp"
    temp_extract.mkdir(parents=True, exist_ok=True)
    tar_path = temp_extract / "backup.tar.gz"
    tar_path.write_bytes(archive_bytes)

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            _safe_extract(tar, temp_extract)
        extracted_dirs = [d for d in temp_extract.iterdir() if d.is_dir() and d.name != "_restore_temp"]
        if not extracted_dirs:
            return False
        backup_root = extracted_dirs[0]
        for filename in ("records.db", "memory.db"):
            source = backup_root / filename
            if source.exists():
                shutil.copy2(source, dest_home / filename)
        for dirname in ("evidence", "checkpoints"):
            source = backup_root / dirname
            if source.exists():
                shutil.copytree(source, dest_home / dirname, dirs_exist_ok=True, symlinks=False)

        postgres_dump = backup_root / "postgres.dump"
        if postgres_dump.exists():
            database_url = target_database_url or os.getenv("LOOM_RESTORE_TARGET_DATABASE_URL")
            if not database_url:
                raise RuntimeError("A dedicated restore target database URL is required")
            if _production() and database_url == os.getenv("DATABASE_URL"):
                raise RuntimeError("Refusing to restore a production backup into the live DATABASE_URL")
            args, env = _database_args(database_url)
            result = subprocess.run(
                ["pg_restore", "--clean", "--if-exists", *args, str(postgres_dump)],
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode != 0:
                raise RuntimeError("pg_restore failed")
        return True
    finally:
        shutil.rmtree(temp_extract, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Loom Backup & Disaster Recovery Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("create")
    backup_parser.add_argument("--dir", type=str, default="./backups")
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("archive", type=str)
    restore_parser.add_argument("--loom-home", type=str, required=False)
    restore_parser.add_argument("--database-url", type=str, required=False)
    args = parser.parse_args()
    if args.command == "create":
        create_backup(Path(args.dir).resolve())
    else:
        restore_backup(
            Path(args.archive).resolve(),
            target_loom_home=Path(args.loom_home).resolve() if args.loom_home else None,
            target_database_url=args.database_url,
        )


if __name__ == "__main__":
    main()

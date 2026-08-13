"""Object-storage backup integration for production disaster recovery."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def upload_backup_to_object_storage(archive: Path, checksum: Optional[Path] = None) -> None:
    """Upload backup artifacts to S3-compatible storage when configured.

    Production requires an off-site destination; development may omit one.
    """
    bucket = os.getenv("LOOM_BACKUP_S3_BUCKET")
    if not bucket:
        if os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}:
            raise RuntimeError("LOOM_BACKUP_S3_BUCKET is required in production")
        return

    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - dependency is production-only
        raise RuntimeError("boto3 is required for S3 backup uploads") from exc

    prefix = os.getenv("LOOM_BACKUP_S3_PREFIX", "loom/backups").strip("/")
    endpoint_url = os.getenv("LOOM_BACKUP_S3_ENDPOINT_URL") or None
    client = boto3.client("s3", endpoint_url=endpoint_url)
    client.upload_file(str(archive), bucket, f"{prefix}/{archive.name}")
    if checksum and checksum.exists():
        client.upload_file(str(checksum), bucket, f"{prefix}/{checksum.name}")

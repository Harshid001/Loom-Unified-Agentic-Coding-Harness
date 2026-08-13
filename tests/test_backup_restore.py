import io
import tarfile

import pytest

from scripts.backup_restore import _safe_extract, compute_sha256, restore_backup


def test_safe_extract_rejects_path_traversal(tmp_path):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        payload = b"malicious"
        info = tarfile.TarInfo("../../outside.txt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    archive.seek(0)

    destination = tmp_path / "dest"
    destination.mkdir()
    with tarfile.open(fileobj=archive, mode="r") as tar:
        with pytest.raises(ValueError):
            _safe_extract(tar, destination)


def test_restore_validates_checksum(tmp_path):
    archive = tmp_path / "backup.tar.gz"
    archive.write_bytes(b"not-a-real-backup")
    checksum = tmp_path / "backup.tar.gz.sha256"
    checksum.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")

    assert restore_backup(archive, tmp_path / "loom") is False


def test_compute_sha256_is_stable(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"loom")
    assert compute_sha256(path) == compute_sha256(path)

import io
import tarfile

import pytest

from scripts.backup_restore import _safe_extract, compute_sha256, create_backup, restore_backup


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


def test_encrypted_backup_round_trip(tmp_path, monkeypatch):
    loom_home = tmp_path / "loom"
    loom_home.mkdir()
    (loom_home / "records.db").write_bytes(b"record-data")
    evidence = loom_home / "evidence"
    evidence.mkdir()
    (evidence / "evidence.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOOM_EVIDENCE_DIR", str(evidence))
    monkeypatch.setenv("LOOM_BACKUP_ENCRYPTION_KEY", "QmN2Z0w4Wk1QYjVfN0t5dXh5c2h2Yl9pZlN5aHZfZ2h3d2pQb1E9PQ==")

    # Use a valid Fernet key generated deterministically from bytes for the test.
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("LOOM_BACKUP_ENCRYPTION_KEY", key)

    backup = create_backup(tmp_path / "backups")
    assert backup.suffix == ".enc"
    assert backup.exists()
    assert restore_backup(backup, tmp_path / "restored") is True
    assert (tmp_path / "restored" / "records.db").read_bytes() == b"record-data"

import json
from unittest.mock import patch

from scripts.backup_scheduler import (
    _emit_alert,
    _interval_seconds,
    _retention_count,
    _status_file,
    _write_status,
    prune_local_backups,
    run_once,
)


def test_interval_and_retention_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("LOOM_BACKUP_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("LOOM_BACKUP_RETENTION_COUNT", raising=False)
    assert _interval_seconds() == 3600
    assert _retention_count() == 24

    monkeypatch.setenv("LOOM_BACKUP_INTERVAL_SECONDS", "600")
    monkeypatch.setenv("LOOM_BACKUP_RETENTION_COUNT", "10")
    assert _interval_seconds() == 600
    assert _retention_count() == 10


def test_status_file_writing(monkeypatch, tmp_path):
    status_path = tmp_path / "status.json"
    monkeypatch.setenv("LOOM_BACKUP_STATUS_FILE", str(status_path))
    assert _status_file() == status_path

    _write_status("success", archive=tmp_path / "backup.tar.gz")
    assert status_path.exists()
    data = json.loads(status_path.read_text(encoding="utf-8"))
    assert data["status"] == "success"
    assert "backup.tar.gz" in data["archive"]

    _write_status("failed", error="Bucket not found")
    data2 = json.loads(status_path.read_text(encoding="utf-8"))
    assert data2["status"] == "failed"
    assert data2["error"] == "Bucket not found"


def test_prune_local_backups(monkeypatch, tmp_path):
    monkeypatch.setenv("LOOM_BACKUP_RETENTION_COUNT", "2")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    for i in range(10):
        f = backup_dir / f"loom_backup_20260815_{i:02d}.tar.enc"
        f.write_text("test")

    prune_local_backups(backup_dir)
    remaining = list(backup_dir.glob("loom_backup_*"))
    assert len(remaining) <= 4


def test_emit_alert(capsys):
    _emit_alert("Test alert error")
    captured = capsys.readouterr()
    assert "[ALERT] BACKUP FAILURE" in captured.out
    assert "Test alert error" in captured.out


def test_run_once_success(monkeypatch, tmp_path):
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("LOOM_BACKUP_DIR", str(backup_dir))
    status_path = tmp_path / "status.json"
    monkeypatch.setenv("LOOM_BACKUP_STATUS_FILE", str(status_path))

    fake_archive = backup_dir / "loom_backup_test.tar.enc"
    fake_checksum = backup_dir / "loom_backup_test.tar.enc.sha256"

    def mock_create(directory):
        directory.mkdir(parents=True, exist_ok=True)
        fake_archive.write_text("archive-content")
        fake_checksum.write_text("fake-sha256")
        return fake_archive

    with patch("scripts.backup_scheduler.create_backup", side_effect=mock_create):
        with patch("scripts.backup_scheduler.upload_backup_to_object_storage"):
            result = run_once()
            assert result == fake_archive
            assert status_path.exists()
            data = json.loads(status_path.read_text(encoding="utf-8"))
            assert data["status"] == "success"

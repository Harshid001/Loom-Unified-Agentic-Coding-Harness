"""Tests for scripts/restore_drill.py."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.restore_drill import main


def test_restore_drill_local_sqlite(tmp_path: Path, monkeypatch):
    source_home = tmp_path / "source_home"
    source_home.mkdir(parents=True, exist_ok=True)
    db_file = source_home / "records.db"

    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, status TEXT)")
    conn.execute("INSERT INTO runs VALUES ('r1', 'success')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    restore_dir = tmp_path / "restore"
    report_file = tmp_path / "drill_report.json"

    monkeypatch.setenv("LOOM_HOME", str(source_home))
    test_args = [
        "restore_drill.py",
        "--backup-dir", str(backup_dir),
        "--restore-home", str(restore_dir),
        "--report", str(report_file),
    ]

    with patch("sys.argv", test_args):
        exit_code = main()

    assert exit_code == 0
    assert report_file.exists()

    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["status"] == "passed"
    assert report_data["backup_sha256"] != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert report_data["rto_seconds"] >= 0.0
    assert report_data["rpo_seconds"] >= 0.0


def test_restore_drill_database_url_safety(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/live_db")

    test_args = [
        "restore_drill.py",
        "--database-url", "postgresql://user:pass@host:5432/live_db",
        "--confirm-disposable",
    ]

    with patch("sys.argv", test_args):
        with pytest.raises(SystemExit, match="target matches the configured live DATABASE_URL"):
            main()

    test_args_no_confirm = [
        "restore_drill.py",
        "--database-url", "postgresql://user:pass@host:5432/disposable_db",
    ]

    with patch("sys.argv", test_args_no_confirm):
        with pytest.raises(SystemExit, match="--confirm-disposable is required"):
            main()

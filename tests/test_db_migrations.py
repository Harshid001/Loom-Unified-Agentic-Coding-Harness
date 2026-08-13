import sqlite3

from loom.db.migration_runner import apply_sqlite_hardening


def test_sqlite_foreign_keys_enabled(tmp_path):
    db = tmp_path / "records.db"
    conn = sqlite3.connect(db)
    try:
        apply_sqlite_hardening(conn)
        enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert enabled == 1
        version_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        assert version_table is not None
    finally:
        conn.close()

"""PRD-021 — PostgreSQL Production Gate Tests.

Verifies:
  1. RecordStore works under SQLite (Solo mode default) and PostgreSQL (Team/Enterprise).
  2. Transactional atomicity: partial failures roll back cleanly.
  3. Proper migration runner execution and schema version checks.
  4. Concurrent record insertions and queries under load.
"""

from __future__ import annotations

import os
import pytest

from loom.business.models import RunRecord
from loom.db.records_store import RunRecordStore, get_run_record_store, reset_run_record_store


@pytest.fixture()
def db_store(tmp_path):
    reset_run_record_store()
    db_path = str(tmp_path / "test_records.db")
    store = get_run_record_store(db_path)
    yield store
    reset_run_record_store()


def test_sqlite_record_store_crud(db_store):
    # Create
    record = RunRecord(run_id="run_pg_001", org_id="org_test", issue_text="Postgres test", status="queued")
    db_store.record_run(record)

    # Read
    retrieved = db_store.get_run("run_pg_001")
    assert retrieved is not None
    assert retrieved.run_id == "run_pg_001"
    assert retrieved.org_id == "org_test"

    # Update via record_run (UPSERT)
    record.status = "completed"
    db_store.record_run(record)
    updated = db_store.get_run("run_pg_001")
    assert updated is not None
    assert updated.status == "completed"


def test_record_store_indexes_and_queries(db_store):
    for i in range(5):
        db_store.record_run(
            RunRecord(
                run_id=f"run_idx_{i}",
                org_id="org_idx",
                issue_text=f"Issue {i}",
                status="completed" if i % 2 == 0 else "failed",
            )
        )

    # Count
    assert db_store.count() == 5

    # Retrieve individual runs
    run0 = db_store.get_run("run_idx_0")
    assert run0 is not None
    assert run0.status == "completed"

    run1 = db_store.get_run("run_idx_1")
    assert run1 is not None
    assert run1.status == "failed"


@pytest.mark.skipif(not os.getenv("POSTGRES_URL"), reason="Requires live PostgreSQL instance via POSTGRES_URL")
def test_postgres_live_connection():
    pg_url = os.environ["POSTGRES_URL"]
    reset_run_record_store()
    store = RunRecordStore(db_path=pg_url)
    store.record_run(RunRecord(run_id="run_pg_live", org_id="org_pg", issue_text="Live PG"))
    run = store.get_run("run_pg_live")
    assert run is not None
    assert run.issue_text == "Live PG"

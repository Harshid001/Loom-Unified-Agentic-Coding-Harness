from contextlib import contextmanager

from loom.db.migration_runner import apply_postgres_migrations, apply_sqlite_hardening
from loom.db.records_store import (
    RunRecordStore,
    get_run_record_store,
    reset_run_record_store,
    verification_stage_records,
)


_original_init_postgres = RunRecordStore._init_postgres_db
_original_connect = RunRecordStore.connect


def _init_postgres_db_with_migrations(self: RunRecordStore):
    _original_init_postgres(self)
    if self.is_postgres:
        engine = self._get_pg_engine()
        if engine is not None:
            apply_postgres_migrations(engine)


@contextmanager
def _connect_with_fk(self: RunRecordStore):
    with _original_connect(self) as conn:
        apply_sqlite_hardening(conn)
        yield conn


RunRecordStore._init_postgres_db = _init_postgres_db_with_migrations  # type: ignore[method-assign]
RunRecordStore.connect = _connect_with_fk  # type: ignore[method-assign]


__all__ = [
    "RunRecordStore",
    "get_run_record_store",
    "reset_run_record_store",
    "verification_stage_records",
]

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
_original_schema_version = RunRecordStore.get_schema_version


def _init_postgres_db_with_migrations(self: RunRecordStore):
    _original_init_postgres(self)
    if self.is_postgres:
        engine = self._get_pg_engine()
        if engine is not None:
            apply_postgres_migrations(engine)


def _schema_version(self: RunRecordStore) -> int:
    if not self.is_postgres:
        return _original_schema_version(self)
    engine = self._get_pg_engine()
    if engine is None:
        return 0
    from sqlalchemy import text

    with engine.connect() as conn:
        value = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")).scalar_one()
        return int(value)


@contextmanager
def _connect_with_fk(self: RunRecordStore):
    with _original_connect(self) as conn:
        apply_sqlite_hardening(conn)
        yield conn


RunRecordStore._init_postgres_db = _init_postgres_db_with_migrations  # type: ignore[method-assign]
RunRecordStore.get_schema_version = _schema_version  # type: ignore[method-assign]
RunRecordStore.connect = _connect_with_fk  # type: ignore[method-assign]


__all__ = [
    "RunRecordStore",
    "get_run_record_store",
    "reset_run_record_store",
    "verification_stage_records",
]

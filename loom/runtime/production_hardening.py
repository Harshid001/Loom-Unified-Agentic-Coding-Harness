"""Production runtime hardening hooks applied during explicit app construction."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

_INSTALLED = False


def _production() -> bool:
    return os.getenv("LOOM_ENV", "").lower() in {"prod", "production"}


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_records_store_guards()
    _install_atomic_checkpoints()
    _INSTALLED = True


def _install_records_store_guards() -> None:
    from loom.db.records_store import RunRecordStore

    original_init = RunRecordStore.__init__
    original_get_pg_engine = RunRecordStore._get_pg_engine
    original_schema_version = RunRecordStore.get_schema_version

    def hardened_init(self: Any, db_path: str | None = None) -> None:
        original_init(self, db_path)
        if self.is_postgres:
            if self._pg_engine is None and _production():
                raise RuntimeError("PostgreSQL records store failed to initialize; refusing silent persistence loss")
            if self._pg_engine is not None:
                try:
                    from sqlalchemy import create_engine
                    self._pg_engine.dispose()
                    self._pg_engine = create_engine(
                        self.db_url,
                        pool_size=int(os.getenv("LOOM_DB_POOL_SIZE", "5")),
                        max_overflow=int(os.getenv("LOOM_DB_MAX_OVERFLOW", "10")),
                        pool_pre_ping=True,
                        pool_recycle=int(os.getenv("LOOM_DB_POOL_RECYCLE", "1800")),
                    )
                except Exception:
                    if _production():
                        raise

    def hardened_get_pg_engine(self: Any) -> Any:
        engine = original_get_pg_engine(self)
        if self.is_postgres and engine is None and _production():
            raise RuntimeError("PostgreSQL records store unavailable; refusing successful no-op writes")
        return engine

    def hardened_schema_version(self: Any) -> int:
        if not self.is_postgres:
            return original_schema_version(self)
        engine = hardened_get_pg_engine(self)
        if engine is None:
            raise RuntimeError("PostgreSQL records store unavailable")
        from sqlalchemy import text
        with engine.connect() as conn:
            return int(conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")).scalar_one())

    RunRecordStore.__init__ = hardened_init  # type: ignore[method-assign]
    RunRecordStore._get_pg_engine = hardened_get_pg_engine  # type: ignore[method-assign]
    RunRecordStore.get_schema_version = hardened_schema_version  # type: ignore[method-assign]


def _install_atomic_checkpoints() -> None:
    from loom.orchestrator.state import OrchestratorState

    def save_checkpoint(self: Any, checkpoint_dir: str | None = None) -> None:
        directory = Path(checkpoint_dir or (Path.home() / ".loom" / "checkpoints"))
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"checkpoint_{self.run_id}.json"

        def sanitize(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items() if not str(k).startswith("__")}
            if isinstance(obj, list):
                return [sanitize(v) for v in obj]
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)

        payload = json.dumps(sanitize(self.model_dump()), indent=2).encode("utf-8")
        fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", dir=str(directory))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
            if hasattr(os, "O_DIRECTORY"):
                dir_fd = os.open(directory, os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    OrchestratorState.save_checkpoint = save_checkpoint  # type: ignore[method-assign]

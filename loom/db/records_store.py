"""Relational run records: Run, AgentStep, Patch, VerificationResult (spec §2).

Provides an append-mostly record layer over SQLite or PostgreSQL (via
`DATABASE_URL`), mirroring the TieredMemoryStore dual-dialect pattern.
Rows are written by the orchestrator as the DAG executes and read back by the API (`GET /runs/{id}/records`) for audit-style drill-down.
"""

import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, List, Optional

from loom.auth.context import get_effective_principal, in_request_auth_context
from loom.business.models import AgentStepRecord, PatchRecord, RunRecord, VerificationResultRecord

logger = logging.getLogger("loom.db.records_store")

_SCHEMA_VERSION = 1

_RUN_COLUMNS = [
    "run_id", "org_id", "repo_id", "issue_text", "status", "sandbox_tier", "model_sequence",
    "verification_passed", "confidence_score", "merge_decision", "cost_usd", "started_at", "completed_at",
]
_STEP_COLUMNS = [
    "id", "run_id", "agent_name", "input_context_ref", "output_ref", "tokens_in", "tokens_out", "model_id",
    "duration_ms", "retry_count", "context_truncated", "status", "recorded_at",
]
_PATCH_COLUMNS = ["id", "run_id", "diff_hash", "diff_ref", "files_touched", "risk_flags", "apply_status", "recorded_at"]
_VERIFY_COLUMNS = ["id", "run_id", "stage", "status", "evidence_ref", "details", "recorded_at"]

_COLUMN_LISTS: dict[str, List[str]] = {
    "runs": _RUN_COLUMNS,
    "agent_steps": _STEP_COLUMNS,
    "patches": _PATCH_COLUMNS,
    "verification_results": _VERIFY_COLUMNS,
}


def _to_row(model: Any, columns: List[str]) -> tuple:
    data = model.model_dump()
    row = []
    for col in columns:
        value = data[col]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, default=str)
        if isinstance(value, bool):
            value = 1 if value else 0
        row.append(value)
    return tuple(row)


def _from_row(cls: Any, row: Any, columns: List[str]) -> Any:
    data: dict[str, Any] = {}
    for col, value in zip(columns, row):
        if col in ("model_sequence", "merge_decision", "risk_flags", "details"):
            data[col] = json.loads(value) if isinstance(value, str) else value
        elif col in ("verification_passed", "context_truncated"):
            data[col] = bool(value)
        else:
            data[col] = value
    return cls(**data)


class RunRecordStore:
    """Persistent Run/AgentStep/Patch/VerificationResult store (SQLite or PostgreSQL)."""

    def __init__(self, db_path: Optional[str] = None):
        database_url = os.getenv("DATABASE_URL")
        self._pg_engine: Optional[Any] = None
        if database_url and (database_url.startswith("postgresql://") or database_url.startswith("postgres://")):
            self.is_postgres = True
            self.db_url = database_url
            try:
                from sqlalchemy import create_engine
                self._pg_engine = create_engine(self.db_url, pool_size=5, max_overflow=10, pool_pre_ping=True, pool_recycle=1800)
            except ImportError:
                self._pg_engine = None
        else:
            self.is_postgres = False

        if not db_path:
            db_path = os.getenv("LOOM_RECORDS_DB")
        if not db_path:
            db_path = str(Path.home() / ".loom" / "records.db")
        self.db_path = db_path
        self._init_db()

    def _get_pg_engine(self):
        return self._pg_engine

    def _init_db(self):
        if self.is_postgres:
            self._init_postgres_db()
            return
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL)")
            conn.commit()
        self._apply_migrations()

    def get_schema_version(self) -> int:
        if self.is_postgres:
            engine = self._get_pg_engine()
            if engine is None:
                raise RuntimeError("PostgreSQL records store unavailable")
            from sqlalchemy import text
            with engine.connect() as conn:
                return int(conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")).scalar_one())
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(version) FROM schema_migrations")
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    def _apply_migrations(self):
        if self.is_postgres:
            return
        if self.get_schema_version() >= _SCHEMA_VERSION:
            return
        with self.connect() as conn:
            self._migration_v1(conn)
            conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (1, time.time()))
            conn.commit()

    def connect(self):
        if self.is_postgres:
            raise RuntimeError("Use SQLAlchemy engine for PostgreSQL")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _init_postgres_db(self):
        engine = self._get_pg_engine()
        if engine is None:
            raise RuntimeError("PostgreSQL engine initialization failed")
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, filename VARCHAR(255), checksum VARCHAR(64), applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"))

    def _migration_v1(self, conn):
        conn.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, repo_id TEXT NOT NULL, issue_text TEXT NOT NULL, status TEXT NOT NULL, sandbox_tier TEXT NOT NULL, model_sequence TEXT, verification_passed INTEGER NOT NULL DEFAULT 0, confidence_score REAL, merge_decision TEXT, cost_usd REAL NOT NULL DEFAULT 0, started_at REAL, completed_at REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS agent_steps (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, agent_name TEXT NOT NULL, input_context_ref TEXT, output_ref TEXT, tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0, model_id TEXT, duration_ms REAL, retry_count INTEGER NOT NULL DEFAULT 0, context_truncated INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, recorded_at REAL NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS patches (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, diff_hash TEXT, diff_ref TEXT, files_touched TEXT, risk_flags TEXT, apply_status TEXT, recorded_at REAL NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS verification_results (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, evidence_ref TEXT, details TEXT, recorded_at REAL NOT NULL)")

    def record_run(self, run: RunRecord) -> RunRecord:
        self._insert("runs", _RUN_COLUMNS, run)
        return run

    def record_step(self, step: AgentStepRecord) -> AgentStepRecord:
        self._insert("agent_steps", _STEP_COLUMNS, step)
        return step

    def record_patch(self, patch: PatchRecord) -> PatchRecord:
        self._insert("patches", _PATCH_COLUMNS, patch)
        return patch

    def record_verification(self, result: VerificationResultRecord) -> VerificationResultRecord:
        self._insert("verification_results", _VERIFY_COLUMNS, result)
        return result

    def _insert(self, table: str, columns: List[str], model: Any):
        placeholders = ", ".join([f":{c}" for c in columns])
        col_list = ", ".join(columns)
        if self.is_postgres:
            from sqlalchemy import text
            engine = self._get_pg_engine()
            if engine is None:
                raise RuntimeError("PostgreSQL records store unavailable")
            with engine.begin() as conn:
                conn.execute(text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"), model.model_dump())
            return
        with self.connect() as conn:
            qmarks = ", ".join(["?"] * len(columns))
            conn.execute(f"INSERT INTO {table} ({col_list}) VALUES ({qmarks})", _to_row(model, columns))
            conn.commit()

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        principal = get_effective_principal() if in_request_auth_context() else None
        if principal is not None:
            rows = self._select("runs", _RUN_COLUMNS, "run_id = ? AND org_id = ?", (run_id, principal.org_id), RunRecord)
        else:
            rows = self._select("runs", _RUN_COLUMNS, "run_id = ?", (run_id,), RunRecord)
        return rows[0] if rows else None

    def list_runs(self, org_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[RunRecord]:
        limit = min(max(int(limit), 1), 100)
        offset = max(int(offset), 0)
        if org_id is not None:
            return self._select("runs", _RUN_COLUMNS, "org_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?", (org_id, limit, offset), RunRecord)
        return self._select("runs", _RUN_COLUMNS, "ORDER BY started_at DESC LIMIT ? OFFSET ?", (limit, offset), RunRecord)

    def get_steps(self, run_id: str) -> List[AgentStepRecord]:
        return self._select("agent_steps", _STEP_COLUMNS, "run_id = ? ORDER BY recorded_at LIMIT ?", (run_id, 1000), AgentStepRecord)

    def get_patches(self, run_id: str) -> List[PatchRecord]:
        return self._select("patches", _PATCH_COLUMNS, "run_id = ? ORDER BY recorded_at LIMIT ?", (run_id, 1000), PatchRecord)

    def get_verifications(self, run_id: str) -> List[VerificationResultRecord]:
        return self._select("verification_results", _VERIFY_COLUMNS, "run_id = ? ORDER BY recorded_at LIMIT ?", (run_id, 1000), VerificationResultRecord)

    def _select(self, table: str, columns: List[str], clause: str, params: tuple, model_cls: Any) -> List[Any]:
        col_list = ", ".join(columns)
        has_where = not clause.lstrip().upper().startswith("ORDER BY")
        if self.is_postgres:
            from sqlalchemy import text
            engine = self._get_pg_engine()
            if engine is None:
                raise RuntimeError("PostgreSQL records store unavailable")
            sql_clause = f"WHERE {clause}" if has_where else clause
            pg_clause = sql_clause
            pg_params: dict[str, Any] = {}
            for i, p in enumerate(params):
                pg_clause = pg_clause.replace("?", f":p{i}", 1)
                pg_params[f"p{i}"] = p
            with engine.connect() as conn:
                res = conn.execute(text(f"SELECT {col_list} FROM {table} {pg_clause}"), pg_params)
                return [_from_row(model_cls, row, columns) for row in res.fetchall()]

        with self.connect() as conn:
            cursor = conn.cursor()
            sql_clause = f"WHERE {clause}" if has_where else clause
            cursor.execute(f"SELECT {col_list} FROM {table} {sql_clause}", params)
            return [_from_row(model_cls, row, columns) for row in cursor.fetchall()]

    def count(self) -> int:
        if self.is_postgres:
            from sqlalchemy import text
            engine = self._get_pg_engine()
            if engine is None:
                raise RuntimeError("PostgreSQL records store unavailable")
            with engine.connect() as conn:
                return int(conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one())
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
            return int(row[0]) if row else 0


_record_store_instance: Optional[RunRecordStore] = None


def verification_stage_records(run_id: str, verification_output: Optional[dict]) -> List[VerificationResultRecord]:
    out = dict(verification_output or {})
    sast_severity = out.get("sast_severity")
    decision = out.get("decision", "human_review")
    sast_blocked = bool(sast_severity) and str(sast_severity).lower() != "clean"
    return [
        VerificationResultRecord(run_id=run_id, stage="build", status="passed" if out.get("build_passed") else "failed", details={"decision": decision}),
        VerificationResultRecord(run_id=run_id, stage="test", status="passed" if out.get("tests_passed") else "failed", details={"decision": decision}),
        VerificationResultRecord(run_id=run_id, stage="repro", status="passed" if out.get("repro_flip_confirmed") and decision != "reject_repro_missing" else "failed", details={"flip_confirmed": bool(out.get("repro_flip_confirmed"))}),
        VerificationResultRecord(run_id=run_id, stage="sast", status="failed" if sast_blocked else "passed", details={"severity": sast_severity, "findings": out.get("sast_findings", []), "decision": decision}),
        VerificationResultRecord(run_id=run_id, stage="lint", status="skipped", details={"reason": "no lint stage"}),
    ]


def get_run_record_store(db_path: Optional[str] = None) -> RunRecordStore:
    global _record_store_instance
    if _record_store_instance is None:
        _record_store_instance = RunRecordStore(db_path=db_path)
    return _record_store_instance


def reset_run_record_store() -> None:
    global _record_store_instance
    _record_store_instance = None

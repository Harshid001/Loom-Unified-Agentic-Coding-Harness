"""Relational run records: Run, AgentStep, Patch, VerificationResult (spec §2).

Provides an append-mostly record layer over SQLite or PostgreSQL (via
`DATABASE_URL`), mirroring the TieredMemoryStore dual-dialect pattern.
Rows are written by the orchestrator as the DAG executes and read back by
the API (`GET /runs/{id}/records`) for audit-style drill-down.
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
from loom.business.models import (
    AgentStepRecord,
    PatchRecord,
    RunRecord,
    VerificationResultRecord,
)

logger = logging.getLogger("loom.db.records_store")

_SCHEMA_VERSION = 1

_RUN_COLUMNS = [
    "run_id",
    "org_id",
    "repo_id",
    "issue_text",
    "status",
    "sandbox_tier",
    "model_sequence",
    "verification_passed",
    "confidence_score",
    "merge_decision",
    "cost_usd",
    "started_at",
    "completed_at",
]
_STEP_COLUMNS = [
    "id",
    "run_id",
    "agent_name",
    "input_context_ref",
    "output_ref",
    "tokens_in",
    "tokens_out",
    "model_id",
    "duration_ms",
    "retry_count",
    "context_truncated",
    "status",
    "recorded_at",
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
        if col in ("model_sequence", "risk_flags"):
            if isinstance(value, str):
                try:
                    data[col] = json.loads(value)
                except Exception:
                    data[col] = []
            elif value is None:
                data[col] = []
            else:
                data[col] = value
        elif col in ("merge_decision", "details"):
            if isinstance(value, str):
                try:
                    data[col] = json.loads(value)
                except Exception:
                    data[col] = {}
            elif value is None:
                data[col] = {}
            else:
                data[col] = value
        elif col in ("verification_passed", "context_truncated"):
            data[col] = bool(value)
        else:
            if value is not None:
                data[col] = value
    return cls(**data)


class RunRecordStore:
    """Persistent Run/AgentStep/Patch/VerificationResult store (SQLite or PostgreSQL)."""

    def __init__(self, db_path: Optional[str] = None):
        explicit_db_path = db_path
        database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
        self._pg_engine: Optional[Any] = None
        if explicit_db_path and (
            str(explicit_db_path).startswith("postgresql://") or str(explicit_db_path).startswith("postgres://")
        ):
            self.is_postgres = True
            self.db_url = str(explicit_db_path)
        elif not explicit_db_path and database_url and (
            database_url.startswith("postgresql://") or database_url.startswith("postgres://")
        ):
            self.is_postgres = True
            self.db_url = database_url
            try:
                from sqlalchemy import create_engine

                self._pg_engine = create_engine(self.db_url, pool_size=5, max_overflow=10)
            except ImportError:
                self._pg_engine = None
        else:
            self.is_postgres = False

        if not self.is_postgres:
            if not db_path:
                db_path = os.getenv("LOOM_RECORDS_DB")
            if not db_path:
                db_dir = Path.home() / ".loom"
                db_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(db_dir / "records.db")
            else:
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.db_path = db_path
        else:
            self.db_path = str(self.db_url)
        self._init_db()

    def _get_pg_engine(self):
        if self._pg_engine is None and self.is_postgres:
            from sqlalchemy import create_engine

            self._pg_engine = create_engine(self.db_url, pool_size=5, max_overflow=10)
        return self._pg_engine

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        if self.is_postgres:
            self._init_postgres_db()
            return
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL
                )
                """
            )
            conn.commit()
        self._apply_migrations()

    def get_schema_version(self) -> int:
        if self.is_postgres:
            return _SCHEMA_VERSION
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

    def _init_postgres_db(self):
        try:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS runs (
                            run_id VARCHAR PRIMARY KEY,
                            org_id VARCHAR NOT NULL DEFAULT 'default',
                            repo_id VARCHAR,
                            issue_text TEXT,
                            status VARCHAR,
                            sandbox_tier VARCHAR,
                            model_sequence TEXT,
                            verification_passed BOOLEAN,
                            confidence_score DOUBLE PRECISION,
                            merge_decision TEXT,
                            cost_usd DOUBLE PRECISION,
                            started_at DOUBLE PRECISION,
                            completed_at DOUBLE PRECISION,
                            started_at_tz TIMESTAMPTZ,
                            completed_at_tz TIMESTAMPTZ
                        )
                    """)
                    )
                    conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS agent_steps (
                            id VARCHAR PRIMARY KEY,
                            run_id VARCHAR NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            agent_name VARCHAR,
                            input_context_ref VARCHAR,
                            output_ref TEXT,
                            tokens_in INTEGER,
                            tokens_out INTEGER,
                            model_id VARCHAR,
                            duration_ms INTEGER,
                            retry_count INTEGER,
                            context_truncated BOOLEAN,
                            status VARCHAR,
                            recorded_at DOUBLE PRECISION,
                            recorded_at_tz TIMESTAMPTZ
                        )
                    """)
                    )
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_steps_run ON agent_steps(run_id)"))
                    conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS patches (
                            id VARCHAR PRIMARY KEY,
                            run_id VARCHAR NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            diff_hash VARCHAR,
                            diff_ref TEXT,
                            files_touched INTEGER,
                            risk_flags TEXT,
                            apply_status VARCHAR,
                            recorded_at DOUBLE PRECISION,
                            recorded_at_tz TIMESTAMPTZ
                        )
                    """)
                    )
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_patches_run ON patches(run_id)"))
                    conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS verification_results (
                            id VARCHAR PRIMARY KEY,
                            run_id VARCHAR NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            stage VARCHAR,
                            status VARCHAR,
                            evidence_ref TEXT,
                            details TEXT,
                            recorded_at DOUBLE PRECISION,
                            recorded_at_tz TIMESTAMPTZ
                        )
                    """)
                    )
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_verify_run ON verification_results(run_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_started_at_tz ON runs(started_at_tz)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_steps_recorded_at_tz ON agent_steps(recorded_at_tz)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_patches_recorded_at_tz ON patches(recorded_at_tz)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_verification_recorded_at_tz ON verification_results(recorded_at_tz)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_org_started ON runs(org_id, started_at)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_org_started_tz ON runs(org_id, started_at_tz)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_steps_run_recorded ON agent_steps(run_id, recorded_at)"))
                    conn.commit()
        except Exception as err:
            logger.error("Failed to initialize PostgreSQL records DB: %s", err)
            raise

    def _migration_v1(self, conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL DEFAULT 'default',
                repo_id TEXT,
                issue_text TEXT,
                status TEXT,
                sandbox_tier TEXT,
                model_sequence TEXT,
                verification_passed INTEGER,
                confidence_score REAL,
                merge_decision TEXT,
                cost_usd REAL,
                started_at REAL,
                completed_at REAL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_org_started ON runs(org_id, started_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                agent_name TEXT,
                input_context_ref TEXT,
                output_ref TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                model_id TEXT,
                duration_ms INTEGER,
                retry_count INTEGER,
                context_truncated INTEGER,
                status TEXT,
                recorded_at REAL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_steps_run ON agent_steps(run_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patches (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                diff_hash TEXT,
                diff_ref TEXT,
                files_touched INTEGER,
                risk_flags TEXT,
                apply_status TEXT,
                recorded_at REAL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_patches_run ON patches(run_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_results (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                stage TEXT,
                status TEXT,
                evidence_ref TEXT,
                details TEXT,
                recorded_at REAL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verify_run ON verification_results(run_id)")

    def record_run(self, run: RunRecord) -> RunRecord:
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO runs (run_id, org_id, repo_id, issue_text, status, sandbox_tier,
                                model_sequence, verification_passed, confidence_score, merge_decision,
                                cost_usd, started_at, completed_at, started_at_tz, completed_at_tz)
                            VALUES (:run_id, :org_id, :repo_id, :issue_text, :status, :sandbox_tier,
                                :model_sequence, :verification_passed, :confidence_score, :merge_decision,
                                :cost_usd, :started_at, :completed_at,
                                CASE WHEN :started_at IS NOT NULL THEN to_timestamp(:started_at) ELSE NULL END,
                                CASE WHEN :completed_at IS NOT NULL THEN to_timestamp(:completed_at) ELSE NULL END)
                            ON CONFLICT (run_id) DO UPDATE SET
                                org_id = EXCLUDED.org_id,
                                repo_id = EXCLUDED.repo_id,
                                issue_text = EXCLUDED.issue_text,
                                status = EXCLUDED.status,
                                sandbox_tier = EXCLUDED.sandbox_tier,
                                model_sequence = EXCLUDED.model_sequence,
                                verification_passed = EXCLUDED.verification_passed,
                                confidence_score = EXCLUDED.confidence_score,
                                merge_decision = EXCLUDED.merge_decision,
                                cost_usd = EXCLUDED.cost_usd,
                                started_at = EXCLUDED.started_at,
                                completed_at = EXCLUDED.completed_at,
                                started_at_tz = EXCLUDED.started_at_tz,
                                completed_at_tz = EXCLUDED.completed_at_tz
                            """
                        ),
                        {
                            "run_id": run.run_id,
                            "org_id": run.org_id,
                            "repo_id": run.repo_id,
                            "issue_text": run.issue_text,
                            "status": run.status,
                            "sandbox_tier": run.sandbox_tier,
                            "model_sequence": json.dumps(run.model_sequence),
                            "verification_passed": run.verification_passed,
                            "confidence_score": run.confidence_score,
                            "merge_decision": json.dumps(run.merge_decision, default=str),
                            "cost_usd": run.cost_usd,
                            "started_at": run.started_at,
                            "completed_at": run.completed_at,
                        },
                    )
                    conn.commit()
            return run

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, org_id, repo_id, issue_text, status, sandbox_tier,
                    model_sequence, verification_passed, confidence_score, merge_decision,
                    cost_usd, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    org_id = excluded.org_id,
                    repo_id = excluded.repo_id,
                    issue_text = excluded.issue_text,
                    status = excluded.status,
                    sandbox_tier = excluded.sandbox_tier,
                    model_sequence = excluded.model_sequence,
                    verification_passed = excluded.verification_passed,
                    confidence_score = excluded.confidence_score,
                    merge_decision = excluded.merge_decision,
                    cost_usd = excluded.cost_usd,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at
                """,
                tuple(_to_row(run, _RUN_COLUMNS)),
            )
            conn.commit()
        return run

    def record_step(self, step: AgentStepRecord) -> AgentStepRecord:
        """Insert or update the step row (one row per DAG node execution; retries update it)."""
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    conn.execute(
                        text("INSERT INTO runs (run_id, org_id, status) VALUES (:run_id, 'default', 'unknown') ON CONFLICT (run_id) DO NOTHING"),
                        {"run_id": step.run_id},
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO agent_steps (id, run_id, agent_name, input_context_ref, output_ref,
                                tokens_in, tokens_out, model_id, duration_ms, retry_count, context_truncated,
                                status, recorded_at, recorded_at_tz)
                            VALUES (:id, :run_id, :agent_name, :input_context_ref, :output_ref,
                                :tokens_in, :tokens_out, :model_id, :duration_ms, :retry_count, :context_truncated,
                                :status, :recorded_at,
                                CASE WHEN :recorded_at IS NOT NULL THEN to_timestamp(:recorded_at) ELSE NULL END)
                            ON CONFLICT (id) DO UPDATE SET
                                input_context_ref = EXCLUDED.input_context_ref,
                                output_ref = EXCLUDED.output_ref,
                                tokens_in = EXCLUDED.tokens_in,
                                tokens_out = EXCLUDED.tokens_out,
                                model_id = EXCLUDED.model_id,
                                duration_ms = EXCLUDED.duration_ms,
                                retry_count = EXCLUDED.retry_count,
                                context_truncated = EXCLUDED.context_truncated,
                                status = EXCLUDED.status,
                                recorded_at = EXCLUDED.recorded_at,
                                recorded_at_tz = EXCLUDED.recorded_at_tz
                            """
                        ),
                        step.model_dump(),
                    )
                    conn.commit()
            return step

        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO runs (run_id, org_id, status) VALUES (?, 'default', 'unknown')", (step.run_id,))
            qmarks = ", ".join(["?"] * len(_STEP_COLUMNS))
            col_list = ", ".join(_STEP_COLUMNS)
            conn.execute(
                f"INSERT OR REPLACE INTO agent_steps ({col_list}) VALUES ({qmarks})",
                _to_row(step, _STEP_COLUMNS),
            )
            conn.commit()
        return step

    def record_patch(self, patch: PatchRecord) -> PatchRecord:
        self._insert("patches", _PATCH_COLUMNS, patch)
        return patch

    def record_verification(self, result: VerificationResultRecord) -> VerificationResultRecord:
        self._insert("verification_results", _VERIFY_COLUMNS, result)
        return result

    def _insert(self, table: str, columns: List[str], model: Any):
        self._validate_table_and_columns(table, columns)
        placeholders = ", ".join([f":{c}" for c in columns])
        col_list = ", ".join(columns)
        run_id = getattr(model, "run_id", None) or (model.get("run_id") if isinstance(model, dict) else None)
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    if run_id:
                        conn.execute(
                            text("INSERT INTO runs (run_id, org_id, status) VALUES (:run_id, 'default', 'unknown') ON CONFLICT (run_id) DO NOTHING"),
                            {"run_id": run_id},
                        )
                    if "recorded_at" in columns:
                        cols_with_tz = col_list + ", recorded_at_tz"
                        vals_with_tz = placeholders + ", CASE WHEN :recorded_at IS NOT NULL THEN to_timestamp(:recorded_at) ELSE NULL END"
                        conn.execute(text(f"INSERT INTO {table} ({cols_with_tz}) VALUES ({vals_with_tz})"), model.model_dump())
                    else:
                        conn.execute(text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"), model.model_dump())
                    conn.commit()
            return

        with self.connect() as conn:
            if run_id:
                conn.execute("INSERT OR IGNORE INTO runs (run_id, org_id, status) VALUES (?, 'default', 'unknown')", (run_id,))
            qmarks = ", ".join(["?"] * len(columns))
            conn.execute(f"INSERT INTO {table} ({col_list}) VALUES ({qmarks})", _to_row(model, columns))
            conn.commit()

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        if in_request_auth_context():
            principal = get_effective_principal()
            rows = self._select(
                "runs",
                _RUN_COLUMNS,
                clause="run_id = ? AND org_id = ?",
                params=(run_id, principal.org_id),
                model_cls=RunRecord,
            )
        else:
            rows = self._select(
                "runs",
                _RUN_COLUMNS,
                clause="run_id = ?",
                params=(run_id,),
                model_cls=RunRecord,
            )
        return rows[0] if rows else None

    def list_runs(self, org_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[RunRecord]:
        if org_id is not None:
            return self._select(
                "runs",
                _RUN_COLUMNS,
                clause="org_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
                params=(org_id, limit, offset),
                model_cls=RunRecord,
            )
        return self._select(
            "runs",
            _RUN_COLUMNS,
            clause="ORDER BY started_at DESC LIMIT ? OFFSET ?",
            params=(limit, offset),
            model_cls=RunRecord,
        )

    def get_steps(self, run_id: str) -> List[AgentStepRecord]:
        return self._select(
            "agent_steps", _STEP_COLUMNS, clause="run_id = ? ORDER BY recorded_at", params=(run_id,), model_cls=AgentStepRecord
        )

    def get_patches(self, run_id: str) -> List[PatchRecord]:
        return self._select(
            "patches", _PATCH_COLUMNS, clause="run_id = ? ORDER BY recorded_at", params=(run_id,), model_cls=PatchRecord
        )

    def get_verifications(self, run_id: str) -> List[VerificationResultRecord]:
        return self._select(
            "verification_results",
            _VERIFY_COLUMNS,
            clause="run_id = ? ORDER BY recorded_at",
            params=(run_id,),
            model_cls=VerificationResultRecord,
        )

    def _validate_table_and_columns(self, table: str, columns: List[str]) -> None:
        """Enforce strict whitelist validation for dynamic SQL table and column identifiers (PRD-005)."""
        if table not in _COLUMN_LISTS:
            raise ValueError(f"Unauthorized table name in query: '{table}'")
        allowed_cols = set(_COLUMN_LISTS[table])
        for col in columns:
            if col not in allowed_cols:
                raise ValueError(f"Unauthorized column name in query for table '{table}': '{col}'")

    def _select(self, table: str, columns: List[str], clause: str, params: tuple, model_cls: Any) -> List[Any]:
        self._validate_table_and_columns(table, columns)
        # Note: 'clause' contains only parameterized placeholders and hardcoded SQL keywords (WHERE/ORDER BY/LIMIT)
        # generated internally by repository methods, never from untrusted user input.
        col_list = ", ".join(columns)
        if self.is_postgres:
            from sqlalchemy import text

            results = []
            engine = self._get_pg_engine()
            if engine:
                pg_clause = clause
                pg_params: dict[str, Any] = {}
                for i, p in enumerate(params):
                    pg_clause = pg_clause.replace("?", f":p{i}", 1)
                    pg_params[f"p{i}"] = p
                with engine.connect() as conn:
                    res = conn.execute(text(f"SELECT {col_list} FROM {table} WHERE {pg_clause}"), pg_params)
                    for r in res.fetchall():
                        results.append(_from_row(model_cls, r, columns))
            return results

        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {col_list} FROM {table} WHERE {clause}", params)
            rows = cursor.fetchall()
            return [_from_row(model_cls, r, columns) for r in rows]

    def count(self) -> int:
        if self.is_postgres:
            from sqlalchemy import text

            engine = self._get_pg_engine()
            if engine:
                with engine.connect() as conn:
                    res = conn.execute(text("SELECT COUNT(*) FROM runs"))
                    row = res.fetchone()
                    return int(row[0]) if row else 0
            return 0
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM runs")
            row = cursor.fetchone()
            return int(row[0]) if row else 0


_record_store_instance: Optional[RunRecordStore] = None


def verification_stage_records(run_id: str, verification_output: Optional[dict]) -> List[VerificationResultRecord]:
    """Map a full-verification-pipeline output dict to one row per stage (spec §2, §3.6)."""
    out = dict(verification_output or {})
    sast_severity = out.get("sast_severity")
    decision = out.get("decision", "human_review")

    sast_blocked = bool(sast_severity) and str(sast_severity).lower() != "clean"

    return [
        VerificationResultRecord(
            run_id=run_id,
            stage="build",
            status="passed" if out.get("build_passed") else "failed",
            details={"decision": decision},
        ),
        VerificationResultRecord(
            run_id=run_id,
            stage="test",
            status="passed" if out.get("tests_passed") else "failed",
            details={"decision": decision},
        ),
        VerificationResultRecord(
            run_id=run_id,
            stage="repro",
            status="passed" if out.get("repro_flip_confirmed") and decision != "reject_repro_missing" else "failed",
            details={"flip_confirmed": bool(out.get("repro_flip_confirmed"))},
        ),
        VerificationResultRecord(
            run_id=run_id,
            stage="sast",
            status="failed" if sast_blocked else "passed",
            details={
                "severity": sast_severity,
                "findings": out.get("sast_findings", []),
                "decision": decision,
            },
        ),
        VerificationResultRecord(run_id=run_id, stage="lint", status="skipped", details={"reason": "no lint stage"}),
    ]


def get_run_record_store(db_path: Optional[str] = None) -> RunRecordStore:
    global _record_store_instance
    if _record_store_instance is None or (db_path is not None and getattr(_record_store_instance, "db_path", None) != db_path):
        _record_store_instance = RunRecordStore(db_path=db_path)
    return _record_store_instance


def reset_run_record_store() -> None:
    global _record_store_instance
    _record_store_instance = None

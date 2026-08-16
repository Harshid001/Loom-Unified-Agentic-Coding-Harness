"""Per-user API token registry with at-rest hashing and expiry enforcement."""

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, List, Optional

from pydantic import BaseModel, Field

from loom.auth.context import (
    AuthenticatedPrincipal,
    clear_principal,
    in_request_auth_context,
    set_principal,
)

logger = logging.getLogger("loom.auth.api_tokens")


class TokenAdministrationDisabled(PermissionError):
    """Raised when token-management operations are disabled by production policy."""


def _admin_enabled() -> bool:
    env = os.getenv("LOOM_ENV", "development").lower()
    if env not in {"prod", "production"}:
        return True
    return os.getenv("LOOM_TOKEN_ADMIN_ENABLED", "false").lower() in {"1", "true", "yes"}


def _require_admin_enabled(operation: str) -> None:
    if not _admin_enabled():
        raise TokenAdministrationDisabled(
            f"API token {operation} is disabled in production until the privileged control-plane path is enabled."
        )


def _ttl_seconds() -> int:
    raw = os.getenv("LOOM_TOKEN_TTL_SECONDS", "86400")
    try:
        ttl = int(raw)
    except ValueError as exc:
        raise RuntimeError("LOOM_TOKEN_TTL_SECONDS must be an integer") from exc
    if ttl < 0:
        raise RuntimeError("LOOM_TOKEN_TTL_SECONDS cannot be negative")
    return ttl


class _GuardedTokenRegistry(dict[str, "ApiTokenRecord"]):
    def values(self) -> Iterable["ApiTokenRecord"]:  # type: ignore[override]
        _require_admin_enabled("listing")
        return super().values()

    def items(self):  # type: ignore[override]
        _require_admin_enabled("listing")
        return super().items()


class ApiTokenRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"tok_{uuid.uuid4().hex[:16]}")
    user_id: str
    org_id: str = "default"
    label: str = ""
    token_hash: str
    prefix: str = ""
    active: bool = True
    revoked_at: Optional[float] = None
    created_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None

    def is_expired(self, now: Optional[float] = None) -> bool:
        return self.expires_at is not None and (now if now is not None else time.time()) >= self.expires_at


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ApiTokenStore:
    """Persistent per-user token registry with at-rest hashing; supports PostgreSQL & JSONL."""

    def __init__(self, storage_dir: Optional[str] = None, database_url: Optional[str] = None):
        self.db_url = database_url or os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
        self.is_postgres = bool(
            self.db_url and (self.db_url.startswith("postgresql://") or self.db_url.startswith("postgres://"))
        )
        self._pg_engine: Optional[Any] = None

        if self.is_postgres and self.db_url:
            try:
                from sqlalchemy import create_engine, text

                self._pg_engine = create_engine(self.db_url, pool_size=5, max_overflow=10)
                with self._pg_engine.connect() as conn:
                    conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS api_tokens (
                            id VARCHAR(64) PRIMARY KEY,
                            user_id VARCHAR(128) NOT NULL,
                            org_id VARCHAR(128) NOT NULL DEFAULT 'default',
                            label VARCHAR(255) DEFAULT '',
                            token_hash VARCHAR(64) NOT NULL,
                            prefix VARCHAR(32) DEFAULT '',
                            active BOOLEAN NOT NULL DEFAULT TRUE,
                            revoked_at DOUBLE PRECISION,
                            created_at DOUBLE PRECISION NOT NULL,
                            expires_at DOUBLE PRECISION
                        )
                    """)
                    )
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_api_tokens_token_hash ON api_tokens(token_hash)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_api_tokens_org_user ON api_tokens(org_id, user_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_api_tokens_active ON api_tokens(active)"))
                    conn.commit()
            except Exception as exc:
                logger.warning("Failed to initialize PostgreSQL API token table; falling back to memory/JSONL: %s", exc)
                self.is_postgres = False
                self._pg_engine = None

        if storage_dir is None:
            storage_dir = str(Path.home() / ".loom" / "tokens")
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._records: _GuardedTokenRegistry = _GuardedTokenRegistry()
        if not self.is_postgres:
            self._load()

    def _file(self) -> Path:
        return self._dir / "api_tokens.jsonl"

    def _load(self) -> None:
        path = self._file()
        if not path.exists():
            return
        changed = False
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                record = ApiTokenRecord(**json.loads(line))
                if record.active and record.is_expired():
                    record.active = False
                    record.revoked_at = time.time()
                    changed = True
                self._records[record.id] = record
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        if changed:
            self._persist()

    def _persist(self) -> None:
        if self.is_postgres:
            return
        try:
            with self._file().open("w", encoding="utf-8") as f:
                for record in dict.values(self._records):
                    f.write(json.dumps(record.model_dump(), default=str) + "\n")
        except OSError as exc:
            logger.error("Failed to persist API token registry: %s", exc)

    def issue(self, user_id: str, org_id: str = "default", label: str = "") -> tuple[ApiTokenRecord, str]:
        _require_admin_enabled("issuance")
        token = secrets.token_urlsafe(32)
        created_at = time.time()
        ttl = _ttl_seconds()
        record = ApiTokenRecord(
            user_id=user_id,
            org_id=org_id,
            label=label,
            token_hash=hash_token(token),
            prefix=token[:8],
            created_at=created_at,
            expires_at=(created_at + ttl) if ttl else None,
        )
        if self.is_postgres and self._pg_engine:
            from sqlalchemy import text

            with self._pg_engine.connect() as conn:
                conn.execute(
                    text("""
                    INSERT INTO api_tokens (id, user_id, org_id, label, token_hash, prefix, active, created_at, expires_at)
                    VALUES (:id, :user_id, :org_id, :label, :token_hash, :prefix, :active, :created_at, :expires_at)
                """),
                    {
                        "id": record.id,
                        "user_id": record.user_id,
                        "org_id": record.org_id,
                        "label": record.label,
                        "token_hash": record.token_hash,
                        "prefix": record.prefix,
                        "active": record.active,
                        "created_at": record.created_at,
                        "expires_at": record.expires_at,
                    },
                )
                conn.commit()
        else:
            self._records[record.id] = record
            self._persist()
        return record, token

    def verify(self, token: str) -> Optional[ApiTokenRecord]:
        if in_request_auth_context():
            clear_principal()
        digest = hash_token(token)
        now = time.time()

        if self.is_postgres and self._pg_engine:
            from sqlalchemy import text

            with self._pg_engine.connect() as conn:
                result = conn.execute(
                    text("""
                    SELECT id, user_id, org_id, label, token_hash, prefix, active, revoked_at, created_at, expires_at
                    FROM api_tokens
                    WHERE token_hash = :digest AND active = true
                """),
                    {"digest": digest},
                ).mappings().first()

                if result:
                    record = ApiTokenRecord(**dict(result))
                    if record.is_expired(now):
                        conn.execute(
                            text("UPDATE api_tokens SET active = false, revoked_at = :now WHERE id = :id"),
                            {"now": now, "id": record.id},
                        )
                        conn.commit()
                        return None
                    if in_request_auth_context():
                        set_principal(
                            AuthenticatedPrincipal(
                                user_id=record.user_id,
                                org_id=record.org_id,
                                token_id=record.id,
                                auth_method="api_token",
                            )
                        )
                    return record
            return None

        for record in dict.values(self._records):
            if record.active and not record.is_expired(now) and secrets.compare_digest(record.token_hash, digest):
                if in_request_auth_context():
                    set_principal(
                        AuthenticatedPrincipal(
                            user_id=record.user_id,
                            org_id=record.org_id,
                            token_id=record.id,
                            auth_method="api_token",
                        )
                    )
                return record
        return None

    def revoke(self, token_id: str) -> bool:
        _require_admin_enabled("revocation")
        now = time.time()
        if self.is_postgres and self._pg_engine:
            from sqlalchemy import text

            with self._pg_engine.connect() as conn:
                res = conn.execute(
                    text("UPDATE api_tokens SET active = false, revoked_at = :now WHERE id = :id AND active = true"),
                    {"now": now, "id": token_id},
                )
                conn.commit()
                return bool(res.rowcount and res.rowcount > 0)

        record = self._records.get(token_id)
        if record is None or not record.active:
            return False
        record.active = False
        record.revoked_at = now
        self._persist()
        return True

    def revoke_all_for_user(self, user_id: str) -> int:
        _require_admin_enabled("revocation")
        now = time.time()
        if self.is_postgres and self._pg_engine:
            from sqlalchemy import text

            with self._pg_engine.connect() as conn:
                res = conn.execute(
                    text("UPDATE api_tokens SET active = false, revoked_at = :now WHERE user_id = :user_id AND active = true"),
                    {"now": now, "user_id": user_id},
                )
                conn.commit()
                return int(res.rowcount or 0)

        revoked = 0
        for record in dict.values(self._records):
            if record.user_id == user_id and record.active:
                record.active = False
                record.revoked_at = now
                revoked += 1
        if revoked:
            self._persist()
        return revoked

    def list_active_for_user(self, user_id: str) -> List[ApiTokenRecord]:
        _require_admin_enabled("listing")
        now = time.time()
        if self.is_postgres and self._pg_engine:
            from sqlalchemy import text

            with self._pg_engine.connect() as conn:
                rows = conn.execute(
                    text("""
                    SELECT id, user_id, org_id, label, token_hash, prefix, active, revoked_at, created_at, expires_at
                    FROM api_tokens
                    WHERE user_id = :user_id AND active = true
                """),
                    {"user_id": user_id},
                ).mappings().all()
                return [ApiTokenRecord(**dict(row)) for row in rows if not ApiTokenRecord(**dict(row)).is_expired(now)]

        return [r for r in dict.values(self._records) if r.user_id == user_id and r.active and not r.is_expired()]

    def count(self) -> int:
        now = time.time()
        if self.is_postgres and self._pg_engine:
            from sqlalchemy import text

            with self._pg_engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT id, user_id, org_id, label, token_hash, prefix, active, revoked_at, created_at, expires_at FROM api_tokens WHERE active = true")
                ).mappings().all()
                return sum(1 for row in rows if not ApiTokenRecord(**dict(row)).is_expired(now))

        return sum(1 for r in dict.values(self._records) if r.active and not r.is_expired())


_api_token_store_instance: Optional[ApiTokenStore] = None


def get_api_token_store(storage_dir: Optional[str] = None, database_url: Optional[str] = None) -> ApiTokenStore:
    global _api_token_store_instance
    if _api_token_store_instance is None:
        _api_token_store_instance = ApiTokenStore(storage_dir=storage_dir, database_url=database_url)
    return _api_token_store_instance


def reset_api_token_store() -> None:
    global _api_token_store_instance
    _api_token_store_instance = None


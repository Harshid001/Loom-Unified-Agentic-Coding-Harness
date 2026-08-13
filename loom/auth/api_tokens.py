"""Per-user API token registry with at-rest hashing.

Verification remains available to API authentication. Administrative operations are
explicitly disabled in production unless the privileged control-plane feature flag is
enabled; direct enumeration of the internal registry is guarded as well.
"""

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field

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


class _GuardedTokenRegistry(dict[str, "ApiTokenRecord"]):
    """Guard public enumeration while preserving normal internal dictionary operations."""

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


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ApiTokenStore:
    """Persistent JSONL per-user token registry; hashes tokens at rest."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            storage_dir = str(Path.home() / ".loom" / "tokens")
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._records: _GuardedTokenRegistry = _GuardedTokenRegistry()
        self._load()

    def _file(self) -> Path:
        return self._dir / "api_tokens.jsonl"

    def _load(self) -> None:
        path = self._file()
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                record = ApiTokenRecord(**json.loads(line))
                self._records[record.id] = record
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    def _persist(self) -> None:
        try:
            with self._file().open("w", encoding="utf-8") as f:
                for record in dict.values(self._records):
                    f.write(json.dumps(record.model_dump(), default=str) + "\n")
        except OSError as exc:
            logger.error("Failed to persist API token registry: %s", exc)

    def issue(self, user_id: str, org_id: str = "default", label: str = "") -> tuple[ApiTokenRecord, str]:
        _require_admin_enabled("issuance")
        token = secrets.token_urlsafe(32)
        record = ApiTokenRecord(
            user_id=user_id,
            org_id=org_id,
            label=label,
            token_hash=hash_token(token),
            prefix=token[:8],
        )
        self._records[record.id] = record
        self._persist()
        return record, token

    def verify(self, token: str) -> Optional[ApiTokenRecord]:
        digest = hash_token(token)
        for record in dict.values(self._records):
            if record.active and secrets.compare_digest(record.token_hash, digest):
                return record
        return None

    def revoke(self, token_id: str) -> bool:
        _require_admin_enabled("revocation")
        record = self._records.get(token_id)
        if record is None or not record.active:
            return False
        record.active = False
        record.revoked_at = time.time()
        self._persist()
        return True

    def revoke_all_for_user(self, user_id: str) -> int:
        _require_admin_enabled("revocation")
        revoked = 0
        for record in dict.values(self._records):
            if record.user_id == user_id and record.active:
                record.active = False
                record.revoked_at = time.time()
                revoked += 1
        if revoked:
            self._persist()
        return revoked

    def list_active_for_user(self, user_id: str) -> List[ApiTokenRecord]:
        _require_admin_enabled("listing")
        return [r for r in dict.values(self._records) if r.user_id == user_id and r.active]

    def count(self) -> int:
        return len(self._records)


_api_token_store_instance: Optional[ApiTokenStore] = None


def get_api_token_store(storage_dir: Optional[str] = None) -> ApiTokenStore:
    global _api_token_store_instance
    if _api_token_store_instance is None:
        _api_token_store_instance = ApiTokenStore(storage_dir=storage_dir)
    return _api_token_store_instance


def reset_api_token_store() -> None:
    global _api_token_store_instance
    _api_token_store_instance = None

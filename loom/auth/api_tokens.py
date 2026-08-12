"""Per-user API token registry with at-rest hashing (spec §4.2).

Tokens are issued per user and stored only as SHA-256 hashes; verification
re-hashes the presented credential. Deprovisioning revokes every active
token for a user so the SCIM 5-minute SLA can be enforced end-to-end.
"""

import hashlib
import json
import logging
import secrets
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("loom.auth.api_tokens")


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
    """Persistent (JSONL) per-user API token registry; hashes tokens at rest."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            storage_dir = str(Path.home() / ".loom" / "tokens")
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._records: Dict[str, ApiTokenRecord] = {}
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
                for record in self._records.values():
                    f.write(json.dumps(record.model_dump(), default=str) + "\n")
        except OSError as exc:
            logger.error("Failed to persist API token registry: %s", exc)

    def issue(self, user_id: str, org_id: str = "default", label: str = "") -> tuple[ApiTokenRecord, str]:
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
        for record in self._records.values():
            if record.active and record.token_hash == digest:
                return record
        return None

    def revoke(self, token_id: str) -> bool:
        record = self._records.get(token_id)
        if record is None or not record.active:
            return False
        record.active = False
        record.revoked_at = time.time()
        self._persist()
        return True

    def revoke_all_for_user(self, user_id: str) -> int:
        revoked = 0
        for record in self._records.values():
            if record.user_id == user_id and record.active:
                record.active = False
                record.revoked_at = time.time()
                revoked += 1
        if revoked:
            self._persist()
        return revoked

    def list_active_for_user(self, user_id: str) -> List[ApiTokenRecord]:
        return [r for r in self._records.values() if r.user_id == user_id and r.active]

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

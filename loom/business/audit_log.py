import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loom.business.models import AuditAction, AuditLogEntry

logger = logging.getLogger("loom.business.audit_log")


class AuditLogger:
    """Append-only SOC2-scoped audit log (spec §2, §3.7). Entries are never mutated in place."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            storage_dir = str(Path.home() / ".loom" / "audit")
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._entries: List[AuditLogEntry] = []
        self._load_entries()

    def _audit_file(self) -> Path:
        return self._dir / "audit_log.jsonl"

    def _load_entries(self) -> None:
        audit_file = self._audit_file()
        if not audit_file.exists():
            return
        try:
            for line in audit_file.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    self._entries.append(AuditLogEntry(**json.loads(line)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        except OSError as exc:
            logger.warning("Failed to load existing audit entries: %s", exc)

    def record(
        self,
        org_id: str,
        action: AuditAction,
        actor_id: str = "system",
        target: str = "",
        ip: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditLogEntry]:
        entry = AuditLogEntry(
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            target=target,
            ip=ip,
            metadata=metadata or {},
            timestamp=time.time(),
        )
        self._entries.append(entry)
        try:
            with self._audit_file().open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.model_dump(), default=str) + "\n")
        except Exception as exc:
            logger.error("Failed to persist audit entry for org=%s action=%s: %s", org_id, action.value, exc)
            self._entries.remove(entry)
            return None
        return entry

    def get_entries(self, org_id: Optional[str] = None, action: Optional[AuditAction] = None) -> List[AuditLogEntry]:
        entries = self._entries
        if org_id is not None:
            entries = [e for e in entries if e.org_id == org_id]
        if action is not None:
            entries = [e for e in entries if e.action == action]
        return list(entries)

    def count(self) -> int:
        return len(self._entries)


_audit_logger_instance: Optional[AuditLogger] = None


def get_audit_logger(storage_dir: Optional[str] = None) -> AuditLogger:
    global _audit_logger_instance
    if _audit_logger_instance is None:
        _audit_logger_instance = AuditLogger(storage_dir=storage_dir)
    return _audit_logger_instance


def reset_audit_logger() -> None:
    global _audit_logger_instance
    _audit_logger_instance = None

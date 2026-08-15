import json
import logging
import time
from pathlib import Path
from typing import List, Optional, Set

from loom.business.models import (
    OrgTier,
    OrgUsageSnapshot,
    UsageEvent,
    UsageLedgerEntry,
)

logger = logging.getLogger("loom.business.usage_ledger")


class UsageLedger:
    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            storage_dir = str(Path.home() / ".loom" / "ledger")
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._written_keys: Set[str] = set()
        self._entries: List[UsageLedgerEntry] = []
        self._load_existing_entries()

    def _ledger_file(self) -> Path:
        return self._dir / "usage_ledger.jsonl"

    def _load_existing_entries(self) -> None:
        """Restore both historical entries and deduplication state after restart."""
        ledger_file = self._ledger_file()
        if not ledger_file.exists():
            return
        try:
            for line_number, line in enumerate(ledger_file.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    entry = UsageLedgerEntry(**json.loads(line))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    logger.warning("Skipping invalid ledger entry at line %d: %s", line_number, exc)
                    continue
                if entry.dedup_key in self._written_keys:
                    logger.warning("Skipping duplicate ledger entry at line %d: dedup_key=%s", line_number, entry.dedup_key)
                    continue
                self._written_keys.add(entry.dedup_key)
                self._entries.append(entry)
        except OSError as exc:
            logger.warning("Failed to load existing ledger entries: %s", exc)

    def record(self, event: UsageEvent) -> Optional[UsageLedgerEntry]:
        dedup_key = event.dedup_key
        ledger_file = self._ledger_file()

        if ledger_file.exists():
            try:
                for line in ledger_file.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            d = json.loads(line)
                            k = d.get("dedup_key")
                            if k:
                                self._written_keys.add(k)
                        except Exception:
                            pass
            except Exception:
                pass

        if dedup_key in self._written_keys:
            logger.debug("Skipping duplicate ledger entry for dedup_key=%s", dedup_key)
            return None

        entry = UsageLedgerEntry(
            dedup_key=dedup_key,
            org_id=event.org_id,
            run_id=event.run_id,
            step_id=event.step_id,
            attempt_number=event.attempt_number,
            tokens_in=event.tokens_in,
            tokens_out=event.tokens_out,
            model_id=event.model_id,
            sandbox_tier=event.sandbox_tier,
            wall_clock_ms=event.wall_clock_ms,
            cost_usd=event.cost_usd,
        )

        try:
            with ledger_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.model_dump(), default=str) + "\n")
        except Exception as exc:
            logger.error("Failed to persist ledger entry %s: %s", dedup_key, exc)
            return None

        self._written_keys.add(dedup_key)
        self._entries.append(entry)
        return entry

    def get_entries_for_org(self, org_id: str) -> List[UsageLedgerEntry]:
        return [e for e in self._entries if e.org_id == org_id]

    def get_entries_for_run(self, run_id: str) -> List[UsageLedgerEntry]:
        return [e for e in self._entries if e.run_id == run_id]

    def build_snapshot(self, org_id: str, tier: OrgTier) -> OrgUsageSnapshot:
        org_entries = self.get_entries_for_org(org_id)

        total_tokens = sum(e.tokens_in + e.tokens_out for e in org_entries)
        total_sandbox_ms = sum(e.wall_clock_ms for e in org_entries)
        total_cost = sum(e.cost_usd for e in org_entries)

        runs = set(e.run_id for e in org_entries)
        return OrgUsageSnapshot(
            org_id=org_id,
            month_start=time.strftime("%Y-%m-01"),
            runs_consumed=len(runs),
            tokens_consumed=total_tokens,
            sandbox_ms_consumed=total_sandbox_ms,
            cost_usd_accrued=round(total_cost, 6),
        )

    def get_dedup_key_count(self) -> int:
        return len(self._written_keys)


_ledger_instance: Optional[UsageLedger] = None


def get_usage_ledger(storage_dir: Optional[str] = None) -> UsageLedger:
    global _ledger_instance
    if _ledger_instance is None:
        _ledger_instance = UsageLedger(storage_dir=storage_dir)
    return _ledger_instance


def reset_usage_ledger() -> None:
    global _ledger_instance
    _ledger_instance = None

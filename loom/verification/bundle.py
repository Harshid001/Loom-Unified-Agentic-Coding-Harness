import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger("loom.verification.bundle")


class ChainedBundleEntry(BaseModel):
    index: int
    run_id: str
    timestamp: float
    payload_hash: str
    prev_hash: str
    chain_hash: str
    signature: Optional[str] = None


class EvidenceBundle(BaseModel):
    run_id: str
    timestamp: float = Field(default_factory=time.time)
    verified_patch: str
    verification_success: bool
    test_summary: Dict[str, Any]
    cost_report: Dict[str, Any]
    trace_events: List[Dict[str, Any]] = Field(default_factory=list)
    rollback_snapshot_id: Optional[str] = None
    merge_decision: Dict[str, Any] = Field(default_factory=dict)


class ChainIntegrityError(Exception):
    pass


class TamperDetected(ChainIntegrityError):
    pass


class EvidenceBundler:
    """
    Compiles patch diff, test evidence, trace data, and cost report into a
    hash-chained deliverable bundle. Each exported bundle links to its
    predecessor, forming a tamper-evident audit trail (PRD §3.7).
    """

    CHAIN_FILE_NAME = "evidence_chain.json"
    SEPARATOR = "|"

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or str(Path.home() / ".loom" / "evidence")
        self._chain: List[ChainedBundleEntry] = []
        self._cache: Dict[str, ChainedBundleEntry] = {}

    def _chain_file_path(self) -> Path:
        return Path(self.output_dir) / self.CHAIN_FILE_NAME

    def _payload_hash(self, bundle: EvidenceBundle) -> str:
        payload = json.dumps(
            {
                "run_id": bundle.run_id,
                "timestamp": bundle.timestamp,
                "verified_patch": bundle.verified_patch,
                "verification_success": bundle.verification_success,
                "test_summary": bundle.test_summary,
                "cost_report": bundle.cost_report,
                "rollback_snapshot_id": bundle.rollback_snapshot_id,
                "merge_decision": bundle.merge_decision,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _compute_chain_hash(self, index: int, payload_hash: str, prev_hash: str) -> str:
        seed = self.SEPARATOR.join([str(index), payload_hash, prev_hash])
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def _sign_entry(self, entry: ChainedBundleEntry, hmac_key: Optional[str] = None) -> str:
        message = self.SEPARATOR.join([entry.chain_hash, entry.payload_hash, entry.prev_hash])
        if hmac_key:
            import hmac

            return hmac.new(hmac_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        return ""

    def _load_chain(self) -> List[ChainedBundleEntry]:
        path = self._chain_file_path()
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [ChainedBundleEntry(**e) for e in raw]
        except (json.JSONDecodeError, KeyError, TypeError) as err:
            logger.warning("Evidence chain file corrupted, starting new chain: %s", err)
            return []

    def _save_chain(self, entries: List[ChainedBundleEntry]):
        path = self._chain_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([e.model_dump() for e in entries], indent=2),
            encoding="utf-8",
        )

    def create_bundle(
        self,
        run_id: str,
        patch_diff: str,
        verification_success: bool,
        test_summary: Dict[str, Any],
        cost_report: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        rollback_snapshot_id: Optional[str] = None,
        merge_decision: Optional[Dict[str, Any]] = None,
    ) -> EvidenceBundle:
        return EvidenceBundle(
            run_id=run_id,
            verified_patch=patch_diff,
            verification_success=verification_success,
            test_summary=test_summary,
            cost_report=cost_report,
            trace_events=trace_events,
            rollback_snapshot_id=rollback_snapshot_id,
            merge_decision=merge_decision or {},
        )

    def export_bundle(
        self,
        bundle: EvidenceBundle,
        output_dir: Optional[str] = None,
        hmac_key: Optional[str] = None,
    ) -> ChainedBundleEntry:
        chain = self._load_chain()
        index = len(chain)
        prev_hash = chain[-1].chain_hash if chain else hashlib.sha256(b"GENESIS").hexdigest()

        payload_hash = self._payload_hash(bundle)
        chain_hash = self._compute_chain_hash(index, payload_hash, prev_hash)

        entry = ChainedBundleEntry(
            index=index,
            run_id=bundle.run_id,
            timestamp=bundle.timestamp,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
            chain_hash=chain_hash,
        )

        entry.signature = self._sign_entry(entry, hmac_key) if hmac_key else None

        chain.append(entry)
        self._save_chain(chain)
        self._cache[bundle.run_id] = entry

        out_dir = Path(output_dir or self.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = out_dir / f"evidence_{bundle.run_id}.json"
        bundle_payload = {
            **bundle.model_dump(),
            "chain_entry": entry.model_dump(),
        }
        bundle_path.write_text(json.dumps(bundle_payload, indent=2), encoding="utf-8")

        return entry

    def verify_chain(
        self,
        hmac_key: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], List[int]]:
        chain = self._load_chain()
        if not chain:
            return True, None, []

        tampered_indices: List[int] = []

        for i, entry in enumerate(chain):
            if entry.index != i:
                tampered_indices.append(i)
                continue

            expected_prev = hashlib.sha256(b"GENESIS").hexdigest() if i == 0 else chain[i - 1].chain_hash
            if entry.prev_hash != expected_prev:
                tampered_indices.append(i)
                continue

            recomp = self._compute_chain_hash(i, entry.payload_hash, entry.prev_hash)
            if entry.chain_hash != recomp:
                tampered_indices.append(i)
                continue

            if hmac_key and entry.signature:
                expected_sig = self._sign_entry(entry, hmac_key)
                if entry.signature != expected_sig:
                    tampered_indices.append(i)

        if tampered_indices:
            return False, f"Chain integrity violated at indices: {tampered_indices}", tampered_indices

        return True, None, []

    def verify_bundle_payload(
        self,
        bundle: EvidenceBundle,
        expected_chain_hash: Optional[str] = None,
    ) -> bool:
        actual_payload_hash = self._payload_hash(bundle)
        if expected_chain_hash is None:
            chain = self._load_chain()
            for entry in chain:
                if entry.run_id == bundle.run_id:
                    expected_chain_hash = entry.payload_hash
                    break
        if expected_chain_hash is None:
            return False
        return actual_payload_hash == expected_chain_hash

    def chain_length(self) -> int:
        return len(self._load_chain())

    def get_entry(self, run_id: str) -> Optional[ChainedBundleEntry]:
        if run_id in self._cache:
            return self._cache[run_id]
        chain = self._load_chain()
        for entry in chain:
            if entry.run_id == run_id:
                self._cache[run_id] = entry
                return entry
        return None

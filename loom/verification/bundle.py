import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvidenceBundle(BaseModel):
    run_id: str
    timestamp: float = Field(default_factory=time.time)
    verified_patch: str
    verification_success: bool
    test_summary: Dict[str, Any]
    cost_report: Dict[str, Any]
    trace_events: List[Dict[str, Any]] = Field(default_factory=list)
    rollback_snapshot_id: Optional[str] = None

class EvidenceBundler:
    """Compiles patch diff, test evidence, trace data, and cost report into a single deliverable bundle."""

    def create_bundle(
        self,
        run_id: str,
        patch_diff: str,
        verification_success: bool,
        test_summary: Dict[str, Any],
        cost_report: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        rollback_snapshot_id: Optional[str] = None
    ) -> EvidenceBundle:
        return EvidenceBundle(
            run_id=run_id,
            verified_patch=patch_diff,
            verification_success=verification_success,
            test_summary=test_summary,
            cost_report=cost_report,
            trace_events=trace_events,
            rollback_snapshot_id=rollback_snapshot_id
        )

    def export_bundle(self, bundle: EvidenceBundle, output_dir: str) -> str:
        out_path = Path(output_dir) / f"evidence_{bundle.run_id}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(bundle.model_dump(), indent=2), encoding="utf-8")
        return str(out_path)

"""Post-merge monitoring and auto-rollback (spec §3.6).

Implements the auto-rollback rule: if CI reports a failure within the
post-merge monitor window, the merge is rolled back by generating the
reverse of the merged patch. The rule itself is a pure function so it can
be unit-tested deterministically and reused by the API layer.
"""

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loom.api.webhooks import WebhookEngine, WebhookEventType
from loom.business.audit_log import AuditLogger
from loom.business.models import AuditAction

logger = logging.getLogger("loom.business.post_merge")

DEFAULT_MONITOR_TIMEOUT_SECONDS = 3600

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class RevertPatchError(ValueError):
    pass


def auto_rollback_triggered(
    merge_time: float,
    ci_failure_detected: bool,
    monitor_timeout_seconds: int = DEFAULT_MONITOR_TIMEOUT_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """Pure rule: a CI failure inside the monitor window after merge triggers rollback."""
    if not ci_failure_detected:
        return False
    elapsed = (now if now is not None else time.time()) - merge_time
    return elapsed <= monitor_timeout_seconds


def generate_revert_patch(patch_diff: str) -> str:
    """Reverse a unified diff so it can be applied to undo the original patch (spec §3.6).

    Swaps file headers (---/+++), inverts hunk ranges, and flips addition/removal
    markers. Returns an empty string if the input contains no actual changes.
    """
    if not patch_diff or not patch_diff.strip():
        return ""

    out: List[str] = []
    changed = False
    lines = patch_diff.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("--- "):
            new_file_line = lines[i + 1] if i + 1 < len(lines) and lines[i + 1].startswith("+++ ") else None
            if new_file_line is None:
                raise RevertPatchError("Malformed diff: --- header without following +++ header")
            out.append("--- " + new_file_line[4:])
            out.append("+++ " + line[4:])
            i += 2
            continue

        hunk = _HUNK_RE.match(line.rstrip("\r\n"))
        if hunk:
            old_start, old_len, new_start, new_len = hunk.groups()
            old_len = old_len or "1"
            new_len = new_len or "1"
            out.append(f"@@ -{new_start},{new_len} +{old_start},{old_len} @@\n")
            i += 1
            while i < len(lines):
                content = lines[i]
                if _HUNK_RE.match(content.rstrip("\r\n")) or content.startswith("--- ") or content.startswith("+++ "):
                    break
                stripped = content.rstrip("\r\n")
                if stripped.startswith("+"):
                    out.append("-" + content[1:])
                    changed = True
                elif stripped.startswith("-"):
                    out.append("+" + content[1:])
                    changed = True
                else:
                    out.append(content)
                i += 1
            continue

        out.append(line)
        i += 1

    if not changed:
        return ""
    return "".join(out)


class PostMergeMonitor:
    """Watches merged runs for post-merge CI failures and triggers auto-rollback (spec §3.6).

    `evaluate` is side-effect free; `trigger_rollback` records the revert
    (audit entry, revert log, webhook dispatch) once a rollback is needed.
    """

    def __init__(
        self,
        webhook_engine: Optional[WebhookEngine] = None,
        audit_logger: Optional[AuditLogger] = None,
        revert_log_dir: Optional[str] = None,
    ):
        self.webhook_engine = webhook_engine
        self.audit_logger = audit_logger
        if revert_log_dir is None:
            revert_log_dir = str(Path.home() / ".loom" / "reverts")
        self._revert_dir = Path(revert_log_dir)
        self._revert_dir.mkdir(parents=True, exist_ok=True)

    def _revert_log_file(self) -> Path:
        return self._revert_dir / "revert_log.jsonl"

    def evaluate(
        self,
        run_id: str,
        merge_time: float,
        ci_failure_detected: bool,
        monitor_timeout_seconds: int = DEFAULT_MONITOR_TIMEOUT_SECONDS,
        patch_diff: str = "",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        evaluated_at = now if now is not None else time.time()
        rollback_needed = auto_rollback_triggered(
            merge_time,
            ci_failure_detected,
            monitor_timeout_seconds,
            now=evaluated_at,
        )
        revert_patch = generate_revert_patch(patch_diff) if rollback_needed else ""
        return {
            "run_id": run_id,
            "rollback_needed": rollback_needed,
            "ci_failure_detected": ci_failure_detected,
            "monitor_timeout_seconds": monitor_timeout_seconds,
            "merge_time": merge_time,
            "elapsed_seconds": round(evaluated_at - merge_time, 3),
            "revert_patch": revert_patch,
            "evaluated_at": evaluated_at,
        }

    def record_rollback(
        self,
        org_id: str,
        report: Dict[str, Any],
        actor_id: str = "system",
    ) -> Dict[str, Any]:
        """Persist rollback evidence (audit entry + revert log) and dispatch the rolled-back webhook."""
        revert_record = {
            "id": f"revert_{uuid.uuid4().hex[:16]}",
            "org_id": org_id,
            "run_id": report["run_id"],
            "revert_patch": report.get("revert_patch", ""),
            "elapsed_seconds": report.get("elapsed_seconds"),
            "recorded_at": report.get("evaluated_at", time.time()),
        }

        if self.audit_logger is not None:
            self.audit_logger.record(
                org_id=org_id,
                action=AuditAction.RUN_ROLLED_BACK,
                actor_id=actor_id,
                target=report["run_id"],
                metadata={
                    "reason": "post_merge_ci_failure",
                    "elapsed_seconds": report.get("elapsed_seconds"),
                    "revert_id": revert_record["id"],
                },
            )

        try:
            with self._revert_log_file().open("a", encoding="utf-8") as f:
                f.write(json.dumps(revert_record, default=str) + "\n")
        except OSError as exc:
            logger.error("Failed to persist revert record for run %s: %s", report["run_id"], exc)

        if self.webhook_engine is not None:
            try:
                self.webhook_engine.dispatch_sync(
                    WebhookEventType.RUN_ROLLED_BACK,
                    report["run_id"],
                    {"reason": "post_merge_ci_failure", "revert_record": revert_record},
                    org_id,
                )
            except Exception as exc:
                logger.warning("Failed to dispatch run.rolled_back webhook for %s: %s", report["run_id"], exc)

        return revert_record

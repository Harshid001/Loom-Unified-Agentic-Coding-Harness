import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loom.api.webhooks import WebhookEngine, WebhookEventType
from loom.business.audit_log import AuditLogger
from loom.business.entitlements import EntitlementService
from loom.business.models import AuditAction, OrgUsageSnapshot
from loom.business.usage_ledger import UsageLedger

logger = logging.getLogger("loom.business.rollup")

SOFT_WARN_PCT = 80.0
HARD_STOP_PCT = 100.0


@dataclass
class RollupOutcome:
    org_id: str
    month_start: str
    quota_pct: float
    allowed: bool
    reason: str = ""
    actions: List[str] = field(default_factory=list)


class UsageRollupJob:
    """Hourly metering rollup (spec §1.3): aggregate UsageLedger → snapshot per org,
    compare against quota, emit webhooks + audit entries when thresholds are crossed.

    Idempotent on replay: events are emitted only when an org's quota percentage
    crosses a threshold band since the previous rollup run.
    """

    STATE_FILE_NAME = "rollup_state.json"

    def __init__(
        self,
        entitlements: EntitlementService,
        ledger: UsageLedger,
        webhooks: Optional[WebhookEngine] = None,
        audit_logger: Optional[AuditLogger] = None,
        storage_dir: Optional[str] = None,
    ):
        self._entitlements = entitlements
        self._ledger = ledger
        self._webhooks = webhooks
        self._audit = audit_logger or AuditLogger()
        if storage_dir is None:
            storage_dir = str(Path.home() / ".loom" / "rollup")
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _state_file(self) -> Path:
        return self._dir / self.STATE_FILE_NAME

    def _load_state(self) -> Dict[str, Dict[str, Any]]:
        path = self._state_file()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            state: Dict[str, Dict[str, Any]] = {}
            for org_id, values in raw.items():
                state[org_id] = dict(values)
            return state
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            logger.warning("Corrupt rollup state file at %s, starting fresh", path)
            return {}

    def _save_state(self, state: Dict[str, Dict[str, Any]]) -> None:
        self._state_file().write_text(json.dumps(state, indent=2), encoding="utf-8")

    async def run_once(self) -> List[RollupOutcome]:
        state = self._load_state()
        outcomes: List[RollupOutcome] = []

        for org_id in self._entitlements.list_org_ids():
            org = self._entitlements.get_org(org_id)
            if org is None:
                continue
            snapshot = self._ledger.build_snapshot(org_id, org.tier)
            if snapshot.runs_consumed == 0 and snapshot.tokens_consumed == 0 and snapshot.sandbox_ms_consumed == 0:
                continue

            quota_pct = self._entitlements.quota_usage_percent(org_id, snapshot)
            allowed, reason = self._entitlements.evaluate_quota(org_id, snapshot)

            prev_pct = float(state.get(org_id, {}).get("quota_pct", 0.0))
            outcome = RollupOutcome(
                org_id=org_id,
                month_start=snapshot.month_start,
                quota_pct=round(quota_pct, 2),
                allowed=allowed,
                reason=reason,
            )

            await self._emit_crossings(org_id, prev_pct, quota_pct, snapshot, outcome)

            state[org_id] = {"quota_pct": round(quota_pct, 2), "month_start": snapshot.month_start}
            outcomes.append(outcome)

        self._save_state(state)
        return outcomes

    async def _emit_crossings(
        self,
        org_id: str,
        prev_pct: float,
        quota_pct: float,
        snapshot: OrgUsageSnapshot,
        outcome: RollupOutcome,
    ) -> None:
        snapshot_data = {
            "month_start": snapshot.month_start,
            "runs_consumed": snapshot.runs_consumed,
            "tokens_consumed": snapshot.tokens_consumed,
            "sandbox_ms_consumed": snapshot.sandbox_ms_consumed,
            "cost_usd_accrued": snapshot.cost_usd_accrued,
            "quota_pct": round(quota_pct, 2),
        }

        if prev_pct < SOFT_WARN_PCT <= quota_pct:
            outcome.actions.append("soft_warn")
            self._audit.record(
                org_id=org_id,
                action=AuditAction.QUOTA_SOFT_WARN,
                actor_id="usage_rollup_job",
                target=f"org:{org_id}",
                metadata=snapshot_data,
            )
            if self._webhooks is not None:
                await self._webhooks.dispatch(
                    WebhookEventType.USAGE_QUOTA_WARNING,
                    run_id="",
                    data=snapshot_data,
                    org_id=org_id,
                )

        if prev_pct < HARD_STOP_PCT <= quota_pct and quota_pct < 999.0:
            outcome.actions.append("quota_exceeded")
            self._audit.record(
                org_id=org_id,
                action=AuditAction.QUOTA_EXCEEDED,
                actor_id="usage_rollup_job",
                target=f"org:{org_id}",
                metadata={**snapshot_data, "evaluation": outcome.reason},
            )
            if self._webhooks is not None:
                await self._webhooks.dispatch(
                    WebhookEventType.USAGE_QUOTA_EXCEEDED,
                    run_id="",
                    data={**snapshot_data, "evaluation": outcome.reason},
                    org_id=org_id,
                )

    def run_sync(self) -> List[RollupOutcome]:
        import asyncio

        return asyncio.run(self.run_once())

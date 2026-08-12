import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("loom.integrations.slack")


class SlackNotificationLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    SUCCESS = "success"


class SlackNotificationTemplate(str, Enum):
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    SECURITY_HOLD = "security_hold"
    QUOTA_WARNING = "quota_warning"
    QUOTA_EXCEEDED = "quota_exceeded"
    MERGED = "merged"
    ROLLED_BACK = "rolled_back"
    EVIDENCE_EXPORTED = "evidence_exported"
    CUSTOM = "custom"


LEVEL_COLORS: Dict[SlackNotificationLevel, str] = {
    SlackNotificationLevel.INFO: "#3B82F6",
    SlackNotificationLevel.WARNING: "#F59E0B",
    SlackNotificationLevel.ERROR: "#EF4444",
    SlackNotificationLevel.CRITICAL: "#991B1B",
    SlackNotificationLevel.SUCCESS: "#10B981",
}

TEMPLATE_COLORS: Dict[SlackNotificationTemplate, str] = {
    SlackNotificationTemplate.RUN_COMPLETED: "#10B981",
    SlackNotificationTemplate.RUN_FAILED: "#EF4444",
    SlackNotificationTemplate.SECURITY_HOLD: "#F59E0B",
    SlackNotificationTemplate.QUOTA_WARNING: "#F59E0B",
    SlackNotificationTemplate.QUOTA_EXCEEDED: "#EF4444",
    SlackNotificationTemplate.MERGED: "#3B82F6",
    SlackNotificationTemplate.ROLLED_BACK: "#991B1B",
    SlackNotificationTemplate.EVIDENCE_EXPORTED: "#8B5CF6",
    SlackNotificationTemplate.CUSTOM: "#6B7280",
}


@dataclass
class SlackNotification:
    title: str
    body: str
    level: SlackNotificationLevel = SlackNotificationLevel.INFO
    template: SlackNotificationTemplate = SlackNotificationTemplate.CUSTOM
    fields: List[Dict[str, str]] = field(default_factory=list)
    footer: str = ""
    run_id: str = ""
    timestamp: float = field(default_factory=time.time)


class SlackNotifier:
    def __init__(
        self,
        webhook_url: str,
        bot_name: str = "Loom CI",
        bot_icon: str = ":robot:",
        channel_override: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.webhook_url = webhook_url
        self.bot_name = bot_name
        self.bot_icon = bot_icon
        self.channel_override = channel_override
        self._http = http_client
        self._delivery_log: List[Dict[str, Any]] = []

    async def _ensure_client(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(10.0))

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    def _build_attachment(self, notification: SlackNotification) -> Dict[str, Any]:
        color = LEVEL_COLORS.get(notification.level, TEMPLATE_COLORS.get(notification.template, "#6B7280"))

        attachment: Dict[str, Any] = {
            "color": color,
            "title": notification.title,
            "text": notification.body,
            "fields": [],
            "footer": notification.footer or "Loom Agentic Harness",
            "ts": int(notification.timestamp),
        }

        if notification.fields:
            attachment["fields"] = [
                {"title": f.get("title", ""), "value": f.get("value", ""), "short": f.get("short", True)}
                for f in notification.fields
            ]

        return attachment

    def _build_payload(self, notification: SlackNotification) -> Dict[str, Any]:
        attachment = self._build_attachment(notification)
        payload: Dict[str, Any] = {
            "username": self.bot_name,
            "icon_emoji": self.bot_icon,
            "attachments": [attachment],
        }
        if self.channel_override:
            payload["channel"] = self.channel_override
        return payload

    async def send(self, notification: SlackNotification) -> bool:
        await self._ensure_client()
        assert self._http is not None

        payload = self._build_payload(notification)

        delivery_record = {
            "title": notification.title,
            "level": notification.level.value,
            "run_id": notification.run_id,
            "timestamp": notification.timestamp,
            "success": False,
            "error": None,
        }

        try:
            response = await self._http.post(
                self.webhook_url,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            delivery_record["status_code"] = response.status_code
            if 200 <= response.status_code < 300:
                delivery_record["success"] = True
                return True
            delivery_record["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.warning("Slack delivery failed: %s", delivery_record["error"])
            return False
        except httpx.TimeoutException:
            delivery_record["error"] = "Request timed out"
            logger.warning("Slack delivery timed out for %s", notification.title)
            return False
        except Exception as exc:
            delivery_record["error"] = str(exc)[:200]
            logger.error("Slack delivery error: %s", exc)
            return False
        finally:
            self._delivery_log.append(delivery_record)
            if len(self._delivery_log) > 1000:
                self._delivery_log = self._delivery_log[-500:]

    def send_sync(self, notification: SlackNotification) -> bool:
        import asyncio

        return asyncio.run(self.send(notification))

    def build_run_completed_notification(
        self,
        run_id: str,
        issue_title: str,
        repo_name: str,
        confidence_score: float,
        cost_usd: float,
        verification_passed: bool,
        model_used: str = "unknown",
    ) -> SlackNotification:
        status = "passed" if verification_passed else "failed"
        emoji = ":white_check_mark:" if verification_passed else ":x:"
        return SlackNotification(
            title=f"{emoji} Run {run_id} — Verification {status}",
            body=f"Issue: *{issue_title}* on `{repo_name}`",
            level=SlackNotificationLevel.SUCCESS if verification_passed else SlackNotificationLevel.ERROR,
            template=SlackNotificationTemplate.RUN_COMPLETED,
            fields=[
                {"title": "Confidence", "value": f"{confidence_score:.1%}"},
                {"title": "Model", "value": model_used},
                {"title": "Cost", "value": f"${cost_usd:.4f}"},
            ],
            footer=f"Loom CI Bot | {repo_name}",
            run_id=run_id,
        )

    def build_security_hold_notification(
        self,
        run_id: str,
        repo_name: str,
        blocked_paths: List[str],
        reason: str,
    ) -> SlackNotification:
        paths_text = "\n".join(f"• `{p}`" for p in blocked_paths[:10])
        if len(blocked_paths) > 10:
            paths_text += f"\n• ...and {len(blocked_paths) - 10} more"
        return SlackNotification(
            title=f":warning: Security Hold — Run {run_id}",
            body=f"Patch blocked on `{repo_name}`:\n{paths_text}\n\n*Reason:* {reason}",
            level=SlackNotificationLevel.WARNING,
            template=SlackNotificationTemplate.SECURITY_HOLD,
            fields=[
                {"title": "Blocked Paths", "value": str(len(blocked_paths))},
                {"title": "Run ID", "value": run_id},
            ],
            footer=f"Loom CI Bot | {repo_name}",
            run_id=run_id,
        )

    def build_quota_warning_notification(
        self,
        org_id: str,
        quota_pct: float,
        runs_consumed: int,
        runs_limit: int,
    ) -> SlackNotification:
        return SlackNotification(
            title=f":chart_with_downwards_trend: Quota Warning — {quota_pct:.0f}% Used",
            body=f"Organization `{org_id}` has consumed {runs_consumed}/{runs_limit} runs this month.",
            level=SlackNotificationLevel.WARNING,
            template=SlackNotificationTemplate.QUOTA_WARNING,
            fields=[
                {"title": "Consumed", "value": str(runs_consumed)},
                {"title": "Limit", "value": str(runs_limit)},
                {"title": "Usage", "value": f"{quota_pct:.1f}%"},
            ],
            footer="Loom CI Bot | Billing Alert",
        )

    def build_quota_exceeded_notification(
        self,
        org_id: str,
        quota_pct: float,
        runs_consumed: int,
        runs_limit: int,
        hard_stop_triggered: bool,
    ) -> SlackNotification:
        level = SlackNotificationLevel.CRITICAL if hard_stop_triggered else SlackNotificationLevel.ERROR
        return SlackNotification(
            title=f":no_entry: Quota {'Hard Stop' if hard_stop_triggered else 'Exceeded'} — {quota_pct:.0f}%",
            body=f"Organization `{org_id}` exceeded quota ({runs_consumed}/{runs_limit} runs). "
            + ("New runs are blocked." if hard_stop_triggered else "Overage billing active."),
            level=level,
            template=SlackNotificationTemplate.QUOTA_EXCEEDED,
            fields=[
                {"title": "Consumed", "value": str(runs_consumed)},
                {"title": "Limit", "value": str(runs_limit)},
                {"title": "Status", "value": "BLOCKED" if hard_stop_triggered else "OVERAGE"},
            ],
            footer="Loom CI Bot | Billing Alert",
        )

    def build_merged_notification(
        self,
        run_id: str,
        repo_name: str,
        issue_title: str,
        confidence_score: float,
    ) -> SlackNotification:
        return SlackNotification(
            title=f":rocket: Auto-Merged — Run {run_id}",
            body=f"Fix for *{issue_title}* on `{repo_name}` merged at {confidence_score:.1%} confidence.",
            level=SlackNotificationLevel.SUCCESS,
            template=SlackNotificationTemplate.MERGED,
            fields=[
                {"title": "Confidence", "value": f"{confidence_score:.1%}"},
                {"title": "Run ID", "value": run_id},
            ],
            footer=f"Loom CI Bot | {repo_name}",
            run_id=run_id,
        )

    def build_rolled_back_notification(
        self,
        run_id: str,
        repo_name: str,
        issue_title: str,
        reason: str,
    ) -> SlackNotification:
        return SlackNotification(
            title=f":rewind: Auto-Rollback — Run {run_id}",
            body=f"Fix for *{issue_title}* on `{repo_name}` was rolled back.\n*Reason:* {reason}",
            level=SlackNotificationLevel.ERROR,
            template=SlackNotificationTemplate.ROLLED_BACK,
            fields=[
                {"title": "Reason", "value": reason},
                {"title": "Run ID", "value": run_id},
            ],
            footer=f"Loom CI Bot | {repo_name}",
            run_id=run_id,
        )

    def build_failed_notification(
        self,
        run_id: str,
        repo_name: str,
        issue_title: str,
        error_message: str,
        step_failed: str = "",
    ) -> SlackNotification:
        return SlackNotification(
            title=f":x: Run Failed — {run_id}",
            body=f"Fix for *{issue_title}* on `{repo_name}` failed"
            + (f" at step `{step_failed}`." if step_failed else ".")
            + f"\n```{error_message[:500]}```",
            level=SlackNotificationLevel.ERROR,
            template=SlackNotificationTemplate.RUN_FAILED,
            fields=[
                {"title": "Failed Step", "value": step_failed or "unknown"},
                {"title": "Run ID", "value": run_id},
            ],
            footer=f"Loom CI Bot | {repo_name}",
            run_id=run_id,
        )

    @property
    def delivery_log(self) -> List[Dict[str, Any]]:
        return list(self._delivery_log)

    def clear_delivery_log(self) -> None:
        self._delivery_log.clear()

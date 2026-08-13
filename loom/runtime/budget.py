"""Hard execution budgets for autonomous production runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class RunBudget:
    """Limits applied to one autonomous run.

    Zero/None means that the corresponding resource is not limited.
    """

    max_cost_usd: Optional[float] = None
    max_duration_seconds: Optional[float] = None
    max_attempts: Optional[int] = None
    max_agent_steps: Optional[int] = None
    max_tokens: Optional[int] = None

    @classmethod
    def from_env(cls) -> "RunBudget":
        import os

        def _float(name: str) -> Optional[float]:
            value = os.getenv(name)
            return float(value) if value else None

        def _int(name: str) -> Optional[int]:
            value = os.getenv(name)
            return int(value) if value else None

        return cls(
            max_cost_usd=_float("LOOM_MAX_RUN_COST_USD"),
            max_duration_seconds=_float("LOOM_MAX_RUN_DURATION_SECONDS"),
            max_attempts=_int("LOOM_MAX_RUN_ATTEMPTS"),
            max_agent_steps=_int("LOOM_MAX_AGENT_STEPS"),
            max_tokens=_int("LOOM_MAX_RUN_TOKENS"),
        )


class BudgetExceeded(RuntimeError):
    """Raised when an autonomous run exceeds a configured hard limit."""


def cost_from_summary(summary: Any) -> float:
    if not isinstance(summary, dict):
        return 0.0
    return float(summary.get("total_cost_usd", summary.get("cost_usd", 0.0)) or 0.0)


def tokens_from_summary(summary: Any) -> int:
    if not isinstance(summary, dict):
        return 0
    return int(summary.get("total_tokens", summary.get("tokens", 0)) or 0)

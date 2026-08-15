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

    def check_limits(
        self,
        cost_usd: float = 0.0,
        elapsed_seconds: float = 0.0,
        tokens_used: int = 0,
        agent_steps: int = 0,
    ) -> None:
        if self.max_cost_usd is not None and cost_usd > self.max_cost_usd:
            raise BudgetExceeded(f"Hard cost budget exceeded: ${cost_usd:.2f} > ${self.max_cost_usd:.2f}")
        if self.max_duration_seconds is not None and elapsed_seconds > self.max_duration_seconds:
            raise BudgetExceeded(f"Hard duration budget exceeded: {elapsed_seconds:.1f}s > {self.max_duration_seconds:.1f}s")
        if self.max_tokens is not None and tokens_used > self.max_tokens:
            raise BudgetExceeded(f"Hard token budget exceeded: {tokens_used} > {self.max_tokens}")
        if self.max_agent_steps is not None and agent_steps > self.max_agent_steps:
            raise BudgetExceeded(f"Hard agent steps budget exceeded: {agent_steps} > {self.max_agent_steps}")


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

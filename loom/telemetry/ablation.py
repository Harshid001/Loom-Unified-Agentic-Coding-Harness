from typing import Any, Dict, List

from pydantic import BaseModel


class AblationConfig(BaseModel):
    memory_enabled: bool = True
    context_ranking_enabled: bool = True
    multi_agent_enabled: bool = True
    verification_enabled: bool = True

class AblationResult(BaseModel):
    config_name: str
    config: AblationConfig
    success: bool
    total_cost_usd: float
    total_tokens: int
    duration_seconds: float
    verification_passed: bool

class AblationHarness:
    """Runs controlled same-model, same-budget comparison runs to prove harness architectural delta."""

    def get_ablation_matrix(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "baseline_naive",
                "config": AblationConfig(
                    memory_enabled=False,
                    context_ranking_enabled=False,
                    multi_agent_enabled=False,
                    verification_enabled=False
                ).model_dump()
            },
            {
                "name": "loom_no_memory",
                "config": AblationConfig(
                    memory_enabled=False,
                    context_ranking_enabled=True,
                    multi_agent_enabled=True,
                    verification_enabled=True
                ).model_dump()
            },
            {
                "name": "loom_no_context_ranking",
                "config": AblationConfig(
                    memory_enabled=True,
                    context_ranking_enabled=False,
                    multi_agent_enabled=True,
                    verification_enabled=True
                ).model_dump()
            },
            {
                "name": "loom_full",
                "config": AblationConfig(
                    memory_enabled=True,
                    context_ranking_enabled=True,
                    multi_agent_enabled=True,
                    verification_enabled=True
                ).model_dump()
            }
        ]

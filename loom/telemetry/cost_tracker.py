import hashlib
from typing import Any, Dict

from pydantic import BaseModel

from loom.business.models import UsageEvent
from loom.business.usage_ledger import get_usage_ledger


class NodeCost(BaseModel):
    node_name: str
    model_id: str = "unknown"
    sandbox_tier: str = "A"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


class CostTracker:
    """Tracks token and cost usage broken down per task graph node and model.

    Emits UsageEvent records to the append-only UsageLedger on each add_usage call
    with an idempotency guard (SHA256 of run_id + step_id + attempt_number + input_context_hash)
    to prevent double-counting from retries.
    """

    def __init__(self, run_id: str, org_id: str = "default_org"):
        self.run_id = run_id
        self.org_id = org_id
        self.node_costs: Dict[str, NodeCost] = {}
        self._node_attempts: Dict[str, int] = {}

    def add_usage(self, node_name: str, prompt_tokens: int, completion_tokens: int, cost_usd: float,
                  model_id: str = "unknown", sandbox_tier: str = "A"):
        if node_name not in self.node_costs:
            self.node_costs[node_name] = NodeCost(node_name=node_name, model_id=model_id, sandbox_tier=sandbox_tier)
            self._node_attempts[node_name] = 0

        self._node_attempts[node_name] += 1

        nc = self.node_costs[node_name]
        nc.prompt_tokens += prompt_tokens
        nc.completion_tokens += completion_tokens
        nc.total_tokens += prompt_tokens + completion_tokens
        nc.cost_usd += cost_usd
        nc.model_id = model_id
        nc.sandbox_tier = sandbox_tier

    def add_usage_with_context(
        self,
        node_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        model_id: str = "unknown",
        sandbox_tier: str = "A",
        wall_clock_ms: int = 0,
        input_context: str = "",
    ):
        self.add_usage(node_name, prompt_tokens, completion_tokens, cost_usd)
        input_hash = hashlib.sha256(input_context.encode()).hexdigest() if input_context else ""
        event = UsageEvent(
            run_id=self.run_id,
            org_id=self.org_id,
            step_id=node_name,
            attempt_number=self._node_attempts.get(node_name, 1),
            tokens_in=prompt_tokens,
            tokens_out=completion_tokens,
            model_id=model_id,
            sandbox_tier=sandbox_tier,
            wall_clock_ms=wall_clock_ms,
            cost_usd=cost_usd,
            input_context_hash=input_hash,
        )
        ledger = get_usage_ledger()
        ledger.record(event)

    def get_summary(self) -> Dict[str, Any]:
        total_prompt = sum(c.prompt_tokens for c in self.node_costs.values())
        total_completion = sum(c.completion_tokens for c in self.node_costs.values())
        total_cost = sum(c.cost_usd for c in self.node_costs.values())

        return {
            "run_id": self.run_id,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "total_cost_usd": round(total_cost, 6),
            "by_node": {k: v.model_dump() for k, v in self.node_costs.items()},
        }

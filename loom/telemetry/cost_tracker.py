from typing import Any, Dict

from pydantic import BaseModel


class NodeCost(BaseModel):
    node_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

class CostTracker:
    """Tracks token and cost usage broken down per task graph node and model."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.node_costs: Dict[str, NodeCost] = {}

    def add_usage(self, node_name: str, prompt_tokens: int, completion_tokens: int, cost_usd: float):
        if node_name not in self.node_costs:
            self.node_costs[node_name] = NodeCost(node_name=node_name)

        nc = self.node_costs[node_name]
        nc.prompt_tokens += prompt_tokens
        nc.completion_tokens += completion_tokens
        nc.total_tokens += (prompt_tokens + completion_tokens)
        nc.cost_usd += cost_usd

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
            "by_node": {k: v.model_dump() for k, v in self.node_costs.items()}
        }

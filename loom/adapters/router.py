from typing import Dict, Optional

from loom.adapters.base import BaseModelAdapter
from loom.adapters.litellm_adapter import LiteLLMAdapter

MODEL_PRICING = {
    "claude-3-5-sonnet-20241022": {"input": 3.00 / 1e6, "output": 15.00 / 1e6},
    "gpt-4o": {"input": 2.50 / 1e6, "output": 10.00 / 1e6},
    "gpt-4o-mini": {"input": 0.15 / 1e6, "output": 0.60 / 1e6},
    "gemini-1.5-pro": {"input": 1.25 / 1e6, "output": 5.00 / 1e6},
    "deepseek-v3": {"input": 0.27 / 1e6, "output": 1.10 / 1e6},
    "claude-3-opus-20240229": {"input": 15.00 / 1e6, "output": 75.00 / 1e6},
    "ollama/codellama": {"input": 0.0, "output": 0.0},
    "mock": {"input": 0.001 / 1e6, "output": 0.002 / 1e6},
}


class ModelRouter:
    """Routes task nodes to models based on task complexity and spend policies."""

    def __init__(self, default_model: str = "claude-3-5-sonnet-20241022", mock_mode: bool = False):
        self.default_model = default_model
        self.mock_mode = mock_mode
        self.adapter = LiteLLMAdapter(mock_mode=mock_mode)

        # Route high-complexity reasoning vs low-complexity formatting
        self.node_model_map: Dict[str, str] = {
            "onboarding": default_model,
            "reproduction": default_model,
            "planning": default_model,
            "patcher": default_model,
            "verifier": default_model,
            "reviewer": default_model,
        }

    def set_model(self, new_model: str) -> None:
        self.default_model = new_model
        for key in self.node_model_map:
            self.node_model_map[key] = new_model

    def get_adapter(self, task_node_name: Optional[str] = None) -> BaseModelAdapter:
        return self.adapter

    def resolve_model(self, task_node_name: str) -> str:
        if self.mock_mode:
            return "mock"
        return self.node_model_map.get(task_node_name, self.default_model)

    def estimate_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model_name, MODEL_PRICING["claude-3-5-sonnet-20241022"])
        return (prompt_tokens * pricing["input"]) + (completion_tokens * pricing["output"])


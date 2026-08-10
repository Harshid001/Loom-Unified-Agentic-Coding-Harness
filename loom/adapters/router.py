from typing import Dict, Optional

from loom.adapters.base import BaseModelAdapter
from loom.adapters.litellm_adapter import LiteLLMAdapter


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

    def get_adapter(self, task_node_name: Optional[str] = None) -> BaseModelAdapter:
        return self.adapter

    def resolve_model(self, task_node_name: str) -> str:
        if self.mock_mode:
            return "mock"
        return self.node_model_map.get(task_node_name, self.default_model)

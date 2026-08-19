from abc import ABC, abstractmethod
from typing import Any, Dict

from loom.adapters.base import BaseModelAdapter
from loom.orchestrator.state import OrchestratorState


class BaseAgent(ABC):
    def __init__(self, name: str, adapter: BaseModelAdapter, model_name: str = "claude-3-7-sonnet-20250219"):
        self.name = name
        self.adapter = adapter
        self.model_name = model_name

    @abstractmethod
    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        """Execute agent task step on orchestrator state."""
        pass

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]


class ModelRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    tools: Optional[List[Dict[str, Any]]] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = 4096
    system_prompt: Optional[str] = None


class ModelResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    model: str
    finish_reason: str = "stop"
    raw_response: Optional[Dict[str, Any]] = None


class BaseModelAdapter(ABC):
    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Execute model request and return standardized response."""
        pass

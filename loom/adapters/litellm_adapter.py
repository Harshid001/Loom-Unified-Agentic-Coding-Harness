import json
import logging
from typing import Any, Dict, List

from loom.adapters.base import BaseModelAdapter, ModelRequest, ModelResponse, TokenUsage, ToolCall

logger = logging.getLogger("loom.adapters")

MODEL_COSTS = {
    "gpt-4o": {"input": 0.0000025, "output": 0.00001},
    "claude-3-5-sonnet-20241022": {"input": 0.000003, "output": 0.000015},
    "gemini-1.5-pro": {"input": 0.00000125, "output": 0.000005},
    "mock": {"input": 0.0, "output": 0.0}
}

class LiteLLMAdapter(BaseModelAdapter):
    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if self.mock_mode or request.model.startswith("mock"):
            return self._mock_generate(request)

        try:
            import litellm
            messages = list(request.messages)
            if request.system_prompt:
                messages.insert(0, {"role": "system", "content": request.system_prompt})

            target_model = request.model
            if "deepseek" in target_model.lower() and not target_model.lower().startswith("deepseek/"):
                if target_model.lower() in ["deepseek", "deepseek v4 pro", "deepseek-v4 pro", "deepseek-v4", "deepseek-chat"]:
                    target_model = "deepseek/deepseek-chat"
                else:
                    target_model = f"deepseek/{target_model}"

            kwargs: Dict[str, Any] = {
                "model": target_model,
                "messages": messages,
                "temperature": request.temperature,
            }

            if request.max_tokens:
                kwargs["max_tokens"] = request.max_tokens
            if request.tools:
                kwargs["tools"] = request.tools

            res = await litellm.acompletion(**kwargs)

            choice = res.choices[0].message
            content = getattr(choice, "content", None)
            tool_calls = []

            raw_tool_calls = getattr(choice, "tool_calls", None)
            if raw_tool_calls:
                for idx, tc in enumerate(raw_tool_calls):
                    func = getattr(tc, "function", None)
                    name = getattr(func, "name", "tool") if func else "tool"
                    args_str = getattr(func, "arguments", "{}") if func else "{}"
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except Exception:
                        args = {"raw": args_str}
                    tool_calls.append(ToolCall(
                        id=getattr(tc, "id", f"call_{idx}"),
                        name=name,
                        arguments=args
                    ))

            usage_obj = getattr(res, "usage", None)
            p_tokens = getattr(usage_obj, "prompt_tokens", 0) if usage_obj else 0
            c_tokens = getattr(usage_obj, "completion_tokens", 0) if usage_obj else 0
            t_tokens = getattr(usage_obj, "total_tokens", p_tokens + c_tokens) if usage_obj else 0

            rates = MODEL_COSTS.get(request.model, {"input": 0.000003, "output": 0.000015})
            cost = (p_tokens * rates["input"]) + (c_tokens * rates["output"])

            return ModelResponse(
                content=content,
                tool_calls=tool_calls,
                usage=TokenUsage(
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    total_tokens=t_tokens,
                    estimated_cost_usd=round(cost, 6)
                ),
                model=request.model,
                finish_reason=getattr(res.choices[0], "finish_reason", "stop"),
                raw_response=res.model_dump() if hasattr(res, "model_dump") else None
            )
        except Exception as e:
            if not self.mock_mode:
                logger.error(f"LiteLLM completion failed in production mode: {e}")
                raise e
            logger.warning(f"LiteLLM completion failed, falling back to mock: {e}")
            return self._mock_generate(request)

    def _mock_generate(self, request: ModelRequest) -> ModelResponse:
        """Fallback mock generator for offline mode or test validation."""
        content = "Mock response: Operation completed successfully."
        tool_calls: List[ToolCall] = []

        # Check system/user messages for specific agent intents
        user_msg = ""
        for m in request.messages:
            if m.get("role") == "user":
                user_msg = str(m.get("content", ""))

        if "reproduc" in user_msg.lower():
            content = "Reproduction test generated and verified."
        elif "patch" in user_msg.lower():
            content = "Applied patch to resolve issue in codebase."
        elif "verify" in user_msg.lower():
            content = "All verification checks (build, unit tests, linters) passed."

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            usage=TokenUsage(
                prompt_tokens=150,
                completion_tokens=50,
                total_tokens=200,
                estimated_cost_usd=0.0005
            ),
            model=request.model,
            finish_reason="stop"
        )

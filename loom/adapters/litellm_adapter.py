import json
import logging
import os
from typing import Any, Dict, List

from loom.adapters.base import BaseModelAdapter, ModelRequest, ModelResponse, TokenUsage, ToolCall

logger = logging.getLogger("loom.adapters")

MODEL_COSTS = {
    "gpt-4o": {"input": 0.0000025, "output": 0.00001},
    "claude-3-5-sonnet-20241022": {"input": 0.000003, "output": 0.000015},
    "gemini-3-flash-preview": {"input": 0.00000015, "output": 0.0000006},
    "gemini-3-pro-preview": {"input": 0.00000125, "output": 0.000005},
    "gemini-3.7-flash": {"input": 0.00000015, "output": 0.0000006},
    "gemini-3.5-flash": {"input": 0.00000015, "output": 0.0000006},
    "gemini-3.1-flash-lite": {"input": 0.000000075, "output": 0.0000003},
    "gemini-2.5-pro": {"input": 0.00000125, "output": 0.000005},
    "gemini-2.5-flash": {"input": 0.00000015, "output": 0.0000006},
    "gemini-2.0-flash": {"input": 0.0000001, "output": 0.0000004},
    "gemini-2.0-flash-lite": {"input": 0.000000075, "output": 0.0000003},
    "gemini/gemini-3-flash-preview": {"input": 0.00000015, "output": 0.0000006},
    "gemini/gemini-3-pro-preview": {"input": 0.00000125, "output": 0.000005},
    "gemini/gemini-3.7-flash": {"input": 0.00000015, "output": 0.0000006},
    "gemini/gemini-3.5-flash": {"input": 0.00000015, "output": 0.0000006},
    "gemini/gemini-3.1-flash-lite": {"input": 0.000000075, "output": 0.0000003},
    "gemini/gemini-2.5-pro": {"input": 0.00000125, "output": 0.000005},
    "gemini/gemini-2.5-flash": {"input": 0.00000015, "output": 0.0000006},
    "gemini/gemini-2.0-flash": {"input": 0.0000001, "output": 0.0000004},
    "gemini/gemini-2.0-flash-lite": {"input": 0.000000075, "output": 0.0000003},
    "deepseek/deepseek-v4-pro": {"input": 0.00000027, "output": 0.0000011},
    "deepseek/deepseek-v4": {"input": 0.00000027, "output": 0.0000011},
    "deepseek/deepseek-chat": {"input": 0.00000027, "output": 0.0000011},
    "deepseek/deepseek-reasoner": {"input": 0.00000055, "output": 0.00000219},
    "deepseek/deepseek-v3": {"input": 0.00000027, "output": 0.0000011},
    "deepseek-v4-pro": {"input": 0.00000027, "output": 0.0000011},
    "deepseek-v4": {"input": 0.00000027, "output": 0.0000011},
    "deepseek-chat": {"input": 0.00000027, "output": 0.0000011},
    "deepseek-reasoner": {"input": 0.00000055, "output": 0.00000219},
    "deepseek-v3": {"input": 0.00000027, "output": 0.0000011},
    "mock": {"input": 0.0, "output": 0.0},
}


def _production() -> bool:
    if os.getenv("DEV_MODE", "false").lower() == "true":
        return False
    if os.getenv("ALLOW_MOCK_EXECUTION", "false").lower() == "true":
        return False
    return os.getenv("LOOM_ENV", "development").lower() in {"prod", "production"}


class LiteLLMAdapter(BaseModelAdapter):
    def __init__(self, mock_mode: bool = False):
        if _production() and mock_mode:
            raise RuntimeError("Mock model execution is disabled in production")
        self.mock_mode = mock_mode

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.model.startswith("mock"):
            if _production():
                raise RuntimeError("Mock model requests are disabled in production")
            return self._mock_generate(request)
        if self.mock_mode:
            if _production():
                raise RuntimeError("Mock model execution is disabled in production")
            return self._mock_generate(request)

        try:
            import litellm

            messages = list(request.messages)
            if request.system_prompt:
                messages.insert(0, {"role": "system", "content": request.system_prompt})

            target_model = request.model
            if "gemini" in target_model.lower() and not target_model.lower().startswith("gemini/"):
                target_model = f"gemini/{target_model}"
            elif "deepseek" in target_model.lower() and not target_model.lower().startswith("deepseek/"):
                if target_model.lower() in [
                    "deepseek",
                    "deepseek v4 pro",
                    "deepseek-v4 pro",
                    "deepseek-v4-pro",
                    "deepseek-v4",
                    "deepseek-chat",
                ]:
                    target_model = "deepseek/deepseek-chat"
                else:
                    target_model = f"deepseek/{target_model}"

            api_base = (
                os.getenv("DEEPSEEK_API_BASE")
                or os.getenv("XKIRO_API_BASE")
                or os.getenv("API_BASE")
                or os.getenv("OPENAI_API_BASE")
            )
            temp = 1.0 if "gemini-3" in target_model.lower() else request.temperature
            kwargs: Dict[str, Any] = {
                "model": target_model,
                "messages": messages,
                "temperature": temp,
            }
            if api_base:
                kwargs["api_base"] = api_base

            # Inject explicit API key if available in environment
            if target_model.startswith("gemini/"):
                gem_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                if gem_key:
                    kwargs["api_key"] = gem_key
            elif target_model.startswith("anthropic/") or "claude" in target_model.lower():
                ant_key = os.getenv("ANTHROPIC_API_KEY")
                if ant_key:
                    kwargs["api_key"] = ant_key
            elif target_model.startswith("deepseek/"):
                ds_key = os.getenv("DEEPSEEK_API_KEY")
                if ds_key:
                    kwargs["api_key"] = ds_key
            elif "gpt" in target_model.lower() or "o1" in target_model.lower() or "o3" in target_model.lower():
                oa_key = os.getenv("OPENAI_API_KEY")
                if oa_key:
                    kwargs["api_key"] = oa_key
            elif target_model.startswith("openrouter/") or os.getenv("OPENROUTER_API_KEY"):
                or_key = os.getenv("OPENROUTER_API_KEY")
                if or_key:
                    kwargs["api_key"] = or_key
                    if not target_model.startswith("openrouter/"):
                        kwargs["model"] = f"openrouter/{target_model}"

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
                    tool_calls.append(ToolCall(id=getattr(tc, "id", f"call_{idx}"), name=name, arguments=args))

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
                    estimated_cost_usd=round(cost, 6),
                ),
                model=request.model,
                finish_reason=getattr(res.choices[0], "finish_reason", "stop"),
                raw_response=res.model_dump() if hasattr(res, "model_dump") else None,
            )
        except Exception as e:
            logger.error("LiteLLM completion failed: %s", e)
            raise

    def _mock_generate(self, request: ModelRequest) -> ModelResponse:
        """Deterministic mock generator for explicit offline/test execution."""
        content = "Mock response: Operation completed successfully."
        tool_calls: List[ToolCall] = []

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
            usage=TokenUsage(prompt_tokens=150, completion_tokens=50, total_tokens=200, estimated_cost_usd=0.0005),
            model=request.model,
            finish_reason="stop",
        )

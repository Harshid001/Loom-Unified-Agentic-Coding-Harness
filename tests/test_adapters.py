import asyncio

import pytest

from loom.adapters.base import ModelRequest
from loom.adapters.litellm_adapter import LiteLLMAdapter
from loom.adapters.router import ModelRouter


def test_mock_adapter():
    async def run():
        adapter = LiteLLMAdapter(mock_mode=True)
        req = ModelRequest(model="mock", messages=[{"role": "user", "content": "Test issue reproduction"}])
        res = await adapter.generate(req)
        assert res.content is not None
        assert "Reproduction" in res.content
        assert res.usage.total_tokens > 0

    asyncio.run(run())


def test_model_router():
    router = ModelRouter(default_model="claude-3-5-sonnet-20241022", mock_mode=True)
    assert router.resolve_model("onboarding") == "mock"


def test_litellm_adapter_live_mocked():
    from unittest.mock import AsyncMock, MagicMock, patch

    async def run():
        adapter = LiteLLMAdapter(mock_mode=False)

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_999"
        mock_tool_call.function.name = "execute_command"
        mock_tool_call.function.arguments = '{"command": "pytest"}'

        mock_choice = MagicMock()
        mock_choice.message.content = "I will execute tests."
        mock_choice.message.tool_calls = [mock_tool_call]
        mock_choice.finish_reason = "tool_calls"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150

        mock_res = MagicMock()
        mock_res.choices = [mock_choice]
        mock_res.usage = mock_usage
        mock_res.model_dump.return_value = {"id": "res_123"}

        req = ModelRequest(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "Run tests"}],
            system_prompt="You are a helpful assistant",
            tools=[{"type": "function", "function": {"name": "execute_command"}}],
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_res
            res = await adapter.generate(req)

            assert res.content == "I will execute tests."
            assert len(res.tool_calls) == 1
            assert res.tool_calls[0].name == "execute_command"
            assert res.tool_calls[0].arguments == {"command": "pytest"}
            assert res.usage.prompt_tokens == 100
            assert res.usage.completion_tokens == 50
            assert res.usage.estimated_cost_usd > 0

    asyncio.run(run())


def test_litellm_adapter_exception_in_production():
    from unittest.mock import AsyncMock, patch

    async def run():
        adapter = LiteLLMAdapter(mock_mode=False)
        req = ModelRequest(
            model="claude-3-5-sonnet-20241022", messages=[{"role": "user", "content": "Test patch issue"}]
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = Exception("API connection error")
            with pytest.raises(Exception, match="API connection error"):
                await adapter.generate(req)

        # Test fallback when mock_mode=True
        mock_adapter = LiteLLMAdapter(mock_mode=True)
        res = await mock_adapter.generate(req)
        assert res.content is not None
        assert "Applied patch" in res.content

    asyncio.run(run())


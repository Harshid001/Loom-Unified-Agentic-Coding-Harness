"""Tests for loom.runtime.distributed_runtime."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from loom.infra.distributed import RedisCoordinator
from loom.orchestrator import task_graph as task_graph_module
from loom.runtime.budget import BudgetExceeded, RunBudget, cost_from_summary, tokens_from_summary
from loom.runtime.distributed_runtime import install_production_runtime


@pytest.fixture
def mock_coordinator():
    coord = MagicMock(spec=RedisCoordinator)
    coord.enabled = True
    coord.ping = AsyncMock(return_value=True)
    coord.get_run = AsyncMock(return_value={"org_id": "test_org", "status": "running"})
    coord.list_events = AsyncMock(return_value=[
        {"type": "status_change", "data": {"status": "completed"}}
    ])
    coord.record_event = AsyncMock()
    coord.update_run_status = AsyncMock()
    coord.publish_control = AsyncMock()

    client_mock = MagicMock()
    client_mock.pubsub = MagicMock()
    coord.client = client_mock
    return coord


@pytest.fixture(autouse=True)
def preserve_task_graph():
    orig_init = task_graph_module.TaskGraph.__init__
    orig_run = task_graph_module.TaskGraph.run
    orig_execute = task_graph_module.TaskGraph._execute_node_with_retry
    yield
    task_graph_module.TaskGraph.__init__ = orig_init
    task_graph_module.TaskGraph.run = orig_run
    task_graph_module.TaskGraph._execute_node_with_retry = orig_execute


@pytest.mark.asyncio
async def test_install_production_runtime_requires_redis(monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    app = FastAPI()
    mock_server = MagicMock()

    with patch("loom.runtime.distributed_runtime.RedisCoordinator") as mock_coord_cls:
        coord_inst = MagicMock()
        coord_inst.enabled = False
        mock_coord_cls.return_value = coord_inst

        with pytest.raises(RuntimeError, match="Production runtime requires REDIS_URL"):
            await install_production_runtime(app, mock_server)


@pytest.mark.asyncio
async def test_install_production_runtime_dev_mode_skips(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    app = FastAPI()
    mock_server = MagicMock()
    await install_production_runtime(app, mock_server)
    assert not hasattr(app.state, "distributed_installed")


@pytest.mark.asyncio
async def test_install_production_runtime_success(mock_coordinator, monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    app = FastAPI()
    mock_server = MagicMock()
    mock_server.control_run = AsyncMock()
    mock_server.stream_run_events = AsyncMock()
    mock_server.PrincipalDep = MagicMock
    mock_server.ControlRequest = MagicMock
    mock_server.ACTIVE_RUNS = {}

    @app.get("/api/v1/stream/{run_id}")
    async def stream_route(run_id: str):
        return {"stream": run_id}

    @app.post("/api/v1/run/control")
    async def control_route():
        return {"control": True}

    @app.get("/api/v1/auth/tokens")
    async def token_route():
        return {"tokens": []}

    with patch("loom.runtime.distributed_runtime.RedisCoordinator", return_value=mock_coordinator):
        await install_production_runtime(app, mock_server)

    assert app.state.distributed_installed is True
    assert app.state.redis_coordinator == mock_coordinator


def test_budget_exceeded_helpers():
    summary = {
        "total_cost_usd": 4.50,
        "total_tokens": 125000,
    }
    assert cost_from_summary(summary) == 4.50
    assert tokens_from_summary(summary) == 125000

    budget = RunBudget(
        max_duration_seconds=60.0,
        max_cost_usd=5.0,
        max_tokens=100000,
        max_agent_steps=10,
    )
    assert budget.max_duration_seconds == 60.0
    assert budget.max_cost_usd == 5.0

    exc = BudgetExceeded("Test limit reached")
    assert str(exc) == "Test limit reached"

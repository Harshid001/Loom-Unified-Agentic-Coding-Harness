"""Tests for loom.runtime.distributed_runtime."""
from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute

from loom.adapters.router import ModelRouter
from loom.infra.distributed import RedisCoordinator
from loom.orchestrator import task_graph as task_graph_module
from loom.orchestrator.state import OrchestratorState
from loom.runtime.budget import BudgetExceeded, RunBudget, cost_from_summary, tokens_from_summary
from loom.runtime.distributed_runtime import install_production_runtime
from loom.telemetry.cost_tracker import CostTracker
from loom.telemetry.tracer import TelemetryTracer


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


@pytest.mark.asyncio
async def test_distributed_rate_limiting_middleware(mock_coordinator, monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    app = FastAPI()
    mock_server = MagicMock()
    mock_server.control_run = AsyncMock()
    mock_server.stream_run_events = AsyncMock()
    mock_server.ACTIVE_RUNS = {}

    @app.get("/api/v1/test")
    async def api_test_route():
        return {"ok": True}

    @app.get("/health")
    async def health_route():
        return {"status": "healthy"}

    with patch("loom.runtime.distributed_runtime.RedisCoordinator", return_value=mock_coordinator):
        await install_production_runtime(app, mock_server)

    from starlette.testclient import TestClient
    client = TestClient(app)

    # When rate limiter allows
    with patch.object(app.state.redis_rate_limiter, "allow", new=AsyncMock(return_value=True)):
        res = client.get("/api/v1/test")
        assert res.status_code == 200

    # When rate limiter blocks
    with patch.object(app.state.redis_rate_limiter, "allow", new=AsyncMock(return_value=False)):
        res = client.get("/api/v1/test")
        assert res.status_code == 429
        assert "Rate limit exceeded" in res.json()["detail"]

    # Non-API path bypasses rate limiting
    with patch.object(app.state.redis_rate_limiter, "allow", new=AsyncMock(return_value=False)):
        res = client.get("/health")
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_wrapped_stream_and_control_and_token_block(mock_coordinator, monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    @dataclass
    class FakePrincipal:
        org_id: str

    @dataclass
    class FakeControlReq:
        run_id: str
        action: str
        model: str | None = None
        snapshot_id: str | None = None

    app = FastAPI()
    mock_server = MagicMock()
    mock_server.control_run = AsyncMock(return_value={"local_control": True})
    mock_server.stream_run_events = AsyncMock(return_value={"local_stream": True})
    mock_server.PrincipalDep = FakePrincipal
    mock_server.ControlRequest = FakeControlReq
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

    routes = {r.path: r for r in app.routes if isinstance(r, APIRoute)}

    # 1. Token admin block
    token_endpoint = routes["/api/v1/auth/tokens"].endpoint
    with pytest.raises(HTTPException) as exc_info:
        token_endpoint()
    assert exc_info.value.status_code == 403

    # 2. Control endpoint - Local run
    mock_server.ACTIVE_RUNS["run_local"] = MagicMock()
    control_endpoint = routes["/api/v1/run/control"].endpoint
    res_local = await control_endpoint(FakeControlReq(run_id="run_local", action="pause"), FakePrincipal(org_id="test_org"))
    assert res_local == {"local_control": True}

    # 3. Control endpoint - Remote run
    mock_coordinator.get_run = AsyncMock(return_value={"org_id": "test_org", "status": "running"})
    res_remote = await control_endpoint(FakeControlReq(run_id="run_remote", action="pause"), FakePrincipal(org_id="test_org"))
    assert res_remote["status"] == "accepted"
    assert res_remote["remote"] is True
    assert mock_coordinator.publish_control.called

    # 4. Control endpoint - Remote run org mismatch
    with pytest.raises(HTTPException) as exc_mismatch:
        await control_endpoint(FakeControlReq(run_id="run_remote", action="pause"), FakePrincipal(org_id="wrong_org"))
    assert exc_mismatch.value.status_code == 404

    # 5. Stream endpoint - Local run
    stream_endpoint = routes["/api/v1/stream/{run_id}"].endpoint
    res_stream_local = await stream_endpoint("run_local", FakePrincipal(org_id="test_org"))
    assert res_stream_local == {"local_stream": True}

    # 6. Stream endpoint - Remote run terminal in history
    mock_coordinator.list_events = AsyncMock(return_value=[
        {"type": "status_change", "data": {"status": "completed"}}
    ])
    res_stream_remote = await stream_endpoint("run_remote", FakePrincipal(org_id="test_org"))
    assert res_stream_remote.media_type == "text/event-stream"
    body_chunks = [chunk async for chunk in res_stream_remote.body_iterator]
    assert any("completed" in c for c in body_chunks)

    # 7. Stream endpoint - Remote run not found
    mock_coordinator.get_run = AsyncMock(return_value=None)
    res_not_found = await stream_endpoint("run_missing", FakePrincipal(org_id="test_org"))
    assert res_not_found.status_code == 404


@pytest.mark.asyncio
async def test_task_graph_production_wrapping_and_budget_enforcement(mock_coordinator, monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    app = FastAPI()
    mock_server = MagicMock()
    mock_server.control_run = AsyncMock()
    mock_server.stream_run_events = AsyncMock()
    mock_server.ACTIVE_RUNS = {}

    async def fake_control_stream(run_id):
        yield {"action": "pause"}
        yield {"action": "resume"}
        yield {"action": "step"}
        yield {"action": "model_switch", "payload": {"model": "gpt-4o"}}
        yield {"action": "cancel"}

    mock_coordinator.control_stream = fake_control_stream
    mock_coordinator.register_run = AsyncMock()

    with patch("loom.runtime.distributed_runtime.RedisCoordinator", return_value=mock_coordinator):
        await install_production_runtime(app, mock_server)

    state = OrchestratorState(run_id="run_wrapped", repo_path="/tmp", issue_description="test issue")
    state.shared_data["org_id"] = "org_test"

    on_start_called = []
    on_log_called = []
    on_complete_called = []
    on_fail_called = []

    graph = task_graph_module.TaskGraph(
        state,
        ModelRouter(mock_mode=True),
        TelemetryTracer(run_id="run_wrapped"),
        CostTracker(run_id="run_wrapped"),
        on_step_start=lambda s, m: on_start_called.append((s, m)),
        on_step_log=lambda s, level, msg: on_log_called.append((s, level, msg)),
        on_step_complete=lambda s, o: on_complete_called.append((s, o)),
        on_step_fail=lambda s, e: on_fail_called.append((s, e)),
    )

    # Trigger custom step callbacks injected by wrapped_init
    graph.on_step_start_cb("onboarding", "mock")
    assert ("onboarding", "mock") in on_start_called

    graph.on_step_log_cb("onboarding", "INFO", "Started step")
    assert ("onboarding", "INFO", "Started step") in on_log_called

    graph.on_step_complete_cb("onboarding", {"_usage": {"tokens": 50}})
    assert len(on_complete_called) == 1

    graph.on_step_fail_cb("onboarding", "error reason")
    assert ("onboarding", "error reason") in on_fail_called

    # Test budget enforcement helper
    # 1. Max duration exceeded
    monkeypatch.setenv("LOOM_MAX_RUN_DURATION_SECONDS", "0.01")
    time.sleep(0.02)
    with pytest.raises(BudgetExceeded, match="exceeded duration budget"):
        await graph._execute_node_with_retry("onboarding", task_graph_module.OnboardingAgent, "mock")

    # 2. Max cost exceeded
    monkeypatch.delenv("LOOM_MAX_RUN_DURATION_SECONDS", raising=False)
    monkeypatch.setenv("LOOM_MAX_RUN_COST_USD", "0.0001")
    graph.cost_tracker.add_usage("onboarding", 1000, 1000, 0.05, model_id="gpt-4o")
    with pytest.raises(BudgetExceeded, match="exceeded cost budget"):
        await graph._execute_node_with_retry("onboarding", task_graph_module.OnboardingAgent, "mock")

    # 3. Max tokens exceeded
    monkeypatch.delenv("LOOM_MAX_RUN_COST_USD", raising=False)
    monkeypatch.setenv("LOOM_MAX_RUN_TOKENS", "10")
    with pytest.raises(BudgetExceeded, match="exceeded token budget"):
        await graph._execute_node_with_retry("onboarding", task_graph_module.OnboardingAgent, "mock")


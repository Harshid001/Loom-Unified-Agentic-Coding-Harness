import os

import pytest
from fastapi.testclient import TestClient

from loom.adapters.model_router import ModelRouter, set_runtime_api_key
from loom.api.dependencies import reset_entitlements
from loom.api.models import clear_session_keys, get_session_keys
from loom.api.routes.settings import set_current_active_model
from loom.api.server import app
from loom.business.usage_ledger import get_usage_ledger, reset_usage_ledger
from loom.db.records_store import get_run_record_store, reset_run_record_store
from loom.orchestrator.state import OrchestratorState
from loom.orchestrator.task_graph import TaskGraph

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("LOOM_EVIDENCE_DIR", str(tmp_path / "evidence"))
    reset_entitlements()
    reset_usage_ledger()
    get_usage_ledger(str(tmp_path / "ledger"))
    reset_run_record_store()
    get_run_record_store(str(tmp_path / "records.db"))
    clear_session_keys()
    set_current_active_model("claude-3-7-sonnet-20250219")


def test_runtime_api_key_override(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    router = ModelRouter()
    router.set_runtime_api_key("anthropic", "sk-ant-test-key-12345")
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-key-12345"

    set_runtime_api_key("openai", "sk-proj-test-key-67890")
    assert os.environ.get("OPENAI_API_KEY") == "sk-proj-test-key-67890"

    set_runtime_api_key("deepseek", "sk-deepseek-test-key-11111")
    assert os.environ.get("DEEPSEEK_API_KEY") == "sk-deepseek-test-key-11111"

    set_runtime_api_key("gemini", "AIzaSyTestKeyGemini99999")
    assert os.environ.get("GEMINI_API_KEY") == "AIzaSyTestKeyGemini99999"
    assert os.environ.get("GOOGLE_API_KEY") == "AIzaSyTestKeyGemini99999"


def test_runtime_models_persistence_in_shared_data(tmp_path):
    from loom.telemetry.cost_tracker import CostTracker
    from loom.telemetry.tracer import TelemetryTracer

    state = OrchestratorState(run_id="run-persist-test", repo_path=str(tmp_path), issue_description="test issue")
    router = ModelRouter(default_model="gpt-4o", mock_mode=True)
    tracer = TelemetryTracer(run_id="run-persist-test")
    cost_tracker = CostTracker(run_id="run-persist-test")
    graph = TaskGraph(state=state, router=router, tracer=tracer, cost_tracker=cost_tracker)
    assert graph.state is state

    assert "_runtime_models" in state.shared_data
    runtime_models = state.shared_data["_runtime_models"]
    assert runtime_models["active_model"] == "gpt-4o"
    assert "gpt-4o" in runtime_models["eligible_models"]

    router.set_model("deepseek-v3", shared_data=state.shared_data)
    assert state.shared_data["_runtime_models"]["active_model"] == "deepseek-v3"


def test_detect_models_unauthenticated():
    res = client.post("/api/models/detect", json={"provider": "anthropic", "api_key": "sk-ant-test-key-12345"})
    assert res.status_code == 401


def test_detect_models_success():
    headers = {"X-API-Key": "test-api-key"}

    # Test Anthropic
    res = client.post(
        "/api/models/detect",
        json={"provider": "Anthropic", "api_key": "sk-ant-api03-validkey-xyz"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["provider"] == "anthropic"
    assert len(data["models"]) > 0
    assert any("claude" in m for m in data["models"])
    assert get_session_keys().get("anthropic") == "sk-ant-api03-validkey-xyz"
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-api03-validkey-xyz"

    # Test OpenAI
    res = client.post(
        "/api/v1/models/detect",
        json={"provider": "openai", "api_key": "sk-proj-testkey123456"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert any("gpt-4o" in m for m in data["models"])

    # Test DeepSeek
    res = client.post(
        "/api/models/detect",
        json={"provider": "DeepSeek", "api_key": "sk-ds-testkey123456"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert any("deepseek" in m for m in data["models"])

    # Test Gemini
    res = client.post(
        "/api/models/detect",
        json={"provider": "gemini", "api_key": "AIzaSyTestApiKey12345"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert any("gemini" in m for m in data["models"])


def test_detect_models_invalid_key():
    headers = {"X-API-Key": "test-api-key"}
    res = client.post(
        "/api/models/detect",
        json={"provider": "anthropic", "api_key": ""},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    assert data["models"] == []


def test_settings_model_get_and_put():
    headers = {"X-API-Key": "test-api-key"}

    # GET settings
    res = client.get("/api/settings/model", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "active_model" in data
    assert "available_models" in data
    assert "providers" in data
    assert "anthropic" in data["providers"]
    assert "openai" in data["providers"]
    assert "deepseek" in data["providers"]
    assert "gemini" in data["providers"]

    # PUT settings
    res = client.put(
        "/api/settings/model",
        json={"model": "gpt-4o", "provider": "openai", "api_key": "sk-proj-testkey-put"},
        headers=headers,
    )
    assert res.status_code == 200
    put_data = res.json()
    assert put_data["active_model"] == "gpt-4o"
    assert put_data["status"] == "ok"
    assert os.environ.get("OPENAI_API_KEY") == "sk-proj-testkey-put"

    # Verify GET reflects update
    res_updated = client.get("/api/v1/settings/model", headers=headers)
    assert res_updated.status_code == 200
    assert res_updated.json()["active_model"] == "gpt-4o"


def test_settings_model_put_empty_rejected():
    headers = {"X-API-Key": "test-api-key"}
    res = client.put(
        "/api/settings/model",
        json={"model": "   "},
        headers=headers,
    )
    assert res.status_code == 400

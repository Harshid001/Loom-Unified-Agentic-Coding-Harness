import pytest
from fastapi.testclient import TestClient

from loom.api.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_api_key_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-api-key")


def test_liveness_health():
    res = client.get("/api/v1/health/liveness")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "alive"


def test_readiness_health():
    res = client.get("/api/v1/health/readiness")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert "components" in data


def test_legacy_health_alias():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_list_runs_unauthenticated():
    res = client.get("/api/v1/runs")
    assert res.status_code == 401


def test_list_runs_authenticated():
    res = client.get("/api/v1/runs", headers={"X-API-Key": "test-api-key"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_unauthenticated_create_run_rejected():
    payload = {"issue": "test unauth", "mock": True}
    res = client.post("/api/v1/run", json=payload)
    assert res.status_code == 401


def test_create_run_mock():
    payload = {"issue": "test api issue reproduction", "mock": True}
    headers = {"X-API-Key": "test-api-key"}
    res = client.post("/api/v1/run", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert data["status"] in ["VERIFIED SUCCESS", "FAILED"]
    assert "patch_diff" in data


def test_get_nonexistent_run():
    res = client.get("/api/v1/runs/nonexistent_id_123", headers={"X-API-Key": "test-api-key"})
    assert res.status_code == 404


def test_metrics_endpoint():
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "loom_requests_total" in res.text or "prometheus_client" in res.text


def test_security_headers():
    res = client.get("/api/v1/health/liveness")
    assert res.status_code == 200
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("x-xss-protection") == "1; mode=block"
    assert "max-age=" in res.headers.get("strict-transport-security", "")
    assert res.headers.get("content-security-policy") == "default-src 'self'"
    assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

import pytest


def test_verified_token_identity_is_authoritative(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "server-secret")
    monkeypatch.setenv("API_KEY_USER_ID", "alice")
    monkeypatch.setenv("API_KEY_ORG_ID", "org_a")

    from loom.api.server import get_effective_principal

    principal = get_effective_principal()
    assert principal.user_id == "alice"
    assert principal.org_id == "org_a"


def test_forged_identity_headers_cannot_change_production_role(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "server-secret")
    monkeypatch.setenv("API_KEY_USER_ID", "alice")
    monkeypatch.setenv("API_KEY_ORG_ID", "org_a")

    from loom.api.server import get_effective_principal

    principal = get_effective_principal(user_id_header="owner", org_id_header="org_b")
    assert principal.user_id == "alice"
    assert principal.org_id == "org_a"


def test_production_rbac_rejects_cross_org_resource_even_for_owner_role(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "server-secret")
    monkeypatch.setenv("API_KEY_USER_ID", "alice")
    monkeypatch.setenv("API_KEY_ORG_ID", "org_a")

    from loom.business.rbac import require_permission

    assert require_permission("alice", "org_a", "OWNER", "runs:read") is True
    with pytest.raises(Exception):
        require_permission("alice", "org_b", "OWNER", "runs:read")


def test_shared_api_key_uses_fixed_service_identity(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "server-secret")
    monkeypatch.setenv("API_KEY_USER_ID", "service")
    monkeypatch.setenv("API_KEY_ORG_ID", "default")

    from loom.api.server import get_effective_principal

    principal = get_effective_principal()
    assert principal.user_id == "service"
    assert principal.org_id == "default"


def test_production_request_org_ignores_forged_header(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "server-secret")
    monkeypatch.setenv("API_KEY_USER_ID", "alice")
    monkeypatch.setenv("API_KEY_ORG_ID", "org_a")

    from loom.api.server import resolve_request_org

    assert resolve_request_org("org_b") == "org_a"


def test_production_token_mint_requires_authentication(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "server-secret")

    from fastapi.testclient import TestClient

    from loom.api.server import app

    response = TestClient(app).post("/api/v1/auth/tokens", json={"user_id": "attacker", "org_id": "default"})
    assert response.status_code == 401


def test_stream_requires_authentication_and_org_scope(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "server-secret")
    monkeypatch.setenv("API_KEY_ORG_ID", "org_a")
    monkeypatch.setenv("API_KEY_USER_ID", "alice")
    # This test targets stream authentication/tenant isolation; Redis availability
    # is covered separately by the production rate-limiter tests.
    monkeypatch.setenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "true")

    from fastapi.testclient import TestClient

    from loom.api.server import ACTIVE_RUNS, app
    from loom.business.models import RunRecord
    from loom.db.records_store import get_run_record_store
    from loom.orchestrator.state import OrchestratorState

    get_run_record_store().record_run(RunRecord(run_id="run_stream_auth", org_id="org_a", issue_text="stream auth"))
    state = OrchestratorState(run_id="run_stream_auth", repo_path="/tmp/repo", issue_description="stream auth")
    state.shared_data["org_id"] = "org_a"
    ACTIVE_RUNS["run_stream_auth"] = {
        "queues": [],
        "events": [{"type": "status_change", "data": {"status": "completed"}}],
        "state": state,
    }

    client = TestClient(app)
    try:
        unauth = client.get("/api/v1/stream/run_stream_auth")
        assert unauth.status_code == 401

        monkeypatch.setenv("API_KEY_ORG_ID", "org_b")
        foreign = client.get("/api/v1/stream/run_stream_auth", headers={"X-API-Key": "server-secret"})
        assert foreign.status_code == 404

        monkeypatch.setenv("API_KEY_ORG_ID", "org_a")
        authorized = client.get("/api/v1/stream/run_stream_auth", headers={"X-API-Key": "server-secret"})
        assert authorized.status_code == 200
        assert "status_change" in authorized.text
    finally:
        ACTIVE_RUNS.pop("run_stream_auth", None)

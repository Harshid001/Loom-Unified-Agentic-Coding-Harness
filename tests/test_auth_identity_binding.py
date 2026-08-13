import pytest
from fastapi import HTTPException

from loom.auth.api_tokens import ApiTokenStore
from loom.auth.context import AuthenticatedPrincipal, clear_principal, get_effective_principal, set_principal
from loom.business.entitlements import EntitlementService
from loom.business.models import Membership, MembershipRole, Organization, OrgTier
from loom.business.rbac import Action, RBACEnforcer


@pytest.fixture(autouse=True)
def reset_identity_context():
    clear_principal()
    yield
    clear_principal()


def test_verified_token_identity_is_authoritative(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("LOOM_TOKEN_ADMIN_ENABLED", "true")

    store = ApiTokenStore(storage_dir=str(tmp_path / "tokens"))
    record, token = store.issue("alice", org_id="org_a", label="alice-token")

    verified = store.verify(token)
    assert verified is not None

    principal = get_effective_principal()
    assert principal.user_id == "alice"
    assert principal.org_id == "org_a"
    assert principal.token_id == record.id
    assert principal.auth_method == "api_token"


def test_forged_identity_headers_cannot_change_production_role(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("LOOM_TOKEN_ADMIN_ENABLED", "true")

    store = ApiTokenStore(storage_dir=str(tmp_path / "tokens"))
    _, token = store.issue("alice", org_id="org_a")
    store.issue("victim-owner", org_id="org_b")
    assert store.verify(token) is not None

    svc = EntitlementService()
    svc.register_org(Organization(name="A", tier=OrgTier.TEAM, id="org_a"))
    svc.register_org(Organization(name="B", tier=OrgTier.ENTERPRISE, id="org_b"))
    svc.add_membership(Membership(user_id="alice", org_id="org_a", role=MembershipRole.DEVELOPER))
    svc.add_membership(Membership(user_id="victim-owner", org_id="org_b", role=MembershipRole.OWNER))

    # This models a request carrying forged X-User-Id/X-Org-Id values.
    role = svc.get_role("org_b", "victim-owner")
    assert role == MembershipRole.DEVELOPER


def test_production_rbac_rejects_cross_org_resource_even_for_owner_role(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.delenv("API_KEY_ORG_ID", raising=False)
    monkeypatch.delenv("API_KEY_USER_ID", raising=False)

    enforcer = RBACEnforcer(MembershipRole.OWNER)
    with pytest.raises(HTTPException) as exc_info:
        enforcer.authorize(Action.TRIGGER_RUN, resource="org:attacker-org")

    assert exc_info.value.status_code == 403
    assert "organization scope" in str(exc_info.value.detail).lower()


def test_shared_api_key_uses_fixed_service_identity(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY_USER_ID", "service_user")
    monkeypatch.setenv("API_KEY_ORG_ID", "service_org")

    principal = get_effective_principal()
    assert principal.user_id == "service_user"
    assert principal.org_id == "service_org"
    assert principal.auth_method == "api_key"


def test_production_request_org_ignores_forged_header(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    set_principal(AuthenticatedPrincipal(user_id="alice", org_id="org_a", token_id="tok_a", auth_method="api_token"))

    from loom.api.server import _request_org_id

    assert _request_org_id("org_b") == "org_a"


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

    from fastapi.testclient import TestClient

    from loom.api.server import ACTIVE_RUNS, app
    from loom.orchestrator.state import OrchestratorState

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

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loom.api.server import app
from loom.api.webhooks import get_webhook_engine, reset_webhook_engine
from loom.business.usage_ledger import get_usage_ledger, reset_usage_ledger
from loom.db.records_store import get_run_record_store, reset_run_record_store
from loom.scim.provisioning import get_scim_provisioner, reset_scim_provisioner

client = TestClient(app)


from loom.api.dependencies import reset_entitlements


@pytest.fixture(autouse=True)
def setup_api_key_env(monkeypatch, tmp_path):
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("API_KEY_ORG_ID", "default")
    monkeypatch.setenv("API_KEY_USER_ID", "dev_user")
    monkeypatch.setenv("LOOM_EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setenv("LOOM_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.setenv("LOOM_HOME", str(tmp_path))
    monkeypatch.setenv("LOOM_DB_PATH", str(tmp_path / "loom.db"))
    monkeypatch.setenv("ALLOWED_REPO_ROOTS", f"{tmp_path},{Path('.').resolve()}")
    monkeypatch.setenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "true")
    from loom.api.dependencies import get_entitlements
    from loom.api.server import coordinator
    from loom.auth.context import clear_principal
    from loom.infra.run_state import reset_run_store

    clear_principal()
    reset_entitlements()
    get_entitlements()
    reset_usage_ledger()
    get_usage_ledger(str(tmp_path / "ledger"))
    reset_webhook_engine()
    get_webhook_engine(str(tmp_path / "webhooks"))
    reset_run_record_store()
    get_run_record_store(str(tmp_path / "records.db"))
    reset_scim_provisioner()
    get_scim_provisioner(str(tmp_path / "scim"))
    coordinator.reset()
    reset_run_store()
    yield
    clear_principal()
    coordinator.reset()
    reset_run_store()


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
    assert res.status_code in (401, 403)


def test_list_runs_authenticated():
    res = client.get("/api/v1/runs", headers={"X-API-Key": "test-api-key"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_unauthenticated_create_run_rejected():
    payload = {"issue": "test unauth", "mock": True}
    res = client.post("/api/v1/run", json=payload)
    assert res.status_code in (401, 403)


def test_create_run_mock():
    payload = {"issue": "test api issue reproduction", "mock": True}
    headers = {"X-API-Key": "test-api-key"}
    res = client.post("/api/v1/run", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert data["status"] in ["VERIFIED SUCCESS", "FAILED"]
    assert "patch_diff" in data


def test_create_run_exports_evidence_bundle():
    payload = {"issue": "evidence export check", "mock": True}
    headers = {"X-API-Key": "test-api-key"}
    res = client.post("/api/v1/run", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["evidence"]["exported"] is True
    assert data["evidence"]["chain_hash"]

    run_id = data["run_id"]
    evidence_res = client.get(f"/api/v1/runs/{run_id}/evidence", headers=headers)
    assert evidence_res.status_code == 200
    evidence = evidence_res.json()
    assert evidence["evidence_bundle"]["run_id"] == run_id
    assert evidence["chain_integrity"] is True
    assert "merge_decision" in data


def test_create_run_rbac_blocks_developer_from_admin_action():
    from loom.api.server import _default_org
    headers = {
        "X-API-Key": "test-api-key",
        "X-Org-Id": _default_org.id,
        "X-User-Id": "dev_developer",
    }
    from loom.api.dependencies import get_entitlements
    from loom.business.models import Membership, MembershipRole
    get_entitlements().add_membership(
        Membership(user_id="dev_developer", org_id=_default_org.id, role=MembershipRole.DEVELOPER)
    )
    payload = {"org_id": _default_org.id, "feature_key": "sandbox.tier_b_container"}
    res = client.post("/v1/entitlements/check", json=payload, headers=headers)
    assert res.status_code == 403


def test_entitlement_check_allowed_for_owner():
    from loom.api.server import _default_org
    headers = {"X-API-Key": "test-api-key"}
    payload = {"org_id": _default_org.id, "feature_key": "integrations.ide_plugins"}
    res = client.post("/v1/entitlements/check", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["allowed"] is True


def test_create_run_tier_b_denied_on_solo_org():
    from loom.api.server import _default_org
    headers = {"X-API-Key": "test-api-key", "X-Org-Id": _default_org.id}
    payload = {"issue": "tier b", "mock": True, "sandbox_tier": "B"}
    res = client.post("/api/v1/run", json=payload, headers=headers)
    assert res.status_code == 403
    assert "solo" in res.json()["detail"]


def test_create_run_tier_c_denied_on_solo_org():
    from loom.api.server import _default_org
    headers = {"X-API-Key": "test-api-key", "X-Org-Id": _default_org.id}
    payload = {"issue": "tier c", "mock": True, "sandbox_tier": "C"}
    res = client.post("/api/v1/run", json=payload, headers=headers)
    assert res.status_code == 403


def test_create_run_invalid_sandbox_tier_rejected():
    from loom.api.server import _default_org
    headers = {"X-API-Key": "test-api-key", "X-Org-Id": _default_org.id}
    payload = {"issue": "tier z", "mock": True, "sandbox_tier": "Z"}
    res = client.post("/api/v1/run", json=payload, headers=headers)
    assert res.status_code == 400


def test_create_run_tier_a_allowed_on_solo_org():
    headers = {"X-API-Key": "test-api-key"}
    payload = {"issue": "tier a", "mock": True, "sandbox_tier": "A"}
    res = client.post("/api/v1/run", json=payload, headers=headers)
    assert res.status_code == 200


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


def test_ci_report_triggers_auto_rollback(tmp_path, monkeypatch):
    import time

    import httpx

    from loom.api.webhooks import WebhookEventType, WebhookSubscription
    from loom.business.audit_log import get_audit_logger, reset_audit_logger
    from loom.business.models import AuditAction, RunRecord
    from loom.orchestrator.state import OrchestratorState

    reset_audit_logger()
    get_audit_logger(str(tmp_path / "audit"))

    class FakeAsyncClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, content=None, headers=None, timeout=None):
            self.calls.append({"url": url, "content": content, "headers": headers})
            return httpx.Response(200, text="ok")

        async def aclose(self):
            pass

    engine = get_webhook_engine()
    engine._http = FakeAsyncClient()
    engine.register(
        WebhookSubscription(
            id="sub_ci",
            org_id="default",
            url="https://example.com/ci",
            events={WebhookEventType.RUN_ROLLED_BACK},
            max_retries=1,
            retry_backoff_base_seconds=0.01,
        )
    )

    get_run_record_store().record_run(RunRecord(run_id="run_ci_report", org_id="default", issue_text="ci report test"))

    patch_diff = (
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    state = OrchestratorState(
        run_id="run_ci_report",
        repo_path=str(tmp_path / "repo"),
        issue_description="ci report test",
    )
    state.shared_data["org_id"] = "default"
    state.patch_diff = patch_diff
    state.save_checkpoint()

    headers = {"X-API-Key": "test-api-key"}
    res = client.post(
        "/api/v1/runs/run_ci_report/ci-report",
        json={"merge_time": time.time() - 30, "ci_failure_detected": True},
        headers=headers,
    )
    assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
    data = res.json()
    assert data["rollback_needed"] is True
    assert data["revert_patch"] != ""
    assert "-new" in data["revert_patch"]

    updated = OrchestratorState.load_checkpoint("run_ci_report")
    assert updated.shared_data["run_status"] == "rolled_back"
    assert updated.shared_data["merge_decision"]["auto_rolled_back"] is True

    entries = get_audit_logger().get_entries(org_id="default", action=AuditAction.RUN_ROLLED_BACK)
    assert len(entries) == 1
    assert entries[0].actor_id == "ci_monitor"

    assert len(engine._http.calls) == 1
    import json as _json

    payload = _json.loads(engine._http.calls[0]["content"])
    assert payload["event"] == WebhookEventType.RUN_ROLLED_BACK.value


def test_ci_report_no_rollback_without_ci_failure(tmp_path, monkeypatch):
    from loom.business.models import RunRecord
    from loom.orchestrator.state import OrchestratorState

    get_run_record_store().record_run(RunRecord(run_id="run_ci_ok", org_id="default", issue_text="ci ok"))

    state = OrchestratorState(
        run_id="run_ci_ok",
        repo_path=str(tmp_path / "repo"),
        issue_description="ci ok",
    )
    state.shared_data["org_id"] = "default"
    state.patch_diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
    state.save_checkpoint()

    res = client.post(
        "/api/v1/runs/run_ci_ok/ci-report",
        json={"merge_time": 1234.0, "ci_failure_detected": False},
        headers={"X-API-Key": "test-api-key"},
    )
    assert res.status_code == 200
    assert res.json()["rollback_needed"] is False


def test_ci_report_unknown_run_returns_404(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: Path(str(tmp_path)))
    res = client.post(
        "/api/v1/runs/does_not_exist/ci-report",
        json={"merge_time": 1234.0, "ci_failure_detected": True},
        headers={"X-API-Key": "test-api-key"},
    )
    assert res.status_code == 404


def test_run_records_endpoint():
    payload = {"issue": "records api check", "mock": True}
    headers = {"X-API-Key": "test-api-key"}
    res = client.post("/api/v1/run", json=payload, headers=headers)
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    records_res = client.get(f"/api/v1/runs/{run_id}/records", headers=headers)
    assert records_res.status_code == 200
    data = records_res.json()
    assert data["run"]["run_id"] == run_id
    assert data["run"]["status"] in (
        "merged",
        "evidence_review",
        "failed",
        "security_hold",
        "conflict_resolution",
        "rolled_back",
    )
    steps = data["steps"]
    assert len(steps) >= 5
    assert {s["agent_name"] for s in steps} >= {"onboarding", "reproduction", "planner", "patcher", "verifier"}
    assert len(data["verifications"]) == 5
    patch_rows = data["patches"]
    assert len(patch_rows) == 1


def test_run_records_unknown_run_returns_404():
    res = client.get("/api/v1/runs/nonexistent_records_123/records", headers={"X-API-Key": "test-api-key"})
    assert res.status_code == 404


def test_scim_users_unauthenticated_returns_401(monkeypatch):
    monkeypatch.setenv("SCIM_TOKEN", "scim-test-secret")
    res = client.get("/scim/v2/Users")
    assert res.status_code == 401


def test_scim_users_disabled_returns_503(monkeypatch):
    monkeypatch.delenv("SCIM_TOKEN", raising=False)
    res = client.get("/scim/v2/Users")
    assert res.status_code == 503


def test_scim_users_crud_authenticated(monkeypatch):
    monkeypatch.setenv("SCIM_TOKEN", "scim-test-secret")
    headers = {"Authorization": "Bearer scim-test-secret"}

    # List empty users
    res = client.get("/scim/v2/Users", headers=headers)
    assert res.status_code == 200
    assert "Resources" in res.json()

    # Create user
    user_payload = {
        "orgId": "org_scim_test",
        "urn:ietf:params:scim:schemas:core:2.0:User": {
            "userName": "bob_builder",
            "displayName": "Bob Builder",
            "emails": [{"value": "bob@example.com", "primary": True}],
            "active": True,
        },
    }
    create_res = client.post("/scim/v2/Users", json=user_payload, headers=headers)
    assert create_res.status_code == 200
    created_user = create_res.json()
    assert created_user["userName"] == "bob_builder"
    user_id = created_user["id"]

    # Get user by ID
    get_res = client.get(f"/scim/v2/Users/{user_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == user_id

    # Delete user
    del_res = client.delete(f"/scim/v2/Users/{user_id}", headers=headers)
    assert del_res.status_code == 204


def test_issue_and_authenticate_with_api_token(monkeypatch):
    from loom.auth.api_tokens import reset_api_token_store

    reset_api_token_store()
    monkeypatch.setenv("API_KEY", "env-secret-key")
    monkeypatch.setenv("API_KEY_ORG_ID", "default")
    monkeypatch.setenv("API_KEY_USER_ID", "dev_user")
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("LOOM_TOKEN_ADMIN_ENABLED", "true")

    # Issue API token through the authenticated shared API key.
    issue_res = client.post(
        "/api/v1/auth/tokens",
        json={"user_id": "alice_dev", "label": "test-key"},
        headers={"X-API-Key": "env-secret-key"},
    )
    assert issue_res.status_code == 200
    issued_data = issue_res.json()
    token = issued_data["token"]
    token_id = issued_data["token_id"]

    # Use issued token to authenticate list_runs endpoint
    runs_res = client.get("/api/v1/runs", headers={"X-API-Key": token})
    assert runs_res.status_code == 200

    # List tokens
    list_res = client.get("/api/v1/auth/tokens", headers={"X-API-Key": token})
    assert list_res.status_code == 200
    assert any(t["id"] == token_id for t in list_res.json())

    # Revoke token
    del_res = client.delete(f"/api/v1/auth/tokens/{token_id}", headers={"X-API-Key": "env-secret-key"})
    assert del_res.status_code == 200
    assert del_res.json()["revoked"] is True

    # Confirm revoked token can no longer authenticate
    revoked_res = client.get("/api/v1/runs", headers={"X-API-Key": token})
    assert revoked_res.status_code == 401


def test_production_auth_fail_closed(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("LOOM_ENV", "production")

    res = client.get("/api/v1/runs")
    assert res.status_code == 401
    assert "API_KEY environment variable is not configured" in res.json()["detail"]


def test_production_allowed_repo_roots_required(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "true")
    monkeypatch.delenv("ALLOWED_REPO_ROOTS", raising=False)

    res = client.post(
        "/api/v1/run",
        json={"issue": "test issue", "repo_path": "."},
        headers={"X-API-Key": "test-api-key"},
    )
    assert res.status_code == 403
    assert "ALLOWED_REPO_ROOTS environment variable must be configured" in res.json()["detail"]



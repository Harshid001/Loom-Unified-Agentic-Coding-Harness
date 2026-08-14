"""Comprehensive HTTP boundary regression matrix for PRD-001 run authorization."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loom.api.dependencies import get_entitlements
from loom.api.routes import iter_routes
from loom.api.run_authorization import _route_action, install_run_authorization
from loom.api.server import _default_org, app
from loom.api.webhooks import get_webhook_engine, reset_webhook_engine
from loom.business.models import Membership, MembershipRole, RunRecord
from loom.business.rbac import Action
from loom.business.usage_ledger import get_usage_ledger, reset_usage_ledger
from loom.db.records_store import get_run_record_store, reset_run_record_store
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.local_process import LocalProcessSandbox
from loom.scim.provisioning import get_scim_provisioner, reset_scim_provisioner

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_api_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "true")
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("LOOM_EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from loom.api.server import _rate_limit_memory_store
    _rate_limit_memory_store.clear()
    reset_usage_ledger()
    get_usage_ledger(str(tmp_path / "ledger"))
    reset_webhook_engine()
    get_webhook_engine(str(tmp_path / "webhooks"))
    reset_run_record_store()
    store = get_run_record_store(str(tmp_path / "records.db"))
    reset_scim_provisioner()
    get_scim_provisioner(str(tmp_path / "scim"))

    # Seed runs for org-a (default) and org-b (foreign) in authoritative record store
    store.record_run(RunRecord(run_id="run_own_123", org_id=_default_org.id, issue_text="own run"))
    store.record_run(RunRecord(run_id="run_foreign_456", org_id="org_foreign_b", issue_text="foreign run"))

    # Seed disk checkpoints & snapshots for run_own_123 and run_foreign_456
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    sandbox = LocalProcessSandbox(str(repo_dir))
    snap_own = sandbox.create_snapshot("snap_own")
    snap_foreign = sandbox.create_snapshot("snap_foreign")

    checkpoint_dir = tmp_path / ".loom" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_own = {
        "run_id": "run_own_123",
        "repo_path": str(repo_dir),
        "issue_description": "own run state",
        "snapshot_id": snap_own,
        "shared_data": {"org_id": _default_org.id},
        "patch_diff": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n",
    }
    (checkpoint_dir / "checkpoint_run_own_123.json").write_text(json.dumps(checkpoint_own), encoding="utf-8")

    checkpoint_foreign = {
        "run_id": "run_foreign_456",
        "repo_path": str(repo_dir),
        "issue_description": "foreign run state",
        "snapshot_id": snap_foreign,
        "shared_data": {"org_id": "org_foreign_b"},
        "patch_diff": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n",
    }
    (checkpoint_dir / "checkpoint_run_foreign_456.json").write_text(json.dumps(checkpoint_foreign), encoding="utf-8")

    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_data = {
        "evidence_bundle": {"run_id": "run_own_123"},
        "chain_integrity": True,
    }
    (evidence_dir / "evidence_run_own_123.json").write_text(json.dumps(evidence_data), encoding="utf-8")

    from loom.api.server import ACTIVE_RUNS
    active_state = OrchestratorState(run_id="run_own_123", repo_path=str(repo_dir), issue_description="own")
    active_state.shared_data["org_id"] = _default_org.id
    ACTIVE_RUNS["run_own_123"] = {
        "events": [{"type": "status_change", "data": {"status": "completed"}}],
        "queues": [],
        "state": active_state,
    }


def test_deterministic_route_action_mapping():
    """Assert all registered run-scoped routes in FastAPI match expected authorization actions."""
    run_routes = []
    for route in iter_routes(app):
        path = getattr(route, "path", "")
        if "{run_id}" in path:
            methods = getattr(route, "methods", set()) or {"GET"}
            for method in methods:
                action = _route_action(method, path)
                run_routes.append((method.upper(), path, action))

    assert len(run_routes) > 0, "No run-scoped routes discovered"
    for method, path, action in run_routes:
        assert action is not None, f"Route {method} {path} is missing run authorization mapping"
        if "rollback" in path:
            assert action is Action.ROLLBACK_RUN
        elif "ci-report" in path:
            assert action is Action.REPORT_CI
        else:
            assert action is Action.VIEW_RUN


def test_double_installation_is_idempotent():
    """Verify that calling install_run_authorization multiple times does not duplicate dependencies."""
    from loom.api import server
    initial_dep_counts = {}
    for route in iter_routes(app):
        path = getattr(route, "path", "")
        if "{run_id}" in path:
            initial_dep_counts[path] = len(getattr(route, "dependencies", []))

    install_run_authorization(server)
    install_run_authorization(server)

    for route in iter_routes(app):
        path = getattr(route, "path", "")
        if "{run_id}" in path:
            assert len(getattr(route, "dependencies", [])) == initial_dep_counts[path]


# -----------------------------------------------------------------------------
# Tenant Isolation Matrix: Own tenant (200/expected) vs Foreign tenant (404)
# -----------------------------------------------------------------------------

def test_tenant_isolation_get_run():
    headers = {"X-API-Key": "test-api-key"}
    own_res = client.get("/api/v1/runs/run_own_123", headers=headers)
    if own_res.status_code != 200:
        print("OWN_RES STATUS:", own_res.status_code, own_res.json())
    assert own_res.status_code == 200
    assert own_res.json()["checkpoint"]["run_id"] == "run_own_123"

    foreign_res = client.get("/api/v1/runs/run_foreign_456", headers=headers)
    assert foreign_res.status_code == 404
    assert foreign_res.json()["detail"] == "Run not found"


def test_tenant_isolation_get_evidence():
    headers = {"X-API-Key": "test-api-key"}
    own_res = client.get("/api/v1/runs/run_own_123/evidence", headers=headers)
    assert own_res.status_code == 200

    foreign_res = client.get("/api/v1/runs/run_foreign_456/evidence", headers=headers)
    assert foreign_res.status_code == 404


def test_tenant_isolation_get_records():
    headers = {"X-API-Key": "test-api-key"}
    own_res = client.get("/api/v1/runs/run_own_123/records", headers=headers)
    assert own_res.status_code == 200
    assert own_res.json()["run"]["run_id"] == "run_own_123"

    foreign_res = client.get("/api/v1/runs/run_foreign_456/records", headers=headers)
    assert foreign_res.status_code == 404


def test_tenant_isolation_post_rollback():
    headers = {"X-API-Key": "test-api-key"}
    own_res = client.post("/api/v1/rollback/run_own_123", headers=headers)
    assert own_res.status_code == 200
    assert own_res.json()["success"] is True

    foreign_res = client.post("/api/v1/rollback/run_foreign_456", headers=headers)
    assert foreign_res.status_code == 404


def test_tenant_isolation_post_ci_report():
    headers = {"X-API-Key": "test-api-key"}
    payload = {"merge_time": time.time() - 10, "ci_failure_detected": True}
    own_res = client.post("/api/v1/runs/run_own_123/ci-report", json=payload, headers=headers)
    assert own_res.status_code == 200

    foreign_res = client.post("/api/v1/runs/run_foreign_456/ci-report", json=payload, headers=headers)
    assert foreign_res.status_code == 404


def test_tenant_isolation_get_stream():
    headers = {"X-API-Key": "test-api-key"}
    with client.stream("GET", "/api/v1/stream/run_own_123", headers=headers) as own_res:
        assert own_res.status_code == 200

    with client.stream("GET", "/api/v1/stream/run_foreign_456", headers=headers) as foreign_res:
        assert foreign_res.status_code == 404


# -----------------------------------------------------------------------------
# Alias Coverage Matrix
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "alias_url",
    [
        "/api/runs/run_foreign_456",
        "/api/runs/run_foreign_456/evidence",
        "/api/runs/run_foreign_456/records",
        "/api/stream/run_foreign_456",
        "/v1/runs/run_foreign_456/rollback",
        "/api/rollback/run_foreign_456",
        "/api/runs/run_foreign_456/ci-report",
    ],
)
def test_alias_routes_reject_cross_tenant(alias_url):
    headers = {"X-API-Key": "test-api-key"}
    if "rollback" in alias_url or "ci-report" in alias_url:
        res = client.post(alias_url, json={"merge_time": 100.0, "ci_failure_detected": False}, headers=headers)
        assert res.status_code == 404
        assert res.json()["detail"] == "Run not found"
    elif "stream" in alias_url:
        with client.stream("GET", alias_url, headers=headers) as res:
            assert res.status_code == 404
    else:
        res = client.get(alias_url, headers=headers)
        assert res.status_code == 404
        assert res.json()["detail"] == "Run not found"


# -----------------------------------------------------------------------------
# Identity & Authentication Matrix
# -----------------------------------------------------------------------------

def test_unauthenticated_request_rejected():
    res = client.get("/api/v1/runs/run_own_123")
    assert res.status_code == 401


def test_forged_org_header_overridden_in_production(monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "production")
    monkeypatch.setenv("API_KEY", "test-api-key")
    headers = {
        "X-API-Key": "test-api-key",
        "X-Org-Id": "forged_org_id",
        "X-User-Id": "forged_user_id",
    }
    res = client.get("/api/v1/runs/run_foreign_456", headers=headers)
    assert res.status_code == 404
    assert res.json()["detail"] == "Run not found"


# -----------------------------------------------------------------------------
# RBAC Role Matrix
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "role,can_view,can_rollback,can_report_ci",
    [
        (MembershipRole.OWNER, True, True, True),
        (MembershipRole.ADMIN, True, True, True),
        (MembershipRole.DEVELOPER, True, False, False),
        (MembershipRole.REVIEWER, True, False, False),
        (MembershipRole.AUDITOR, True, False, False),
    ],
)
def test_rbac_role_matrix(role, can_view, can_rollback, can_report_ci):
    headers = {"X-API-Key": "test-api-key"}
    ent = get_entitlements()
    ent._memberships.clear()
    ent.add_membership(
        Membership(user_id="dev_user", org_id=_default_org.id, role=role)
    )

    # VIEW_RUN check
    res_view = client.get("/api/v1/runs/run_own_123", headers=headers)
    assert res_view.status_code == (200 if can_view else 403)

    # ROLLBACK_RUN check
    res_roll = client.post("/api/v1/rollback/run_own_123", headers=headers)
    assert res_roll.status_code == (200 if can_rollback else 403)

    # REPORT_CI check
    res_ci = client.post(
        "/api/v1/runs/run_own_123/ci-report",
        json={"merge_time": 100.0, "ci_failure_detected": False},
        headers=headers,
    )
    assert res_ci.status_code == (200 if can_report_ci else 403)

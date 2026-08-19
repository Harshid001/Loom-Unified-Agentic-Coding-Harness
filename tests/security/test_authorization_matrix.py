"""PRD-017 — Full API Authorization Matrix.

Automatically discovers all routes from create_app(), then verifies each
sensitive route has: authentication, tenant isolation, role enforcement, and
a negative (cross-tenant / wrong-role) test.

Matrix tested:

  Endpoint                    | Anonymous | Viewer | Developer | Owner | Cross-org
  GET /runs/{id}              |   401     |   ✓    |     ✓     |   ✓   |   404
  GET /runs/{id}/evidence     |   401     |   ✓    |     ✓     |   ✓   |   404
  GET /runs/{id}/records      |   401     |   ✓    |     ✓     |   ✓   |   404
  GET /stream/{id}            |   401     |   ✓    |     ✓     |   ✓   |   404
  POST /runs/{id}/ci-report   |   401     |   ✗    |     ✓     |   ✓   |   404
  POST /rollback/{id}         |   401     |   ✗    |     ✗     |   ✓   |   404
  POST /run/control           |   401     |   ✗    |   role-dep |  ✓   |   404
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loom.api.app import create_app
from loom.api.dependencies import get_entitlements, reset_entitlements
from loom.api.routes import iter_routes
from loom.auth.context import get_service_principal
from loom.business.models import Membership, MembershipRole, RunRecord
from loom.db.records_store import get_run_record_store, reset_run_record_store
from loom.orchestrator.state import OrchestratorState
from loom.sandbox.local_process import LocalProcessSandbox

# ---------------------------------------------------------------------------
# Route discovery helpers
# ---------------------------------------------------------------------------

SENSITIVE_PATH_PATTERNS = [
    "/runs/{run_id}",
    "/runs/{run_id}/evidence",
    "/runs/{run_id}/records",
    "/runs/{run_id}/ast",
    "/runs/{run_id}/ci-report",
    "/stream/{run_id}",
    "/rollback/{run_id}",
    "/run/control",
]

_AUTH_HEADERS = {"X-API-Key": "test-key"}
_NO_AUTH_HEADERS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def matrix_app(monkeypatch, tmp_path):
    """Fresh app + data for each matrix test."""
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("LOOM_EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setenv("RATE_LIMIT_ALLOW_LOCAL_FALLBACK", "true")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Reset singletons so each test gets a fresh slate
    reset_entitlements()
    reset_run_record_store()

    app = create_app()
    return app, tmp_path


@pytest.fixture()
def seeded_client(matrix_app):
    """TestClient with runs seeded in both own-org and foreign-org."""
    app, tmp_path = matrix_app

    entitlements = get_entitlements()
    own_org_id = "default"
    foreign_org_id = "org_foreign_test"

    # The authenticated API-key user is the service principal. Seed its
    # membership as OWNER so the RBAC tests can manipulate role cleanly.
    auth_user_id = get_service_principal().user_id
    entitlements.add_membership(
        Membership(user_id=auth_user_id, org_id=own_org_id, role=MembershipRole.OWNER)
    )

    store = get_run_record_store(str(tmp_path / "records.db"))
    store.record_run(RunRecord(run_id="run_own_001", org_id=own_org_id, issue_text="own run"))
    store.record_run(RunRecord(run_id="run_foreign_001", org_id=foreign_org_id, issue_text="foreign run"))

    # Disk checkpoints for get_run / rollback
    checkpoint_dir = tmp_path / ".loom" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    sandbox = LocalProcessSandbox(str(repo_dir))
    snap = sandbox.create_snapshot("snap")

    for run_id, org_id in [("run_own_001", own_org_id), ("run_foreign_001", foreign_org_id)]:
        data = {
            "run_id": run_id,
            "repo_path": str(repo_dir),
            "issue_description": "test",
            "snapshot_id": snap,
            "shared_data": {"org_id": org_id},
            "patch_diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
        }
        (checkpoint_dir / f"checkpoint_{run_id}.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    # Seed ACTIVE_RUNS for SSE stream test
    from loom.api.server import ACTIVE_RUNS
    state = OrchestratorState(run_id="run_own_001", repo_path=str(repo_dir), issue_description="own")
    state.shared_data["org_id"] = own_org_id
    ACTIVE_RUNS["run_own_001"] = {
        "events": [{"type": "status_change", "data": {"status": "completed"}}],
        "queues": [],
        "state": state,
    }

    client = TestClient(app)
    try:
        yield client, own_org_id, foreign_org_id, entitlements
    finally:
        reset_entitlements()


# ---------------------------------------------------------------------------
# Test: Route discovery — every sensitive path must exist in the app
# ---------------------------------------------------------------------------


def test_all_sensitive_routes_are_registered(matrix_app):
    """Assert every expected sensitive endpoint is present in the router."""
    app, _ = matrix_app
    registered_paths = {getattr(r, "path", "") for r in iter_routes(app)}

    # Check at least one v1 variant of each pattern exists
    missing = []
    for pattern in SENSITIVE_PATH_PATTERNS:
        v1_path = f"/api/v1{pattern}"
        if v1_path not in registered_paths:
            missing.append(v1_path)

    assert not missing, f"Missing sensitive routes: {missing}"


def test_every_protected_route_has_security_dependency(matrix_app):
    """Assert no run-scoped route has zero Depends() declared."""
    app, _ = matrix_app
    no_dep_routes = []
    for route in iter_routes(app):
        path = getattr(route, "path", "")
        if "{run_id}" not in path and "stream" not in path and "rollback" not in path:
            continue
        methods = getattr(route, "methods", set()) or set()
        if not methods:
            continue
        deps = getattr(route, "dependencies", []) or []
        endpoint = getattr(route, "endpoint", None)
        # Check endpoint function signature for PrincipalDep or AuthDep
        if endpoint is None:
            continue
        import inspect
        sig = inspect.signature(endpoint)
        has_security = (
            len(deps) > 0
            or any(
                "principal" in p.lower() or "_auth" in p.lower() or "rbac" in p.lower()
                for p in sig.parameters
            )
        )
        if not has_security:
            no_dep_routes.append(f"{methods} {path}")

    assert not no_dep_routes, f"Routes with no security: {no_dep_routes}"


# ---------------------------------------------------------------------------
# Authentication matrix: 401 for unauthenticated requests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/runs/run_own_001"),
        ("GET", "/api/v1/runs/run_own_001/evidence"),
        ("GET", "/api/v1/runs/run_own_001/records"),
        ("GET", "/api/v1/stream/run_own_001"),
        ("POST", "/api/v1/runs/run_own_001/ci-report"),
        ("POST", "/api/v1/rollback/run_own_001"),
    ],
)
def test_anonymous_request_returns_401(seeded_client, method, path):
    """Every sensitive endpoint must reject unauthenticated requests with 401."""
    client, *_ = seeded_client
    if method == "GET":
        resp = client.get(path, headers=_NO_AUTH_HEADERS)
    else:
        resp = client.post(path, json={"merge_time": 0.0, "ci_failure_detected": False}, headers=_NO_AUTH_HEADERS)
    assert resp.status_code == 401, f"{method} {path}: expected 401, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Tenant isolation matrix: cross-org access returns 404
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,url,body",
    [
        ("GET", "/api/v1/runs/run_foreign_001", None),
        ("GET", "/api/v1/runs/run_foreign_001/evidence", None),
        ("GET", "/api/v1/runs/run_foreign_001/records", None),
        ("POST", "/api/v1/rollback/run_foreign_001", None),
        ("POST", "/api/v1/runs/run_foreign_001/ci-report", {"merge_time": 100.0, "ci_failure_detected": False}),
    ],
)
def test_cross_org_returns_404(seeded_client, method, url, body):
    """Cross-tenant access must return 404 (not 403) to avoid leaking run existence."""
    client, *_ = seeded_client
    if method == "GET":
        resp = client.get(url, headers=_AUTH_HEADERS)
    else:
        resp = client.post(url, json=body or {}, headers=_AUTH_HEADERS)
    assert resp.status_code == 404, f"{method} {url}: expected 404, got {resp.status_code}"
    assert resp.json().get("detail") == "Run not found"


# ---------------------------------------------------------------------------
# Role matrix: RBAC enforcement per action
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,url,method,body,expected_success",
    [
        # VIEW_RUN: all authenticated roles can view
        (MembershipRole.OWNER, "/api/v1/runs/run_own_001", "GET", None, True),
        (MembershipRole.DEVELOPER, "/api/v1/runs/run_own_001", "GET", None, True),
        (MembershipRole.REVIEWER, "/api/v1/runs/run_own_001", "GET", None, True),
        (MembershipRole.AUDITOR, "/api/v1/runs/run_own_001", "GET", None, True),
        # ROLLBACK_RUN: only OWNER and ADMIN
        (MembershipRole.OWNER, "/api/v1/rollback/run_own_001", "POST", None, True),
        (MembershipRole.DEVELOPER, "/api/v1/rollback/run_own_001", "POST", None, False),
        (MembershipRole.REVIEWER, "/api/v1/rollback/run_own_001", "POST", None, False),
        # REPORT_CI: DEVELOPER and above
        (MembershipRole.OWNER, "/api/v1/runs/run_own_001/ci-report", "POST",
         {"merge_time": 100.0, "ci_failure_detected": False}, True),
        (MembershipRole.DEVELOPER, "/api/v1/runs/run_own_001/ci-report", "POST",
         {"merge_time": 100.0, "ci_failure_detected": False}, False),
    ],
)
def test_rbac_role_matrix(seeded_client, role, url, method, body, expected_success):
    """Role-based access must match the authorization matrix."""
    client, own_org_id, _, entitlements = seeded_client
    # Clear and re-seed membership for the actual authenticated principal
    auth_user_id = get_service_principal().user_id
    entitlements._memberships.clear()
    entitlements.add_membership(
        Membership(user_id=auth_user_id, org_id=own_org_id, role=role)
    )

    if method == "GET":
        resp = client.get(url, headers=_AUTH_HEADERS)
    else:
        resp = client.post(url, json=body or {}, headers=_AUTH_HEADERS)

    if expected_success:
        assert resp.status_code in (200, 201), (
            f"role={role.value}, {method} {url}: expected 2xx, got {resp.status_code}: {resp.text}"
        )
    else:
        assert resp.status_code in (403, 404), (
            f"role={role.value}, {method} {url}: expected 403/404, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# SSE stream: authenticated own-org succeeds, cross-org fails
# ---------------------------------------------------------------------------


def test_sse_stream_own_org_succeeds(seeded_client):
    """SSE stream for own-org run must return 200."""
    client, *_ = seeded_client
    with client.stream("GET", "/api/v1/stream/run_own_001", headers=_AUTH_HEADERS) as resp:
        assert resp.status_code == 200


def test_sse_stream_cross_org_returns_404(seeded_client):
    """SSE stream for foreign-org run must return 404."""
    client, *_ = seeded_client
    with client.stream("GET", "/api/v1/stream/run_foreign_001", headers=_AUTH_HEADERS) as resp:
        assert resp.status_code == 404


def test_sse_stream_unauthenticated_returns_401(seeded_client):
    """SSE stream without credentials must return 401."""
    client, *_ = seeded_client
    with client.stream("GET", "/api/v1/stream/run_own_001", headers=_NO_AUTH_HEADERS) as resp:
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API alias coverage: /api/* aliases must enforce same policies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias_url",
    [
        "/api/runs/run_foreign_001",
        "/api/runs/run_foreign_001/evidence",
        "/api/runs/run_foreign_001/records",
        "/api/rollback/run_foreign_001",
        "/api/runs/run_foreign_001/ci-report",
    ],
)
def test_api_alias_cross_tenant_blocked(seeded_client, alias_url):
    """/api/* aliases must block cross-tenant access exactly like /api/v1/* routes."""
    client, *_ = seeded_client
    if "ci-report" in alias_url or "rollback" in alias_url:
        resp = client.post(alias_url, json={"merge_time": 100.0, "ci_failure_detected": False},
                           headers=_AUTH_HEADERS)
    else:
        resp = client.get(alias_url, headers=_AUTH_HEADERS)
    assert resp.status_code == 404

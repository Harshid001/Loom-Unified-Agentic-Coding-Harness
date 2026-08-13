from __future__ import annotations

import pytest
from fastapi import HTTPException

from loom.api.run_authorization import _route_action, require_run_access
from loom.auth.context import AuthenticatedPrincipal, begin_request_auth_context, clear_principal, set_principal
from loom.business.models import MembershipRole, RunRecord
from loom.business.rbac import Action


class _FakeEntitlements:
    def __init__(self, role: MembershipRole):
        self.role = role

    def get_role(self, org_id: str, user_id: str) -> MembershipRole:
        return self.role


class _FakeStore:
    def __init__(self, runs: dict[str, RunRecord]):
        self.runs = runs

    def get_run(self, run_id: str):
        return self.runs.get(run_id)


class _FakeModule:
    def __init__(self, role: MembershipRole, store: _FakeStore):
        self._entitlements = _FakeEntitlements(role)
        self._store = store


def _set_principal(org_id: str = "org-a", user_id: str = "user-a") -> None:
    begin_request_auth_context()
    set_principal(AuthenticatedPrincipal(user_id=user_id, org_id=org_id, auth_method="test"))


def _run(org_id: str = "org-a") -> RunRecord:
    return RunRecord(run_id="run-1", org_id=org_id, issue_text="test")


def test_route_action_matrix() -> None:
    assert _route_action("GET", "/runs/{run_id}") is Action.VIEW_RUN
    assert _route_action("GET", "/runs/{run_id}/evidence") is Action.VIEW_RUN
    assert _route_action("GET", "/runs/{run_id}/records") is Action.VIEW_RUN
    assert _route_action("GET", "/stream/{run_id}") is Action.VIEW_RUN
    assert _route_action("POST", "/rollback/{run_id}") is Action.ROLLBACK_RUN
    assert _route_action("POST", "/runs/{run_id}/ci-report") is Action.REPORT_CI


def test_org_a_can_access_own_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_principal("org-a", "user-a")
    store = _FakeStore({"run-a": _run("org-a")})
    monkeypatch.setattr("loom.api.run_authorization.get_run_record_store", lambda: store)

    run = require_run_access("run-a", Action.VIEW_RUN, module=_FakeModule(MembershipRole.DEVELOPER, store))
    assert run.org_id == "org-a"
    clear_principal()


def test_org_a_cannot_access_org_b_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_principal("org-a", "user-a")
    store = _FakeStore({"run-b": _run("org-b")})
    monkeypatch.setattr("loom.api.run_authorization.get_run_record_store", lambda: store)

    with pytest.raises(HTTPException) as exc:
        require_run_access("run-b", Action.VIEW_RUN, module=_FakeModule(MembershipRole.DEVELOPER, store))
    assert exc.value.status_code == 404
    clear_principal()


@pytest.mark.parametrize("action", [Action.VIEW_RUN, Action.ROLLBACK_RUN, Action.REPORT_CI])
def test_org_a_cannot_access_org_b_for_any_run_action(action: Action, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_principal("org-a", "user-a")
    store = _FakeStore({"run-b": _run("org-b")})
    monkeypatch.setattr("loom.api.run_authorization.get_run_record_store", lambda: store)

    with pytest.raises(HTTPException) as exc:
        require_run_access("run-b", action, module=_FakeModule(MembershipRole.OWNER, store))
    assert exc.value.status_code == 404
    clear_principal()


def test_unauthenticated_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_principal()
    store = _FakeStore({"run-a": _run("org-a")})
    monkeypatch.setattr("loom.api.run_authorization.get_run_record_store", lambda: store)

    with pytest.raises(HTTPException) as exc:
        require_run_access("run-a", Action.VIEW_RUN, module=_FakeModule(MembershipRole.OWNER, store))
    assert exc.value.status_code == 401


def test_insufficient_role_is_403(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_principal("org-a", "user-a")
    store = _FakeStore({"run-a": _run("org-a")})
    monkeypatch.setattr("loom.api.run_authorization.get_run_record_store", lambda: store)

    with pytest.raises(HTTPException) as exc:
        require_run_access("run-a", Action.ROLLBACK_RUN, module=_FakeModule(MembershipRole.DEVELOPER, store))
    assert exc.value.status_code == 403
    clear_principal()

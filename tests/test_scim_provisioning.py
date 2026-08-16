import pytest
from fastapi import HTTPException

from loom.auth.api_tokens import ApiTokenStore
from loom.business.audit_log import AuditLogger
from loom.business.entitlements import EntitlementService
from loom.business.models import AuditAction, MembershipRole
from loom.scim.provisioning import (
    DEPROVISION_SLA_SECONDS,
    SCIM_GROUP_SCHEMA,
    SCIM_USER_SCHEMA,
    ScimProvisioner,
)


@pytest.fixture(autouse=True)
def _isolate_token_store_mode(monkeypatch):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture
def provisioner(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIM_TOKEN", "test-scim-token")
    audit = AuditLogger(storage_dir=str(tmp_path / "audit"))
    monkeypatch.setattr("loom.scim.provisioning.get_audit_logger", lambda: audit)
    entitlements = EntitlementService()
    tokens = ApiTokenStore(storage_dir=str(tmp_path / "tokens"))
    monkeypatch.setattr("loom.scim.provisioning.get_api_token_store", lambda: tokens)
    provisioner = ScimProvisioner(storage_dir=str(tmp_path / "scim"), entitlements=entitlements)
    provisioner.audit = audit
    provisioner.token_store = tokens
    return provisioner


def _user_payload(user_name="alice", **overrides):
    payload = {
        SCIM_USER_SCHEMA: {
            "userName": user_name,
            "displayName": "Alice A.",
            "emails": [{"value": "alice@example.com", "primary": True}],
            "active": True,
        }
    }
    payload[SCIM_USER_SCHEMA].update(overrides)
    return payload


class TestUsers:
    def test_create_and_get_user(self, provisioner):
        user = provisioner.create_user("org_1", _user_payload())
        assert user.user_name == "alice"
        assert provisioner.get_user(user.id).harness_user_id == user.harness_user_id
        assert provisioner.find_by_user_name("alice", "org_1") is not None

    def test_duplicate_username_raises_conflict(self, provisioner):
        provisioner.create_user("org_1", _user_payload())
        with pytest.raises(HTTPException) as exc:
            provisioner.create_user("org_1", _user_payload())
        assert exc.value.status_code == 409

    def test_missing_username_raises_bad_request(self, provisioner):
        with pytest.raises(HTTPException) as exc:
            provisioner.create_user("org_1", {SCIM_USER_SCHEMA: {"active": True}})
        assert exc.value.status_code == 400

    def test_create_records_invite_audit(self, provisioner):
        provisioner.create_user("org_1", _user_payload())
        entries = provisioner.audit.get_entries(org_id="org_1", action=AuditAction.MEMBER_INVITED)
        assert len(entries) == 1

    def test_update_unknown_user_raises_not_found(self, provisioner):
        with pytest.raises(HTTPException) as exc:
            provisioner.update_user("u_missing", _user_payload())
        assert exc.value.status_code == 404


class TestGroups:
    def test_group_creates_memberships(self, provisioner):
        alice = provisioner.create_user("org_1", _user_payload("alice"))
        bob = provisioner.create_user("org_1", _user_payload("bob"))
        group = provisioner.create_group(
            "org_1",
            {SCIM_GROUP_SCHEMA: {"displayName": "eng", "members": [{"value": alice.id}, {"value": bob.id}]}},
        )
        assert set(group.members) == {alice.harness_user_id, bob.harness_user_id}
        assert provisioner.entitlements.get_membership("org_1", alice.harness_user_id).role == MembershipRole.DEVELOPER

    def test_group_update_replaces_members(self, provisioner):
        alice = provisioner.create_user("org_1", _user_payload("alice"))
        bob = provisioner.create_user("org_1", _user_payload("bob"))
        group = provisioner.create_group(
            "org_1",
            {SCIM_GROUP_SCHEMA: {"displayName": "eng", "members": [{"value": alice.id}]}},
        )
        provisioner.update_group(
            group.id,
            {SCIM_GROUP_SCHEMA: {"displayName": "eng", "members": [{"value": bob.id}]}},
        )
        assert group.members == [bob.harness_user_id]
        assert provisioner.entitlements.get_membership("org_1", bob.harness_user_id) is not None
        assert provisioner.entitlements.get_membership("org_1", alice.harness_user_id) is None

    def test_delete_group(self, provisioner):
        group = provisioner.create_group("org_1", {SCIM_GROUP_SCHEMA: {"displayName": "eng"}})
        provisioner.delete_group(group.id)
        assert provisioner._groups.get(group.id) is None


class TestDeprovisioning:
    def test_active_false_revokes_tokens_and_removes_memberships(self, provisioner):
        user = provisioner.create_user("org_1", _user_payload("carol"))
        _, token = provisioner.token_store.issue(user.harness_user_id, org_id="org_1")

        group = provisioner.create_group(
            "org_1",
            {SCIM_GROUP_SCHEMA: {"displayName": "eng", "members": [{"value": user.id}]}},
        )
        assert len(group.members) == 1

        provisioner.update_user(user.id, _user_payload("carol", active=False))

        assert provisioner.token_store.verify(token) is None
        assert provisioner.entitlements.get_membership("org_1", user.harness_user_id) is None
        audit = provisioner.audit
        entries = audit.get_entries(org_id="org_1", action=AuditAction.MEMBER_DEPROVISIONED)
        assert len(entries) == 1
        assert entries[0].metadata["tokens_revoked"] == 1

    def test_delete_user_deprovisions(self, provisioner):
        user = provisioner.create_user("org_1", _user_payload("dave"))
        provisioner.delete_user(user.id)
        assert len(provisioner.pending_deprovision_tasks()) == 1

    def test_sweep_finalizes_only_past_deadline(self, provisioner):
        user = provisioner.create_user("org_1", _user_payload("erin"))
        provisioner.delete_user(user.id)
        task = provisioner.pending_deprovision_tasks()[0]

        result = provisioner.sweep_deprovisions(now=task.enqueued_at + 1)
        assert result["finalized"] == []
        assert result["still_pending"] == 1

        result = provisioner.sweep_deprovisions(now=task.sla_deadline + 1)
        assert result["finalized"] == [task.id]
        assert result["still_pending"] == 0

    def test_deprovision_task_has_five_minute_sla(self, provisioner):
        user = provisioner.create_user("org_1", _user_payload("frank"))
        provisioner.delete_user(user.id)
        task = provisioner.pending_deprovision_tasks()[0]
        assert task.sla_deadline - task.enqueued_at == pytest.approx(DEPROVISION_SLA_SECONDS)

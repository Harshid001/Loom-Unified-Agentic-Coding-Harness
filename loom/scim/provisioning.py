"""SCIM 2.0 provisioning server (spec §4.2).

Implements the SCIM 2.0 User and Group resources against the entitlement
membership model. Deprovisioning (PATCH active=false or DELETE) revokes all
active API tokens for the user, removes every membership, writes
`member.deprovisioned` audit entries, and enqueues a deprovision record used
by the 5-minute SLA sweeper.
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from loom.auth.api_tokens import get_api_token_store
from loom.business.audit_log import get_audit_logger
from loom.business.entitlements import EntitlementService
from loom.business.models import AuditAction, Membership, MembershipRole

logger = logging.getLogger("loom.scim.provisioning")

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_RESPONSE_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"

DEPROVISION_SLA_SECONDS = 5 * 60


class ScimUser(BaseModel):
    id: str = Field(default_factory=lambda: f"u_{uuid.uuid4().hex[:12]}")
    org_id: str = "default"
    external_id: str = ""
    user_name: str
    display_name: str = ""
    emails: List[str] = Field(default_factory=list)
    active: bool = True
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @property
    def harness_user_id(self) -> str:
        return self.external_id or f"scim_{self.user_name}"


class ScimGroup(BaseModel):
    id: str = Field(default_factory=lambda: f"g_{uuid.uuid4().hex[:12]}")
    org_id: str = "default"
    display_name: str
    members: List[str] = Field(default_factory=list)  # harness user ids
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class DeprovisionTask(BaseModel):
    id: str = Field(default_factory=lambda: f"dep_{uuid.uuid4().hex[:16]}")
    user_id: str
    scim_user_id: str
    org_id: str
    reason: str = "scim"
    enqueued_at: float = Field(default_factory=time.time)
    sla_deadline: float = Field(default_factory=lambda: time.time() + DEPROVISION_SLA_SECONDS)
    finalized_at: Optional[float] = None
    status: str = "pending"  # pending | finalized


class ScimProvisioner:
    """SCIM resource store + deprovisioning orchestration (JSONL persistence)."""

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        entitlements: Optional[EntitlementService] = None,
    ):
        if storage_dir is None:
            storage_dir = str(Path.home() / ".loom" / "scim")
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.entitlements = entitlements if entitlements is not None else EntitlementService()
        self._users: Dict[str, ScimUser] = {}
        self._groups: Dict[str, ScimGroup] = {}
        self._deprovisions: Dict[str, DeprovisionTask] = {}
        self._load()

    def _users_file(self) -> Path:
        return self._dir / "users.jsonl"

    def _groups_file(self) -> Path:
        return self._dir / "groups.jsonl"

    def _depro_file(self) -> Path:
        return self._dir / "deprovisions.jsonl"

    def _load(self) -> None:
        for path, target in (
            (self._users_file(), self._users),
            (self._groups_file(), self._groups),
            (self._depro_file(), self._deprovisions),
        ):
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    if target is self._users:
                        item: Any = ScimUser(**json.loads(line))
                    elif target is self._groups:
                        item = ScimGroup(**json.loads(line))
                    else:
                        item = DeprovisionTask(**json.loads(line))
                    target[item.id] = item
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

    def _persist(self) -> None:
        try:
            self._users_file().write_text(
                "\n".join(json.dumps(u.model_dump(), default=str) for u in self._users.values()) + "\n",
                encoding="utf-8",
            )
            self._groups_file().write_text(
                "\n".join(json.dumps(g.model_dump(), default=str) for g in self._groups.values()) + "\n",
                encoding="utf-8",
            )
            self._depro_file().write_text(
                "\n".join(json.dumps(d.model_dump(), default=str) for d in self._deprovisions.values()) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to persist SCIM state: %s", exc)

    def create_user(self, org_id: str, payload: Dict[str, Any]) -> ScimUser:
        attrs = payload.get(SCIM_USER_SCHEMA, payload)
        user_name = attrs.get("userName") or attrs.get("user_name")
        if not user_name:
            raise HTTPException(status_code=400, detail="userName is required")
        duplicate = self.find_by_user_name(user_name, org_id)
        if duplicate:
            raise HTTPException(status_code=409, detail=f"User {user_name} already exists")
        emails = [e.get("value") for e in attrs.get("emails", []) if isinstance(e, dict) and e.get("value")]
        user = ScimUser(
            org_id=org_id,
            external_id=str(attrs.get("externalId") or ""),
            user_name=user_name,
            display_name=str(attrs.get("displayName") or user_name),
            emails=[str(e) for e in emails],
            active=bool(attrs.get("active", True)),
        )
        self._users[user.id] = user
        self._persist()
        get_audit_logger().record(
            org_id=org_id,
            action=AuditAction.MEMBER_INVITED,
            actor_id="scim",
            target=user.harness_user_id,
            metadata={"scim_user_id": user.id, "provisioned": True},
        )
        return user

    def find_by_user_name(self, user_name: str, org_id: str) -> Optional[ScimUser]:
        for user in self._users.values():
            if user.user_name == user_name and user.org_id == org_id:
                return user
        return None

    def get_user(self, scim_user_id: str) -> Optional[ScimUser]:
        return self._users.get(scim_user_id)

    def update_user(self, scim_user_id: str, payload: Dict[str, Any]) -> ScimUser:
        user = self.get_user(scim_user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        attrs = payload.get(SCIM_USER_SCHEMA, payload)
        if "displayName" in attrs:
            user.display_name = str(attrs["displayName"])
        if "emails" in attrs:
            user.emails = [str(e.get("value")) for e in attrs["emails"] if isinstance(e, dict) and e.get("value")]
        if "active" in attrs:
            user.active = bool(attrs["active"])
        user.updated_at = time.time()
        self._users[user.id] = user
        self._persist()
        if not user.active:
            self.deprovision_user(user.org_id, user, reason="active:false")
        return user

    def delete_user(self, scim_user_id: str) -> None:
        user = self.get_user(scim_user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user.active = False
        self.deprovision_user(user.org_id, user, reason="delete")

    def deprovision_user(self, org_id: str, user: ScimUser, reason: str) -> None:
        """Revoke tokens, remove memberships, audit, and enqueue the SLA task (spec §4.2)."""
        revoked = get_api_token_store().revoke_all_for_user(user.harness_user_id)
        removed = []
        for member_org_id, members in list(self.entitlements.memberships_dict().items()):
            if user.harness_user_id in members:
                self.entitlements.remove_membership(member_org_id, user.harness_user_id)
                removed.append(member_org_id)

        get_audit_logger().record(
            org_id=org_id,
            action=AuditAction.MEMBER_DEPROVISIONED,
            actor_id="scim",
            target=user.harness_user_id,
            metadata={
                "reason": reason,
                "tokens_revoked": revoked,
                "memberships_removed": removed,
                "sla_deadline": time.time() + DEPROVISION_SLA_SECONDS,
            },
        )
        task = DeprovisionTask(
            user_id=user.harness_user_id,
            scim_user_id=user.id,
            org_id=org_id,
            reason=reason,
        )
        self._deprovisions[task.id] = task
        self._persist()

    def create_group(self, org_id: str, payload: Dict[str, Any]) -> ScimGroup:
        attrs = payload.get(SCIM_GROUP_SCHEMA, payload)
        display_name = attrs.get("displayName")
        if not display_name:
            raise HTTPException(status_code=400, detail="displayName is required")
        group = ScimGroup(org_id=org_id, display_name=str(display_name))
        self._sync_group_members(group, attrs.get("members", []))
        self._groups[group.id] = group
        self._persist()
        return group

    def update_group(self, group_id: str, payload: Dict[str, Any]) -> ScimGroup:
        group = self._groups.get(group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        attrs = payload.get(SCIM_GROUP_SCHEMA, payload)
        if "displayName" in attrs:
            group.display_name = str(attrs["displayName"])
        if "members" in attrs:
            self._sync_group_members(group, attrs["members"])
        group.updated_at = time.time()
        self._persist()
        return group

    def delete_group(self, group_id: str) -> None:
        group = self._groups.pop(group_id, None)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        self._persist()

    def _sync_group_members(self, group: ScimGroup, members: List[Any]) -> None:
        """Map member refs (SCIM user ids) → memberships (developer role).

        Full replacement semantics: members removed from the group also lose
        their SCIM-managed membership.
        """
        prev_members = set(group.members)
        group.members = []
        for m in members:
            if not isinstance(m, dict) or not m.get("value"):
                continue
            scim_user = self.get_user(str(m["value"]))
            if scim_user is None:
                continue
            user_id = scim_user.harness_user_id
            group.members.append(user_id)
            if self.entitlements.get_membership(group.org_id, user_id) is not None:
                continue
            self.entitlements.add_membership(
                Membership(user_id=user_id, org_id=group.org_id, role=MembershipRole.DEVELOPER)
            )
        for removed in prev_members - set(group.members):
            self.entitlements.remove_membership(group.org_id, removed)

    def pending_deprovision_tasks(self) -> List[DeprovisionTask]:
        return [t for t in self._deprovisions.values() if t.status == "pending"]

    def sweep_deprovisions(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Finalize deprovision tasks past their 5-minute SLA deadline (idempotent)."""
        now = now if now is not None else time.time()
        finalized: List[str] = []
        missed = 0
        for task in list(self._deprovisions.values()):
            if task.status != "pending":
                continue
            if now >= task.sla_deadline:
                task.status = "finalized"
                task.finalized_at = now
                finalized.append(task.id)
            else:
                missed += 1
        if finalized:
            self._persist()
        return {"finalized": finalized, "still_pending": missed, "checked_at": now}


_scim_provisioner_instance: Optional[ScimProvisioner] = None


def get_scim_provisioner(storage_dir: Optional[str] = None) -> ScimProvisioner:
    global _scim_provisioner_instance
    if _scim_provisioner_instance is None:
        _scim_provisioner_instance = ScimProvisioner(storage_dir=storage_dir)
    return _scim_provisioner_instance


def reset_scim_provisioner() -> None:
    global _scim_provisioner_instance
    _scim_provisioner_instance = None


def _require_scim_token(x_scim_token: Optional[str] = Header(None, alias="Authorization")) -> str:
    import hmac
    import os

    required = os.getenv("SCIM_TOKEN")
    if not required:
        raise HTTPException(status_code=503, detail="SCIM not enabled: SCIM_TOKEN not configured")
    if not x_scim_token or not hmac.compare_digest(x_scim_token, f"Bearer {required}"):
        raise HTTPException(status_code=401, detail="Invalid SCIM bearer token")
    return x_scim_token


def _user_meta(user: ScimUser) -> Dict[str, str]:
    return {
        "resourceType": "User",
        "location": f"/scim/v2/Users/{user.id}",
    }


def _user_response(user: ScimUser) -> Dict[str, Any]:
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": user.id,
        "externalId": user.external_id,
        "userName": user.user_name,
        "displayName": user.display_name,
        "emails": [{"value": e, "primary": i == 0} for i, e in enumerate(user.emails)],
        "active": user.active,
        "meta": _user_meta(user),
    }


def _group_response(group: ScimGroup) -> Dict[str, Any]:
    return {
        "schemas": [SCIM_GROUP_SCHEMA],
        "id": group.id,
        "displayName": group.display_name,
        "members": [{"value": m, "type": "User"} for m in group.members],
        "meta": {
            "resourceType": "Group",
            "location": f"/scim/v2/Groups/{group.id}",
        },
    }


scim_router = APIRouter(prefix="/scim/v2", tags=["scim"], dependencies=[Depends(_require_scim_token)])


@scim_router.get("/Users")
def list_users(provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    users = [_user_response(u) for u in provisioner._users.values()]
    return {
        "schemas": [SCIM_LIST_RESPONSE_SCHEMA],
        "totalResults": len(users),
        "Resources": users,
    }


@scim_router.post("/Users")
def create_user(payload: Dict[str, Any], provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    org_id = str(payload.get("orgId") or "default")
    user = provisioner.create_user(org_id, payload)
    return _user_response(user)


@scim_router.get("/Users/{user_id}")
def get_user(user_id: str, provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    user = provisioner.get_user(user_id)
    if user is None:
        raise _scim_not_found("User")
    return _user_response(user)


@scim_router.put("/Users/{user_id}")
@scim_router.patch("/Users/{user_id}")
def update_user(user_id: str, payload: Dict[str, Any], provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    user = provisioner.update_user(user_id, payload)
    return _user_response(user)


@scim_router.delete("/Users/{user_id}")
def delete_user(user_id: str, provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    provisioner.delete_user(user_id)
    return Response(status_code=204)


@scim_router.post("/Groups")
def create_group(payload: Dict[str, Any], provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    org_id = str(payload.get("orgId") or "default")
    return _group_response(provisioner.create_group(org_id, payload))


@scim_router.get("/Groups")
def list_groups(provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    groups = [_group_response(g) for g in provisioner._groups.values()]
    return {
        "schemas": [SCIM_LIST_RESPONSE_SCHEMA],
        "totalResults": len(groups),
        "Resources": groups,
    }


@scim_router.get("/Groups/{group_id}")
def get_group(group_id: str, provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    group = provisioner._groups.get(group_id)
    if group is None:
        raise _scim_not_found("Group")
    return _group_response(group)


@scim_router.put("/Groups/{group_id}")
@scim_router.patch("/Groups/{group_id}")
def update_group(group_id: str, payload: Dict[str, Any], provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    return _group_response(provisioner.update_group(group_id, payload))


@scim_router.delete("/Groups/{group_id}")
def delete_group(group_id: str, provisioner: ScimProvisioner = Depends(get_scim_provisioner)):
    provisioner.delete_group(group_id)
    return Response(status_code=204)


def _scim_not_found(resource_type: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"{resource_type} not found",
        headers={"content-type": "application/scim+json"},
    )

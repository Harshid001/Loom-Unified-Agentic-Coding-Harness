import os
from enum import Enum
from typing import Dict, Set

from fastapi import HTTPException
from fastapi import status as http_status

from loom.auth.context import get_effective_principal
from loom.business.models import MembershipRole


class Action(str, Enum):
    TRIGGER_RUN = "trigger_run"
    APPROVE_AUTO_MERGE_OVERRIDE = "approve_auto_merge_override"
    MODIFY_ENTITLEMENTS = "modify_entitlements"
    MODIFY_QUOTA_POLICY = "modify_quota_policy"
    CONFIGURE_SANDBOX = "configure_sandbox"
    EXPORT_EVIDENCE = "export_evidence"
    EXPORT_AUDIT_LOG = "export_audit_log"
    MANAGE_SSO_SCIM = "manage_sso_scim"
    INVITE_MEMBERS = "invite_members"
    REMOVE_MEMBERS = "remove_members"
    VIEW_BILLING = "view_billing"
    MODIFY_BILLING = "modify_billing"


RBAC_MATRIX: Dict[MembershipRole, Set[Action]] = {
    MembershipRole.OWNER: {
        Action.TRIGGER_RUN,
        Action.APPROVE_AUTO_MERGE_OVERRIDE,
        Action.MODIFY_ENTITLEMENTS,
        Action.MODIFY_QUOTA_POLICY,
        Action.CONFIGURE_SANDBOX,
        Action.EXPORT_EVIDENCE,
        Action.EXPORT_AUDIT_LOG,
        Action.MANAGE_SSO_SCIM,
        Action.INVITE_MEMBERS,
        Action.REMOVE_MEMBERS,
        Action.VIEW_BILLING,
        Action.MODIFY_BILLING,
    },
    MembershipRole.ADMIN: {
        Action.TRIGGER_RUN,
        Action.APPROVE_AUTO_MERGE_OVERRIDE,
        Action.MODIFY_ENTITLEMENTS,
        Action.MODIFY_QUOTA_POLICY,
        Action.CONFIGURE_SANDBOX,
        Action.EXPORT_EVIDENCE,
        Action.EXPORT_AUDIT_LOG,
        Action.MANAGE_SSO_SCIM,
        Action.INVITE_MEMBERS,
        Action.REMOVE_MEMBERS,
    },
    MembershipRole.DEVELOPER: {Action.TRIGGER_RUN},
    MembershipRole.REVIEWER: {Action.APPROVE_AUTO_MERGE_OVERRIDE},
    MembershipRole.BILLING_ADMIN: {
        Action.VIEW_BILLING,
        Action.MODIFY_BILLING,
        Action.MODIFY_QUOTA_POLICY,
    },
    MembershipRole.AUDITOR: {Action.EXPORT_EVIDENCE, Action.EXPORT_AUDIT_LOG},
}


class RBACEnforcer:
    def __init__(self, role: MembershipRole):
        self._role = role
        self._permissions = RBAC_MATRIX.get(role, set())

    def can(self, action: Action) -> bool:
        return action in self._permissions

    def authorize(self, action: Action, resource: str = "") -> None:
        if not self.can(action):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{self._role.value}' lacks permission '{action.value}'"
                    + (f" on '{resource}'" if resource else "")
                ),
            )

        if _secure_runtime() and resource.startswith("org:"):
            resource_org = resource.split(":", 1)[1]
            principal = get_effective_principal()
            if resource_org != principal.org_id:
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="Organization scope is not authorized for the authenticated credential",
                )

    @property
    def role(self) -> MembershipRole:
        return self._role

    @property
    def permissions(self) -> Set[Action]:
        return set(self._permissions)


def _secure_runtime() -> bool:
    return not (
        os.getenv("LOOM_ENV", "production").lower() == "development"
        and os.getenv("DEV_MODE", "").lower() in {"1", "true", "yes", "on"}
    )


def require_permission(user_id: str, org_id: str, role: str | MembershipRole, permission: str) -> bool:
    """Authorize a legacy permission request while binding identity to the verified credential."""
    principal = get_effective_principal()
    if _secure_runtime() and (user_id != principal.user_id or org_id != principal.org_id):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Identity is not authorized for the authenticated credential",
        )

    try:
        role_value = role if isinstance(role, MembershipRole) else MembershipRole(str(role).lower())
    except ValueError as exc:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Invalid membership role") from exc

    if permission == "runs:read":
        return True

    action_map = {
        "runs:write": Action.TRIGGER_RUN,
        "runs:trigger": Action.TRIGGER_RUN,
        "entitlements:modify": Action.MODIFY_ENTITLEMENTS,
        "quota:modify": Action.MODIFY_QUOTA_POLICY,
        "sandbox:configure": Action.CONFIGURE_SANDBOX,
        "evidence:export": Action.EXPORT_EVIDENCE,
        "audit:export": Action.EXPORT_AUDIT_LOG,
        "billing:read": Action.VIEW_BILLING,
        "billing:write": Action.MODIFY_BILLING,
    }
    action = action_map.get(permission)
    if action is None or action not in RBAC_MATRIX.get(role_value, set()):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail=f"Permission denied: {permission}")
    return True

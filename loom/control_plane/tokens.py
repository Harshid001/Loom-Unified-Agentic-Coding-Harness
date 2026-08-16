"""Privileged API-token control-plane operations.

These functions are intentionally separate from the data-plane API. Production callers
must enter through an authenticated control-plane boundary and cannot rely on client-
supplied organization identifiers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loom.auth.api_tokens import ApiTokenRecord, TokenAdministrationDisabled, get_api_token_store


@dataclass(frozen=True)
class TokenPrincipal:
    user_id: str
    org_id: str
    is_admin: bool


def _check_admin(principal: TokenPrincipal) -> None:
    if not principal.is_admin:
        raise PermissionError("token administration requires an administrative principal")


def issue(principal: TokenPrincipal, user_id: Optional[str] = None, label: str = "control-plane") -> tuple[ApiTokenRecord, str]:
    _check_admin(principal)
    target_user = user_id or principal.user_id
    try:
        return get_api_token_store().issue(target_user, principal.org_id, label)
    except TokenAdministrationDisabled as exc:
        raise PermissionError("production token administration is disabled until its control-plane is enabled") from exc


def revoke(principal: TokenPrincipal, token_id: str) -> None:
    _check_admin(principal)
    store = get_api_token_store()
    record = store.get(token_id)
    if record is None or record.org_id != principal.org_id:
        raise LookupError("token not found")
    store.revoke(token_id)

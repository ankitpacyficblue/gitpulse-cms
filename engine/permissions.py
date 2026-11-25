"""
GitPulse CMS - Roles and permissions.

Roles are per account membership. Permissions are strings derived from the role.
Routes are checked against a table; an unlisted route is denied (see routes_api).
"""

from typing import Dict, FrozenSet, Optional

ROLES = ("owner", "admin", "agent", "viewer")

_VIEWER = frozenset({"crm.read", "content.read"})
_AGENT = _VIEWER | {"crm.write", "content.write"}
_ADMIN = _AGENT | {
    "crm.delete", "wa.config", "automations.manage", "broadcasts.run",
    "content.publish", "users.manage", "audit.read", "ai.manage",
}
_OWNER = _ADMIN | {"account.manage", "owners.manage"}

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "viewer": frozenset(_VIEWER),
    "agent": frozenset(_AGENT),
    "admin": frozenset(_ADMIN),
    "owner": frozenset(_OWNER),
}


def permissions_for(role: Optional[str]) -> FrozenSet[str]:
    return ROLE_PERMISSIONS.get(role or "", frozenset())


def has_permission(role: Optional[str], permission: str) -> bool:
    return permission in permissions_for(role)


def can_assign_role(actor_role: Optional[str], target_role: str) -> bool:
    """Admins may manage non-owner roles. Only owners may grant or change the owner role."""
    if target_role not in ROLES:
        return False
    if target_role == "owner":
        return has_permission(actor_role, "owners.manage")
    return has_permission(actor_role, "users.manage")

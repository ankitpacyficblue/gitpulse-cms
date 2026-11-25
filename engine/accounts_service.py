"""
GitPulse CMS - Account and user management rules.

Business rules live here, not in the route handlers, so they are testable and
cannot be skipped by a new route:
- only a platform admin creates accounts;
- admins manage non-owner roles, only owners touch the owner role;
- an account always keeps at least one owner;
- users are created inside the caller's account, never elsewhere.
"""

from typing import Any, Dict, Optional

import crm_store as cs
from engine import auth
from engine.permissions import ROLES, can_assign_role, has_permission


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(message or code)
        self.status, self.code, self.message = status, code, message or code


def create_account_with_owner(actor: Dict[str, Any], name: str, owner_username: str = "",
                              owner_email: str = "") -> Dict[str, Any]:
    """Platform admin only. Creates an empty account and its first owner.
    If owner_username names an existing user they become owner; otherwise a login is created
    with a temporary password returned once. With no owner given, the platform admin owns it."""
    if not actor.get("is_platform_admin"):
        raise ServiceError(403, "forbidden", "Only a platform admin can create accounts.")
    if not (name or "").strip():
        raise ServiceError(400, "name_required", "Account name is required.")
    out: Dict[str, Any] = {}
    owner_id = actor["id"]
    uname = (owner_username or "").strip().lower()
    if uname:
        existing = auth.get_user_by_username(uname)
        if existing:
            owner_id = existing["id"]
        else:
            temp = auth.generate_temporary_password()
            owner_id = auth.create_user(uname, temp, email=owner_email, temporary=True)
            out["owner_temporary_password"] = temp
    acct = cs.create_account(name, owner_email)
    cs.add_membership(acct["id"], owner_id, "owner")
    out.update({"id": acct["id"], "name": acct["name"], "owner_user_id": owner_id})
    return out


def add_user(account_id: str, actor_role: str, username: str, role: str, email: str = "") -> Dict[str, Any]:
    if role not in ROLES:
        raise ServiceError(400, "invalid_role", "Role must be one of: " + ", ".join(ROLES))
    if not can_assign_role(actor_role, role):
        raise ServiceError(403, "forbidden", "You cannot grant this role.")
    uname = (username or "").strip().lower()
    if not uname:
        raise ServiceError(400, "username_required", "A username is required.")
    out: Dict[str, Any] = {}
    user = auth.get_user_by_username(uname)
    if user:
        if cs.get_membership_role(account_id, user["id"]):
            raise ServiceError(409, "already_member", "This user is already in the account.")
        user_id = user["id"]
    else:
        temp = auth.generate_temporary_password()
        user_id = auth.create_user(uname, temp, email=email, temporary=True)
        out["temporary_password"] = temp
    cs.add_membership(account_id, user_id, role)
    out.update({"user_id": user_id, "username": uname, "role": role})
    return out


def _target_role(account_id: str, user_id: int) -> str:
    role = cs.get_membership_role(account_id, user_id)
    if not role:
        raise ServiceError(404, "not_found", "No such member in this account.")
    return role


def change_role(account_id: str, actor_role: str, target_user_id: int, new_role: str) -> None:
    if new_role not in ROLES:
        raise ServiceError(400, "invalid_role", "Role must be one of: " + ", ".join(ROLES))
    current = _target_role(account_id, target_user_id)
    if not (can_assign_role(actor_role, new_role) and (current != "owner" or has_permission(actor_role, "owners.manage"))):
        raise ServiceError(403, "forbidden", "You cannot change this member's role.")
    if current == "owner" and new_role != "owner" and cs.count_owners(account_id) <= 1:
        raise ServiceError(409, "last_owner", "An account must keep at least one owner.")
    cs.set_membership_role(account_id, target_user_id, new_role)


def reset_password(account_id: str, actor_role: str, actor_user_id: int, target_user_id: int) -> str:
    """New one-time password for a member (shown once, expires in 72 h, must be changed). Sessions are revoked.
    Only for people who belong to this account alone, so an admin can never take over a login
    that also works in another account or on the platform."""
    current = _target_role(account_id, target_user_id)
    if not has_permission(actor_role, "users.manage") or (current == "owner" and not has_permission(actor_role, "owners.manage")):
        raise ServiceError(403, "forbidden", "You cannot reset this member's password.")
    if target_user_id == actor_user_id:
        raise ServiceError(400, "use_change_password", "Use change password for your own login.")
    target = auth.get_user_by_id(target_user_id)
    if not target or target["is_platform_admin"] or len(cs.list_accounts_for_user(target_user_id)) > 1:
        raise ServiceError(403, "shared_login", "This login is shared with another account or the platform; its owner must reset it.")
    temp = auth.generate_temporary_password()
    auth.update_user_password(target_user_id, temp, temporary=True)
    return temp


def remove_member(account_id: str, actor_role: str, target_user_id: int, purge: bool = False) -> Dict[str, Any]:
    current = _target_role(account_id, target_user_id)
    if not has_permission(actor_role, "users.manage") or (current == "owner" and not has_permission(actor_role, "owners.manage")):
        raise ServiceError(403, "forbidden", "You cannot remove this member.")
    if current == "owner" and cs.count_owners(account_id) <= 1:
        raise ServiceError(409, "last_owner", "An account must keep at least one owner.")
    cs.remove_membership(account_id, target_user_id)
    deleted = False
    if purge:
        target = auth.get_user_by_id(target_user_id)
        if target and not target["is_platform_admin"] and not cs.list_accounts_for_user(target_user_id):
            deleted = auth.delete_user(target_user_id)
    return {"success": True, "login_deleted": deleted}


def delete_account(account_id: str, actor_role: str, confirm_name: str) -> None:
    if not has_permission(actor_role, "account.manage"):
        raise ServiceError(403, "forbidden", "Only an owner can delete the account.")
    acct = cs.get_account(account_id)
    if not acct:
        raise ServiceError(404, "not_found", "Account not found.")
    if (confirm_name or "").strip() != acct["name"]:
        raise ServiceError(400, "confirm_name_mismatch", "Type the account name to confirm deletion.")
    cs.soft_delete_account(account_id)

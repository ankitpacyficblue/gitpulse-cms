"""
GitPulse CMS - Account and user management rules.

Business rules live here, not in the route handlers, so they are testable and
cannot be skipped by a new route:
- only a platform admin creates accounts;
- admins manage non-owner roles, only owners touch the owner role;
- an account always keeps at least one owner;
- users are created inside the caller's account, never elsewhere.
"""

from typing import Any, Dict

import crm_store as cs
from engine import access, auth


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


ASSIGNABLE = tuple(access.DEFAULTS) + ("agent",)      # "agent": the older role, still accepted


def _manager(actor: Any, account_id: str) -> Dict[str, Any]:
    """`actor`: an access description, or an older role name."""
    if isinstance(actor, str):
        key = "crm_agent" if actor == "agent" else actor
        who = {"role_key": key, "access": access.target_access(account_id, actor)}
    else:
        who = actor
    if not access.allows(who, "users:manage"):
        raise ServiceError(403, "forbidden", "You cannot manage people in this account.")
    return who


def _may_give(actor: Dict[str, Any], account_id: str, role: str) -> None:
    if role not in ASSIGNABLE:
        raise ServiceError(400, "invalid_role", "Role must be one of: " + ", ".join(access.DEFAULTS))
    if actor["role_key"] == "owner":
        return
    if role == "owner" or not access.within(actor, access.target_access(account_id, role)):
        raise ServiceError(403, "above_your_access", "You cannot grant more than you have.")


def _target(actor: Dict[str, Any], account_id: str, user_id: int) -> Dict[str, Any]:
    """The member to be changed. Only an owner may touch an owner or someone with more access than their own."""
    member = access.membership(account_id, user_id)
    if not member:
        raise ServiceError(404, "not_found", "No such member in this account.")
    if actor["role_key"] != "owner":
        if member["role_key"] == "owner":
            raise ServiceError(403, "owner_only", "Only an owner can change an owner.")
        if not access.within(actor, member["access"]):
            raise ServiceError(403, "above_your_access", "This person has access you do not have.")
    return member


def add_user(account_id: str, actor: Any, username: str, role: str, email: str = "") -> Dict[str, Any]:
    who = _manager(actor, account_id)
    _may_give(who, account_id, role)
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
    cs.add_membership(account_id, user_id, access.OLD_ROLE[role])
    access.save_role(account_id, user_id, role)
    out.update({"user_id": user_id, "username": uname, "role": role})
    return out


def change_role(account_id: str, actor: Any, target_user_id: int, new_role: str) -> None:
    who = _manager(actor, account_id)
    _may_give(who, account_id, new_role)
    current = _target(who, account_id, target_user_id)["role_key"]
    if current == "owner" and new_role != "owner" and cs.count_owners(account_id) <= 1:
        raise ServiceError(409, "last_owner", "An account must keep at least one owner.")
    access.save_role(account_id, target_user_id, new_role)


def set_overrides(account_id: str, actor: Any, actor_user_id: int, target_user_id: int, overrides: Any) -> None:
    who = _manager(actor, account_id)
    if target_user_id == actor_user_id:
        raise ServiceError(403, "own_access", "You cannot change your own access.")
    member = _target(who, account_id, target_user_id)
    if member["role_key"] == "owner":
        raise ServiceError(400, "owner_only", "An owner always has everything.")
    try:
        levels = access.check_levels(overrides)
    except ValueError as e:
        raise ServiceError(400, str(e), "That section or level does not exist.")
    if who["role_key"] != "owner" and not access.within(who, levels):
        raise ServiceError(403, "above_your_access", "You cannot grant more than you have.")
    access.set_overrides(account_id, target_user_id, levels)


def reset_password(account_id: str, actor: Any, actor_user_id: int, target_user_id: int) -> str:
    """New one-time password for a member (shown once, expires in 72 h, must be changed). Sessions are revoked.
    Only for people who belong to this account alone, so an admin can never take over a login
    that also works in another account or on the platform."""
    _target(_manager(actor, account_id), account_id, target_user_id)
    if target_user_id == actor_user_id:
        raise ServiceError(400, "use_change_password", "Use change password for your own login.")
    target = auth.get_user_by_id(target_user_id)
    if not target or target["is_platform_admin"] or len(cs.list_accounts_for_user(target_user_id)) > 1:
        raise ServiceError(403, "shared_login", "This login is shared with another account or the platform; its owner must reset it.")
    temp = auth.generate_temporary_password()
    auth.update_user_password(target_user_id, temp, temporary=True)
    return temp


def remove_member(account_id: str, actor: Any, target_user_id: int, purge: bool = False) -> Dict[str, Any]:
    current = _target(_manager(actor, account_id), account_id, target_user_id)["role_key"]
    if current == "owner" and cs.count_owners(account_id) <= 1:
        raise ServiceError(409, "last_owner", "An account must keep at least one owner.")
    cs.remove_membership(account_id, target_user_id)
    access.forget(account_id, target_user_id)
    deleted = False
    if purge:
        target = auth.get_user_by_id(target_user_id)
        if target and not target["is_platform_admin"] and not cs.list_accounts_for_user(target_user_id):
            deleted = auth.delete_user(target_user_id)
    return {"success": True, "login_deleted": deleted}


def delete_account(account_id: str, actor_role: str, confirm_name: str) -> None:
    if (actor_role if isinstance(actor_role, str) else actor_role["role_key"]) != "owner":
        raise ServiceError(403, "forbidden", "Only an owner can delete the account.")
    acct = cs.get_account(account_id)
    if not acct:
        raise ServiceError(404, "not_found", "Account not found.")
    if (confirm_name or "").strip() != acct["name"]:
        raise ServiceError(400, "confirm_name_mismatch", "Type the account name to confirm deletion.")
    member_ids = [m["user_id"] for m in cs.list_members(account_id)]
    cs.soft_delete_account(account_id)
    # Logins that belonged only to this account are removed with it (never platform admins or shared logins).
    for uid in member_ids:
        u = auth.get_user_by_id(uid)
        if u and not u["is_platform_admin"] and not cs.list_accounts_for_user(uid):
            auth.delete_user(uid)

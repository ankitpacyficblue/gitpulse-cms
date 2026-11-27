"""Who may do what: a level per sidebar section, per account (docs/CRM-DASHBOARD-PERMISSIONS.md).

A person has one role per account plus per-section overrides. `memberships.role` keeps its old values for the
deployed code; `role_key` (with `role_key_base`, the `role` it was saved with) names the new role. If older code
changes `role`, the two no longer match and its choice wins. Nothing existing is rewritten: today's "agent"
is worked out as CRM agent plus overrides when it is read."""
from typing import Any, Dict, FrozenSet, List, Optional

import crm_store as cs
import database as db

LEVELS = ("none", "view", "manage", "full")

_SEE = ("view",)
_EDIT = ("view", "manage")
_ALL = ("view", "manage", "full")
# key: (name, group, levels it accepts besides "none", what "full" is called)
SECTIONS: Dict[str, tuple] = {
    "blog_dashboard": ("Blog Dashboard", "blog", _SEE, ""),
    "posts": ("Posts", "blog", _ALL, "Publish"),
    "websites": ("Websites", "blog", _EDIT, ""),
    "media": ("Media", "blog", _ALL, "Delete"),
    "crm_dashboard": ("CRM Dashboard", "crm", _SEE, ""),
    "inbox": ("Inbox", "crm", _EDIT, ""),
    "contacts": ("Contacts", "crm", _ALL, "Delete and fields"),
    "pipeline": ("Pipeline", "crm", _ALL, "Delete"),
    "broadcasts": ("Broadcasts", "crm", _EDIT, ""),
    "automations": ("Automations", "crm", _EDIT, ""),
    "ai_assistant": ("AI assistant", "crm", _EDIT, ""),
    "templates": ("Templates", "crm", _EDIT, ""),
    "entry_links": ("Entry links", "crm", _EDIT, ""),
    "wa_setup": ("WhatsApp setup", "platform", _EDIT, ""),
    "users": ("Users & Roles", "platform", ("manage",), ""),
    "logs": ("Logs", "platform", _SEE, ""),
    "settings": ("Settings", "platform", ("manage",), ""),
}      # "database" is platform administrators only: no account role can grant it

ROLE_NAMES = {"owner": "Owner", "admin": "Admin", "content_editor": "Content editor", "crm_agent": "CRM agent",
              "viewer": "Viewer"}
# What `memberships.role` holds for each (new roles fail closed in the older code).
OLD_ROLE = {"owner": "owner", "admin": "admin", "viewer": "viewer", "content_editor": "viewer", "crm_agent": "viewer",
            "agent": "agent"}

_TOP = {key: spec[2][-1] for key, spec in SECTIONS.items()}
DEFAULTS: Dict[str, Dict[str, str]] = {
    "owner": dict(_TOP),
    "admin": {k: v for k, v in _TOP.items() if k != "settings"},
    "content_editor": {"blog_dashboard": "view", "posts": "full", "websites": "manage", "media": "manage"},
    "crm_agent": {"crm_dashboard": "view", "inbox": "manage", "contacts": "manage", "pipeline": "manage"},
    "viewer": {k: "view" for k in SECTIONS if k not in ("users", "logs", "settings")},
}
# What turns a CRM agent into today's "agent".
AGENT_EXTRAS = {"blog_dashboard": "view", "posts": "manage", "websites": "view", "media": "manage",
                "broadcasts": "view", "automations": "view", "ai_assistant": "view", "templates": "view",
                "entry_links": "view", "wa_setup": "view"}

CRM_SECTIONS = ("crm_dashboard", "inbox", "contacts", "pipeline", "broadcasts", "automations", "ai_assistant",
                "templates", "entry_links")


def full_map(partial: Dict[str, str]) -> Dict[str, str]:
    return {key: partial.get(key, "none") for key in SECTIONS}


def at_least(have: str, need: str) -> bool:
    return LEVELS.index(have) >= LEVELS.index(need)


def role_access(account_id: str, role_key: str) -> Dict[str, str]:
    """The role as this account has set it. Owner cannot be changed."""
    out = full_map(DEFAULTS[role_key])
    if role_key != "owner":
        with db.get_connection() as conn:
            for r in conn.execute("SELECT section, level FROM role_permissions WHERE account_id = ? AND role_key = ?",
                                  (account_id, role_key)).fetchall():
                if r["section"] in out:
                    out[r["section"]] = r["level"]
    return out


def describe(account_id: str, user_id: int, role: str, role_key: Optional[str], base: Optional[str]) -> Dict[str, Any]:
    """A membership row -> {role_key, role_name, overrides, access}."""
    stored = role_key in DEFAULTS and role == base
    if stored:
        key = role_key
        with db.get_connection() as conn:
            overrides = {r["section"]: r["level"] for r in conn.execute(
                "SELECT section, level FROM permission_overrides WHERE account_id = ? AND user_id = ?",
                (account_id, user_id)).fetchall() if r["section"] in SECTIONS}
    else:
        key = "crm_agent" if role == "agent" else role
        overrides = dict(AGENT_EXTRAS) if role == "agent" else {}
    if key not in DEFAULTS:
        key = "viewer"
    access = role_access(account_id, key)
    if key != "owner":
        access.update(overrides)
    return {"role_key": key, "role_name": ROLE_NAMES[key], "overrides": overrides if key != "owner" else {},
            "access": access}


def membership(account_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    with db.get_connection() as conn:
        row = conn.execute("""SELECT m.role, m.role_key, m.role_key_base FROM memberships m
                              JOIN accounts a ON a.id = m.account_id
                              WHERE m.account_id = ? AND m.user_id = ? AND a.status = 'active'""",
                           (account_id, user_id)).fetchone()
    return describe(account_id, user_id, row["role"], row["role_key"], row["role_key_base"]) if row else None


def of(account_id: str, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A member's access; a platform administrator acts as owner in any active account."""
    if user.get("is_platform_admin"):
        acct = cs.get_account(account_id)
        if acct and acct.get("status", "active") == "active":
            return {"role_key": "owner", "role_name": "Owner", "overrides": {}, "access": full_map(DEFAULTS["owner"])}
        return None
    return membership(account_id, user["id"])


def allows(who: Dict[str, Any], need: str) -> bool:
    """`need`: "section:level" choices joined by "|". The section "crm" means any CRM section."""
    for choice in need.split("|"):
        section, level = choice.split(":")
        names = CRM_SECTIONS if section == "crm" else (section,)
        if any(at_least(who["access"].get(n, "none"), level) for n in names):
            return True
    return False


def sees_alert(who: Dict[str, Any], alert: Dict[str, Any]) -> bool:
    """A blog alert needs a blog section, every other stored alert a CRM one; system notices go to both."""
    blog, crm = allows(who, "blog_dashboard:view|posts:view"), allows(who, "crm:view")
    if alert["id"] is None:
        return blog or crm
    return blog if alert["type"] == "blog_failed" else crm


# The older permission names, still used by the screens and by checks inside handlers.
_NAMES = {
    "content.read": "blog_dashboard:view|posts:view|websites:view", "content.write": "posts:manage",
    "content.publish": "posts:full", "crm.read": "crm:view", "crm.write": "inbox:manage|contacts:manage|pipeline:manage",
    "crm.delete": "contacts:full|pipeline:full", "wa.config": "wa_setup:manage", "automations.manage": "automations:manage",
    "broadcasts.run": "broadcasts:manage", "users.manage": "users:manage", "audit.read": "logs:view",
    "ai.manage": "ai_assistant:manage", "account.manage": "settings:manage",
}


def names(who: Optional[Dict[str, Any]]) -> FrozenSet[str]:
    if not who:
        return frozenset()
    out = {name for name, need in _NAMES.items() if allows(who, need)}
    if who["role_key"] == "owner":
        out.add("owners.manage")
    return frozenset(out)


def within(actor: Dict[str, Any], access: Dict[str, str]) -> bool:
    """Nothing in `access` is higher than the actor's own."""
    return all(at_least(actor["access"].get(k, "none"), v) for k, v in access.items())


def check_levels(value: Any) -> Dict[str, str]:
    """{section: level} from a request. Raises ValueError("invalid_section" | "invalid_level")."""
    if not isinstance(value, dict):
        raise ValueError("invalid_section")
    out = {}
    for section, level in value.items():
        if section not in SECTIONS:
            raise ValueError("invalid_section")
        if level != "none" and level not in SECTIONS[section][2]:
            raise ValueError("invalid_level")
        out[section] = level
    return out


def _replace(table: str, where: Dict[str, Any], levels: Dict[str, str]) -> None:
    keys = list(where)
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM {table} WHERE {' AND '.join(k + ' = ?' for k in keys)}", tuple(where.values()))
        for section, level in levels.items():
            conn.execute(f"INSERT INTO {table} ({', '.join(keys)}, section, level) VALUES ({','.join('?' * (len(keys) + 2))})",
                         (*where.values(), section, level))
        conn.commit()


def set_role_access(account_id: str, role_key: str, levels: Dict[str, str]) -> None:
    """Only what differs from the default is stored; {} resets the role."""
    changed = {s: v for s, v in levels.items() if v != DEFAULTS[role_key].get(s, "none")}
    _replace("role_permissions", {"account_id": account_id, "role_key": role_key}, changed)


def set_overrides(account_id: str, user_id: int, levels: Dict[str, str]) -> None:
    """Replace a member's overrides, keeping their role."""
    current = membership(account_id, user_id)
    with db.get_connection() as conn:
        conn.execute("UPDATE memberships SET role_key = ?, role_key_base = role WHERE account_id = ? AND user_id = ?",
                     (current["role_key"], account_id, user_id))
        conn.commit()
    _replace("permission_overrides", {"account_id": account_id, "user_id": user_id}, levels)


def forget(account_id: str, user_id: int) -> None:
    _replace("permission_overrides", {"account_id": account_id, "user_id": user_id}, {})


def save_role(account_id: str, user_id: int, role_key: str) -> None:
    """Give a member a role ("agent" is the older one, still accepted) and drop their overrides."""
    old = OLD_ROLE[role_key]
    key = None if role_key == "agent" else role_key
    with db.get_connection() as conn:
        conn.execute("UPDATE memberships SET role = ?, role_key = ?, role_key_base = ? WHERE account_id = ? AND user_id = ?",
                     (old, key, old if key else None, account_id, user_id))
        conn.commit()
    forget(account_id, user_id)


def target_access(account_id: str, role_key: str) -> Dict[str, str]:
    """What giving this role would grant."""
    if role_key == "agent":
        return dict(role_access(account_id, "crm_agent"), **AGENT_EXTRAS)
    return role_access(account_id, role_key)


def members(account_id: str) -> List[Dict[str, Any]]:
    with db.get_connection() as conn:
        extra = {r["user_id"]: (r["role_key"], r["role_key_base"]) for r in conn.execute(
            "SELECT user_id, role_key, role_key_base FROM memberships WHERE account_id = ?", (account_id,)).fetchall()}
    return [dict(m, **describe(account_id, m["user_id"], m["role"], *extra[m["user_id"]]))
            for m in cs.list_members(account_id)]

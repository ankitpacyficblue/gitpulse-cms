"""
GitPulse CMS - REST API controller (multi-account).

Access control is table driven and default-deny:
- every route is registered with @route(method, pattern, access);
- a request that matches no registered route gets 404 and reaches no handler;
- `access` decides what is checked BEFORE the handler runs:
    "public"          no session needed (login, logout, presets)
    "session"         any signed-in user
    "platform"        signed-in platform admin
    "member"          member of the account in the URL (/api/accounts/:id/...)
    "path:<perm>"     member of the URL's account holding permission <perm>
    "acct:<perm>"     member of the account named by the X-Account-Id header holding <perm>
- tenant data is only reachable with the account resolved by those checks; an account id
  in a query string or body is never used.
"""

import dbcompat
from currencies import is_valid_currency
import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import crm_store as cs
import database as db
from config import FRAMEWORK_PRESETS, DEFAULT_AI_PROVIDER
from engine import accounts_service as svc
from engine import auth
from engine import secrets_box
from engine import assistant, contact_fields, jobs, messaging
from engine import media, site_publish
from database import normalize_repo
from engine import writer_tokens
from engine.accounts_service import ServiceError
from engine.auth import (
    authenticate_user, revoke_session, update_user_password, verify_password,
    get_user_by_id, get_user_by_username,
)
from engine.github_client import GitHubClient
from engine.permissions import permissions_for, has_permission
from engine.pipeline import run_publication_pipeline
from engine.seo_linter import lint_article
from engine.templates_embed import generate_one_time_blog_html
from engine.totp import generate_totp_secret, verify_totp_code, get_totp_uri
from engine.whatsapp_client import WhatsAppClient, mock_enabled
from scheduler.cron_worker import scheduler

Response = Tuple[int, Dict[str, Any]]


class Ctx:
    """Who is calling and for which account. Built only by the access checks."""
    def __init__(self, user, account_id=None, role=None, ip="", user_agent="", token=None, host=""):
        self.user, self.account_id, self.role, self.ip, self.user_agent = user, account_id, role, ip, user_agent
        self.token = token
        self.host = host
        self.headers = {}


PASSWORD_CHANGE_OK = {"/api/auth/change-password", "/api/auth/me", "/api/auth/logout"}

ROUTES: List[Tuple[str, "re.Pattern", str, Callable]] = []


def route(method: str, pattern: str, access: str):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), access, fn))
        return fn
    return deco


def _forbidden(required: str) -> Response:
    return 403, {"error": "forbidden", "required": required}


def _mask_project(p: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(p)
    q["has_github_token"] = bool(q.pop("github_token", ""))
    q["has_webhook_secret"] = bool(q.pop("webhook_secret", ""))
    return q


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ==========================================================================
# Dispatcher
# ==========================================================================

def _role_for(user: Dict[str, Any], account_id: str) -> Optional[str]:
    """Role in an account: the membership role, or "owner" for a platform admin (support access to any active
    account; every write is still audit-logged against the account)."""
    role = cs.get_membership_role(account_id, user["id"])
    if role or not user.get("is_platform_admin"):
        return role
    acct = cs.get_account(account_id)
    return "owner" if acct and acct.get("status", "active") == "active" else None


def handle_api_request(method: str, path: str, *args, **kwargs) -> Response:
    """Catch-all: a handler bug returns a JSON 500, never a dropped connection."""
    try:
        return _handle_api_request(method, path, *args, **kwargs)
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("gitpulse").exception("API handler failed: %s %s", method, path)
        if dbcompat.is_transient(e):
            return 503, {"error": "Service temporarily unavailable. Please retry.", "code": "UNAVAILABLE"}
        return 500, {"error": "Internal server error", "code": "INTERNAL"}


def _handle_api_request(method: str, path: str, query_params: Dict[str, str], body_data: Optional[Dict[str, Any]],
                       current_user: Optional[Dict[str, Any]] = None, client_ip: str = "127.0.0.1",
                       user_agent: str = "", headers: Optional[Dict[str, str]] = None) -> Response:
    body = body_data if isinstance(body_data, dict) else {}
    hdrs = {k.lower(): v for k, v in (headers or {}).items()}

    for m, rx, access, fn in ROUTES:
        if m != method:
            continue
        match = rx.match(path)
        if not match:
            continue

        if access == "public":
            ctx = Ctx(None, ip=client_ip, user_agent=user_agent)
            ctx.headers = hdrs
            return fn(ctx, match, query_params, body)

        if access == "writer":      # an AI writer's own token, never a session; scoped to its account
            writer = writer_tokens.authenticate(hdrs.get("authorization", ""))
            if not writer:
                return 401, {"error": "invalid_writer_token", "message": "This writer token is not valid."}
            ctx = Ctx(None, writer["account_id"], ip=client_ip, user_agent=user_agent,
                      host=hdrs.get("x-forwarded-host") or hdrs.get("host", ""))
            if writer["over_limit"]:
                return 429, {"error": "rate_limited", "message": "This writer token has used its requests for this hour."}
            ctx.writer = writer
            return fn(ctx, match, query_params, body)

        if not current_user:
            return 401, {"error": "Authentication required. Please log in.", "code": "UNAUTHORIZED"}
        if current_user.get("must_change_password") and path not in PASSWORD_CHANGE_OK:
            return 403, {"error": "password_change_required", "code": "password_change_required",
                         "message": "Change your temporary password to continue."}
        ctx = Ctx(current_user, ip=client_ip, user_agent=user_agent, token=current_user.get("token"),
                  host=hdrs.get("x-forwarded-host") or hdrs.get("host", ""))

        if access == "session":
            ctx.account_id = hdrs.get("x-account-id") or None   # optional here (used by /api/auth/me)
            if ctx.account_id:
                ctx.role = _role_for(current_user, ctx.account_id)
                if not ctx.role:
                    return _forbidden("membership")
            return fn(ctx, match, query_params, body)

        if access == "platform":
            if not current_user.get("is_platform_admin"):
                return _forbidden("platform_admin")
            return fn(ctx, match, query_params, body)

        if access == "member" or access.startswith("path:"):
            ctx.account_id = match.group("aid")
            ctx.role = _role_for(current_user, ctx.account_id)
            if not ctx.role:
                return _forbidden("membership")
            perm = access[5:] if access.startswith("path:") else None
        elif access.startswith("acct:"):
            account_id = hdrs.get("x-account-id")
            if not account_id:
                return 400, {"error": "account_required", "code": "select_account",
                         "message": "Select an account first (send the X-Account-Id header)."}
            role = _role_for(current_user, account_id)
            if not role:
                return _forbidden("membership")
            ctx.account_id, ctx.role = account_id, role
            perm = access[5:]
        else:
            return 500, {"error": "route misconfigured"}

        if perm and not has_permission(ctx.role, perm):
            return _forbidden(perm)
        jobs.maybe_tick()
        try:
            return fn(ctx, match, query_params, body)
        except ServiceError as e:
            return e.status, {"error": e.code, "message": e.message}

    return 404, {"error": f"API endpoint {method} {path} not found."}


# ==========================================================================
# Authentication
# ==========================================================================

@route("POST", r"/api/auth/login", "public")
def login(ctx, m, q, body):
    username, password = body.get("username", ""), body.get("password", "")
    totp_code = (body.get("totp_code") or "").strip()
    if not username or not password:
        return 400, {"error": "Username and password are required."}
    target = get_user_by_username(username)
    if target and target.get("totp_enabled") and not totp_code:
        if not verify_password(password, target["salt"], target["password_hash"]):
            return 401, {"error": "Invalid username or password."}
        return 200, {"requires_2fa": True,
                     "message": "Enter the 6-digit code from your authenticator app to complete sign-in."}
    if target and target.get("totp_enabled") and not verify_totp_code(target["totp_secret"], totp_code):
        return 401, {"error": "Invalid 2-Factor Authentication code."}
    ok, token, user, err = authenticate_user(username, password, ctx.ip, ctx.user_agent)
    if not ok:
        return 401, {"error": err or "Authentication failed.", "locked": "locked" in (err or "").lower()}
    return 200, {"token": token, "user": user, "must_change_password": bool(user.get("must_change_password")),
                 "message": "Login successful."}


@route("POST", r"/api/auth/logout", "public")
def logout(ctx, m, q, body):
    token = body.get("token")
    if token:
        revoke_session(token)
    return 200, {"message": "Logged out successfully."}


@route("GET", r"/api/presets", "public")
def presets(ctx, m, q, body):
    return 200, FRAMEWORK_PRESETS


@route("GET", r"/api/auth/me", "session")
def me(ctx, m, q, body):
    full = get_user_by_username(ctx.user["username"]) or {}
    memberships = [{"account_id": a["id"], "name": a["name"], "role": a["role"]}
                   for a in cs.list_accounts_for_user(ctx.user["id"])]
    return 200, {
        "user": {"id": ctx.user["id"], "username": ctx.user["username"], "email": ctx.user.get("email", ""),
                 "is_platform_admin": ctx.user["is_platform_admin"],
                 "must_change_password": bool(ctx.user.get("must_change_password")), "totp_enabled": bool(full.get("totp_enabled"))},
        "memberships": memberships,
        "active_account_id": ctx.account_id,
        "permissions": sorted(permissions_for(ctx.role)) if ctx.account_id else [],
    }


@route("GET", r"/api/auth/2fa/setup", "session")
def twofa_setup(ctx, m, q, body):
    secret = generate_totp_secret()
    return 200, {"secret": secret, "otpauth_uri": get_totp_uri(ctx.user["username"], secret)}


@route("POST", r"/api/auth/2fa/enable", "session")
def twofa_enable(ctx, m, q, body):
    if not verify_totp_code(body.get("secret", ""), body.get("code", "")):
        return 400, {"error": "Verification failed: 6-digit code did not match."}
    with db.get_connection() as conn:
        conn.execute("UPDATE users SET totp_secret = ?, totp_enabled = 1 WHERE id = ?", (body["secret"], ctx.user["id"]))
        conn.commit()
    return 200, {"message": "Two-Factor Authentication (2FA) successfully activated!"}


@route("POST", r"/api/auth/2fa/disable", "session")
def twofa_disable(ctx, m, q, body):
    full = get_user_by_username(ctx.user["username"])
    if not verify_password(body.get("password", ""), full["salt"], full["password_hash"]):
        return 400, {"error": "Invalid password."}
    with db.get_connection() as conn:
        conn.execute("UPDATE users SET totp_secret = '', totp_enabled = 0 WHERE id = ?", (ctx.user["id"],))
        conn.commit()
    return 200, {"message": "Two-Factor Authentication has been disabled."}


@route("POST", r"/api/auth/change-password", "session")
def change_password(ctx, m, q, body):
    cur, new = body.get("current_password", ""), body.get("new_password", "")
    if not cur or not new:
        return 400, {"error": "Current and new passwords are required."}
    if len(new) < 8:
        return 400, {"error": "New password must be at least 8 characters long."}
    full = get_user_by_username(ctx.user["username"])
    if not verify_password(cur, full["salt"], full["password_hash"]):
        return 400, {"error": "Current password is incorrect."}
    if new == cur:
        return 400, {"error": "New password must be different from the current one."}
    update_user_password(ctx.user["id"], new)
    return 200, {"message": "Password changed successfully. Please log in again."}


# ==========================================================================
# Accounts and users
# ==========================================================================

@route("GET", r"/api/accounts", "session")
def accounts_list(ctx, m, q, body):
    if ctx.user.get("is_platform_admin"):
        return 200, {"accounts": cs.list_all_accounts(ctx.user["id"])}
    return 200, {"accounts": cs.list_accounts_for_user(ctx.user["id"])}


@route("POST", r"/api/accounts", "session")
def accounts_create(ctx, m, q, body):
    try:
        out = svc.create_account_with_owner(ctx.user, body.get("name", ""), body.get("owner_username", ""),
                                            body.get("owner_email", ""))
    except ServiceError as e:
        return e.status, {"error": e.code, "message": e.message}
    out["role"] = "owner" if out["owner_user_id"] == ctx.user["id"] else None
    return 201, out


@route("GET", r"/api/accounts/(?P<aid>[0-9a-f]{32})", "member")
def account_get(ctx, m, q, body):
    a = cs.get_account(ctx.account_id)
    return 200, {"id": a["id"], "name": a["name"], "default_currency": a.get("default_currency", "INR"), "role": ctx.role, "permissions": sorted(permissions_for(ctx.role))}


@route("PATCH", r"/api/accounts/(?P<aid>[0-9a-f]{32})", "path:account.manage")
def account_rename(ctx, m, q, body):
    ok = False
    try:
        if "default_currency" in body:
            ok = cs.set_default_currency(ctx.account_id, body["default_currency"])
        if "name" in body or "default_currency" not in body:
            ok = cs.rename_account(ctx.account_id, body.get("name", ""))
    except ValueError as e:
        return 400, {"error": "invalid_input", "message": str(e)}
    return 200, {"success": ok}


@route("DELETE", r"/api/accounts/(?P<aid>[0-9a-f]{32})", "path:account.manage")
def account_delete(ctx, m, q, body):
    svc.delete_account(ctx.account_id, ctx.role, body.get("confirm_name", ""))
    return 200, {"success": True, "message": "Account deleted. Its data is retained and stays private to it."}


@route("GET", r"/api/account/settings", "acct:account.manage")
def account_settings_get(ctx, m, q, body):
    return 200, cs.get_account_settings_public(ctx.account_id)


@route("POST", r"/api/account/settings", "acct:account.manage")
def account_settings_save(ctx, m, q, body):
    if (body.get("ai_api_key") or body.get("github_token")) and not secrets_box.is_configured():
        return 500, _NO_ENC
    provider = body.get("ai_provider")
    if provider is not None and provider not in AI_PROVIDERS:
        return 400, {"error": "invalid_ai_provider", "allowed": sorted(AI_PROVIDERS)}
    cs.save_account_settings(ctx.account_id, ai_provider=provider, ai_api_key=body.get("ai_api_key") or "",
                             github_token=body.get("github_token") or "",
                             clear_ai_key=bool(body.get("clear_ai_key")), clear_github_token=bool(body.get("clear_github_token")))
    db.log_event("Account AI/GitHub settings updated.", "INFO", account_id=ctx.account_id)
    return 200, {"success": True, "settings": cs.get_account_settings_public(ctx.account_id)}


@route("GET", r"/api/accounts/(?P<aid>[0-9a-f]{32})/users", "path:users.manage")
def users_list(ctx, m, q, body):
    return 200, {"users": cs.list_members(ctx.account_id)}


@route("POST", r"/api/accounts/(?P<aid>[0-9a-f]{32})/users", "path:users.manage")
def users_add(ctx, m, q, body):
    ident = body.get("username") or body.get("email") or ""
    out = svc.add_user(ctx.account_id, ctx.role, ident, body.get("role", ""), body.get("email", ""))
    db.log_event(f"User '{out['username']}' added as {out['role']}.", "INFO", account_id=ctx.account_id)
    return 201, out


@route("PUT", r"/api/accounts/(?P<aid>[0-9a-f]{32})/users/(?P<uid>\d+)", "path:users.manage")
def users_role(ctx, m, q, body):
    svc.change_role(ctx.account_id, ctx.role, int(m.group("uid")), body.get("role", ""))
    db.log_event(f"Role of user #{m.group('uid')} changed to {body.get('role')}.", "INFO", account_id=ctx.account_id)
    return 200, {"success": True}


@route("POST", r"/api/accounts/(?P<aid>[0-9a-f]{32})/users/(?P<uid>\d+)/reset-password", "path:users.manage")
def users_reset_password(ctx, m, q, body):
    temp = svc.reset_password(ctx.account_id, ctx.role, ctx.user["id"], int(m.group("uid")))
    db.log_event(f"Password reset for user #{m.group('uid')}.", "INFO", account_id=ctx.account_id)
    return 200, {"temporary_password": temp, "expires_in_hours": 72, "must_change_password": True}


@route("DELETE", r"/api/accounts/(?P<aid>[0-9a-f]{32})/users/(?P<uid>\d+)", "path:users.manage")
def users_remove(ctx, m, q, body):
    """Removes the person from this account. With ?purge=1 their login is also deleted when it belongs to no other account."""
    out = svc.remove_member(ctx.account_id, ctx.role, int(m.group("uid")), purge=q.get("purge") in ("1", "true", "yes"))
    db.log_event(f"User #{m.group('uid')} removed from account" + (" and login deleted." if out["login_deleted"] else "."),
                 "INFO", account_id=ctx.account_id)
    return 200, out


# ==========================================================================
# Platform administration (global, not tenant data)
# ==========================================================================

_SENSITIVE = ("key", "secret", "token", "password")


@route("GET", r"/api/users", "platform")
def platform_users(ctx, m, q, body):
    """All logins with their number of active accounts; ?orphans=1 lists only logins with no account."""
    users = [u for u in auth.list_users_with_account_counts() if not (q.get("orphans") in ("1", "true") and u["account_count"] > 0)]
    return 200, {"users": users}


@route("DELETE", r"/api/users/(?P<uid>\d+)", "platform")
def platform_user_delete(ctx, m, q, body):
    """Platform admin removes a login that belongs to no account (left over from deleted accounts)."""
    uid = int(m.group("uid"))
    target = auth.get_user_by_id(uid)
    if not target:
        return 404, {"error": "not_found", "message": "No such user."}
    if uid == ctx.user["id"] or target["is_platform_admin"]:
        return 403, {"error": "forbidden", "message": "Platform admins cannot be deleted here."}
    n = len(cs.list_accounts_for_user(uid))
    if n:
        return 409, {"error": "has_accounts", "message": f"This login still belongs to {n} account(s). Remove it from them first."}
    auth.delete_user(uid)
    db.log_event(f"Orphan login #{uid} deleted by platform admin.", "INFO")
    return 200, {"success": True}


@route("GET", r"/api/settings", "platform")
def settings_get(ctx, m, q, body):
    out = {}
    for k, v in db.get_all_settings().items():
        out[k] = ("…" + v[-4:] if len(v) > 8 else "…") if (v and any(s in k.lower() for s in _SENSITIVE)) else v
    return 200, out


@route("POST", r"/api/settings", "platform")
def settings_set(ctx, m, q, body):
    for k, v in body.items():
        if k == "session_secret" or str(v).startswith("…"):
            continue
        db.set_setting(k, str(v))
    return 200, {"message": "Settings updated successfully."}


@route("GET", r"/api/supabase/status", "platform")
def sb_status(ctx, m, q, body):
    return 200, db.test_supabase_connection()


@route("POST", r"/api/supabase/test", "platform")
def sb_test(ctx, m, q, body):
    from engine.supabase_client import SupabaseClient
    sb = SupabaseClient(url=body.get("url") or db.get_setting("supabase_url", ""),
                        key=body.get("key") or db.get_setting("supabase_key", ""))
    ok, msg = sb.test_connection()
    return 200, {"connected": ok, "message": msg, "configured": sb.is_configured()}


@route("POST", r"/api/supabase/sync", "platform")
def sb_sync(ctx, m, q, body):
    res = db.sync_all_to_supabase()
    return (200 if res.get("success") else 400), res


# ==========================================================================
# Account-scoped: status, blog projects, posts, logs
# ==========================================================================

@route("GET", r"/api/status", "acct:content.read")
def status(ctx, m, q, body):
    projects = db.list_projects(ctx.account_id)
    posts = db.list_posts_for_account(ctx.account_id, limit=100)
    return 200, {"status": "online", "scheduler_active": scheduler.is_alive(), "projects_count": len(projects),
                 "total_posts": len(posts), "published_posts": sum(1 for p in posts if p.get("status") == "published"),
                 "ai_provider": db.get_setting("ai_provider", DEFAULT_AI_PROVIDER), "mock_mode": mock_enabled()}


@route("POST", r"/api/github/verify", "acct:content.publish")
def github_verify(ctx, m, q, body):
    repo = normalize_repo(body.get("github_repo", ""))
    if not repo:
        return 400, {"valid": False, "message": "Please enter a GitHub repository (e.g. username/repo)."}
    ok, msg = GitHubClient(token=body.get("github_token", "").strip()).test_connection(repo)
    return 200, {"valid": ok, "repo": repo, "branch": "main", "message": msg}


@route("GET", r"/api/projects", "acct:content.read")
def projects_list(ctx, m, q, body):
    return 200, {"projects": [_mask_project(p) for p in db.list_projects(ctx.account_id)]}


@route("POST", r"/api/projects", "acct:content.publish")
def projects_create(ctx, m, q, body):
    if not body.get("name") or not body.get("github_repo") or not body.get("topic"):
        return 400, {"error": "Missing required fields: 'name', 'github_repo', and 'topic' are mandatory."}
    if body.get("github_token") and not secrets_box.is_configured():
        return 500, _NO_ENC
    return 201, {"id": db.create_project(body, ctx.account_id), "message": "Project registered successfully."}


_NO_ENC = {"error": "encryption_not_configured",
           "message": "The server has no CREDENTIAL_ENC_KEY, so credentials cannot be stored."}


def _gh_token(ctx, project) -> str:
    """Project token first, then the account's default token. Never the platform-wide token."""
    return project.get("github_token") or cs.get_account_github_token(ctx.account_id)


def _own_project(ctx, project_id: int) -> Optional[Dict[str, Any]]:
    p = db.get_project(project_id)
    return p if p and p.get("account_id") == ctx.account_id else None


@route("GET", r"/api/projects/(?P<pid>\d+)", "acct:content.read")
def project_get(ctx, m, q, body):
    p = _own_project(ctx, int(m.group("pid")))
    return (200, _mask_project(p)) if p else (404, {"error": "Project not found."})


@route("PUT", r"/api/projects/(?P<pid>\d+)", "acct:content.publish")
def project_update(ctx, m, q, body):
    data = {k: v for k, v in body.items() if k not in ("account_id", "client_id", "id")}
    for k in ("github_token", "webhook_secret"):      # empty keeps the stored value
        if not data.get(k):
            data.pop(k, None)
    if data.get("github_token") and not secrets_box.is_configured():
        return 500, _NO_ENC
    if not db.update_project(int(m.group("pid")), data, ctx.account_id):
        return 404, {"error": "Project not found or no changes made."}
    return 200, {"message": "Project updated successfully."}


@route("DELETE", r"/api/projects/(?P<pid>\d+)", "acct:content.publish")
def project_delete(ctx, m, q, body):
    if not db.delete_project(int(m.group("pid")), ctx.account_id):
        return 404, {"error": "Project not found."}
    return 200, {"message": "Project deleted."}


@route("POST", r"/api/projects/(?P<pid>\d+)/trigger", "acct:content.publish")
def project_trigger(ctx, m, q, body):
    pid = int(m.group("pid"))
    if not _own_project(ctx, pid):
        return 404, {"error": "Project not found."}
    try:
        return 200, run_publication_pipeline(pid, force_publish=body.get("force_publish", True))
    except Exception as e:
        return 500, {"error": str(e)}


@route("POST", r"/api/projects/(?P<pid>\d+)/test-github", "acct:content.publish")
def project_test_github(ctx, m, q, body):
    proj = _own_project(ctx, int(m.group("pid")))
    if not proj:
        return 404, {"error": "Project not found."}
    ok, msg = GitHubClient(token=_gh_token(ctx, proj)).test_connection(proj["github_repo"])
    return (200 if ok else 400), {"connected": ok, "message": msg}


@route("POST", r"/api/projects/(?P<pid>\d+)/install-blog-page", "acct:content.publish")
def project_install_blog(ctx, m, q, body):
    pid = int(m.group("pid"))
    proj = _own_project(ctx, pid)
    if not proj:
        return 404, {"error": "Project not found."}
    token = _gh_token(ctx, proj)
    page_path = proj.get("blog_page_path", "public/blog/index.html")
    html = generate_one_time_blog_html(pid, proj["name"], body.get("cms_base_url", ""))
    if not token:
        return 400, {"success": False, "error": "Add a GitHub token to this project first."}
    ok, sha, err = GitHubClient(token=token).commit_file(
        proj["github_repo"], page_path, html, proj["github_branch"],
        f"feat(blog): install zero-redeploy dynamic blog page at {page_path}")
    if ok:
        return 200, {"success": True, "path": page_path, "commit_sha": sha,
                     "message": f"Installed zero-redeploy blog to {proj['github_repo']} at {page_path}."}
    return 500, {"success": False, "error": err or "Failed to commit blog page."}


@route("GET", r"/api/posts", "acct:content.read")
def posts_list(ctx, m, q, body):
    return 200, {"posts": db.list_posts_for_account(ctx.account_id, project_id=_int(q.get("project_id")),
                                                    limit=_int(q.get("limit"), 50))}


@route("GET", r"/api/posts/(?P<id>\d+)", "acct:content.read")
def post_get(ctx, m, q, body):
    post = db.get_post_for_account(ctx.account_id, int(m.group("id")))
    return (200, post) if post else (404, {"error": "Post not found."})


@route("PUT", r"/api/posts/(?P<id>\d+)", "acct:content.publish")
def post_update(ctx, m, q, body):
    post_id = int(m.group("id"))
    post = db.get_post_for_account(ctx.account_id, post_id)
    if not post:
        return 404, {"error": "Post not found."}
    proj = _own_project(ctx, post["project_id"])
    title = body.get("title", post["title"])
    excerpt = body.get("excerpt", post["excerpt"])
    content = body.get("content_markdown", post["content_markdown"])
    db.update_post_content(post_id, title, excerpt, content, body.get("frontmatter_yaml", post["frontmatter_yaml"]),
                           body.get("tags", post["tags"]))
    lint = lint_article(title, excerpt, content, proj.get("forbidden_words", ""))
    with db.get_connection() as conn:
        conn.execute("UPDATE posts SET seo_score = ?, seo_issues = ? WHERE id = ?",
                     (lint["score"], json.dumps(lint["issues"]), post_id))
        conn.commit()
    return 200, {"message": "Article updated in staging queue.", "seo_score": lint["score"], "seo_issues": lint["issues"]}


def _publish_post(ctx, post_id: int, approve: bool) -> Response:
    post = db.get_post_for_account(ctx.account_id, post_id)
    if not post:
        return 404, {"error": "Post not found."}
    project = _own_project(ctx, post["project_id"])
    from engine.formatters import assemble_post_document
    if not site_publish.git_enabled():
        db.update_post_status(post_id=post_id, status="published")
        return 200, {"success": True, "message": "Article published.",
                     "pub_result": {"success": True, "mode": "live", "commit_sha": None, "pr_url": None}}
    res = GitHubClient(token=_gh_token(ctx, project)).publish_post(
        repo=project["github_repo"], branch=project["github_branch"], target_path=post["target_path"],
        file_content=assemble_post_document(post["frontmatter_yaml"], post["content_markdown"]),
        post_title=post["title"], post_excerpt=post["excerpt"],
        post_tags=json.loads(post["tags"]) if isinstance(post["tags"], str) else [],
        mode=project.get("publishing_mode", "pr"))
    if res.get("success"):
        db.update_post_status(post_id=post_id, status="published", commit_sha=res.get("commit_sha"),
                              pr_url=res.get("pr_url"), pr_number=res.get("pr_number"))
        out = {"success": True, "pub_result": res}
        if approve:
            out["message"] = "Article approved and published to GitHub!"
        return 200, out
    db.update_post_status(post_id=post_id, status="failed", error=res.get("error"))
    return 500, {"success": False, "error": res.get("error")}


@route("POST", r"/api/posts/(?P<id>\d+)/approve", "acct:content.publish")
def post_approve(ctx, m, q, body):
    return _publish_post(ctx, int(m.group("id")), True)


@route("POST", r"/api/posts/(?P<id>\d+)/publish", "acct:content.publish")
def post_publish(ctx, m, q, body):
    return _publish_post(ctx, int(m.group("id")), False)


@route("GET", r"/api/logs", "acct:audit.read")
def logs(ctx, m, q, body):
    return 200, {"logs": db.list_logs(ctx.account_id, limit=_int(q.get("limit"), 60))}


# ==========================================================================
# WhatsApp: configuration (per account)
# ==========================================================================

def _wa_public(account_id: str, host: str = "") -> Dict[str, Any]:
    import os
    cfg = cs.get_whatsapp_public(account_id)
    cfg["webhook_path"] = "/api/webhook/whatsapp"
    cfg["mock_mode"] = mock_enabled()
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base and host:
        scheme = "http" if host.startswith(("127.0.0.1", "localhost")) else "https"
        base = f"{scheme}://{host}"
    cfg["webhook_url"] = base + cfg["webhook_path"] if base else ""
    return cfg


@route("GET", r"/api/whatsapp/config", "acct:crm.read")
def wa_config_get(ctx, m, q, body):
    return 200, _wa_public(ctx.account_id, ctx.host)


@route("POST", r"/api/whatsapp/config", "acct:wa.config")
def wa_config_save(ctx, m, q, body):
    if (body.get("access_token") or body.get("app_secret")) and not secrets_box.is_configured():
        return 500, {"error": "encryption_not_configured",
                     "message": "The server has no CREDENTIAL_ENC_KEY, so credentials cannot be stored."}
    try:
        verify = cs.save_whatsapp_account(
            ctx.account_id, phone_number_id=body.get("phone_number_id"), waba_id=body.get("waba_id"),
            business_name=body.get("business_name"), phone_number=body.get("phone_number"),
            access_token=body.get("access_token") or "", app_secret=body.get("app_secret") or "")
    except Exception as e:
        if dbcompat.is_unique_violation(e):
            return 409, {"error": "phone_number_in_use", "message": "That WhatsApp phone number id is already connected to another account."}
        raise
    db.log_event("WhatsApp configuration updated.", "INFO", account_id=ctx.account_id)
    out = {"success": True, "config": _wa_public(ctx.account_id, ctx.host)}
    if verify:
        out["verify_token"] = verify          # shown once
    return 200, out


@route("GET", r"/api/whatsapp/connection-status", "acct:crm.read")
def wa_connection_status(ctx, m, q, body):
    """Setup wizard: {mock_mode, webhook_url, credentials{...bool}, last_webhook_at, last_test{at,ok,message}, ready}."""
    pub = _wa_public(ctx.account_id, ctx.host)
    st = cs.get_whatsapp_status(ctx.account_id)
    c = st["credentials"]
    st.update({"mock_mode": pub["mock_mode"], "webhook_url": pub["webhook_url"],
               "ready": bool(c["phone_number_id"] and c["access_token"] and c["app_secret"] and st["last_webhook_at"])})
    return 200, st


@route("POST", r"/api/whatsapp/config/test", "acct:wa.config")
def wa_test_connection(ctx, m, q, body):
    """Read-only check of the saved credentials at Meta. Never sends a message."""
    res = WhatsAppClient(ctx.account_id).test_connection()
    return 200, res


@route("POST", r"/api/whatsapp/config/verify-token", "acct:wa.config")
def wa_rotate_verify(ctx, m, q, body):
    token = cs.rotate_verify_token(ctx.account_id)
    if not token:
        return 404, {"error": "WhatsApp is not configured for this account."}
    return 200, {"verify_token": token}


# ==========================================================================
# WhatsApp CRM: contacts, conversations, deals, broadcasts, automations
# ==========================================================================

def _valid_phone(phone: str) -> bool:
    digits = re.sub(r"[\s\-().]", "", str(phone))
    return bool(re.fullmatch(r"\+?\d{8,15}", digits))


@route("GET", r"/api/whatsapp/contacts", "acct:crm.read")
def contacts_list(ctx, m, q, body):
    rows = contact_fields.present(ctx.account_id, cs.list_contacts(ctx.account_id, search=q.get("search", ""),
                                                                   tag=q.get("tag", "")))
    try:
        return 200, {"contacts": contact_fields.filter_contacts(ctx.account_id, rows, q)}
    except contact_fields.FieldError as e:
        return e.status, {"error": e.code, "message": e.message}


@route("POST", r"/api/whatsapp/contacts", "acct:crm.write")
def contacts_create(ctx, m, q, body):
    name, phone = str(body.get("name", "")).strip(), str(body.get("phone", "")).strip()
    if not name or not phone:
        return 400, {"error": "Name and phone number are required."}
    if not _valid_phone(phone):
        return 400, {"error": "invalid_phone", "message": "Enter the phone number with country code, 8 to 15 digits, for example +919876543210."}
    try:
        custom = contact_fields.validate(ctx.account_id, body.get("custom"))
    except contact_fields.FieldError as e:
        return e.status, {"error": e.code, "message": e.message}
    try:
        cid = cs.create_contact(ctx.account_id, name, phone, email=body.get("email", ""),
                                tags=body.get("tags") or ["Lead"], notes=body.get("notes", ""))
    except ValueError:
        return 409, {"error": "duplicate_phone", "message": "A contact with this phone number already exists."}
    if custom:
        contact_fields.save(ctx.account_id, cid, custom)
    cs.get_or_create_conversation(ctx.account_id, cid)
    return 201, {"success": True, "id": cid, "message": "Contact created successfully."}


@route("PUT", r"/api/whatsapp/contacts/(?P<id>\d+)", "acct:crm.write")
def contacts_update(ctx, m, q, body):
    fields = {k: body[k] for k in ("name", "phone", "email", "tags", "notes", "status") if k in body}
    try:
        custom = contact_fields.validate(ctx.account_id, body.get("custom"))
    except contact_fields.FieldError as e:
        return e.status, {"error": e.code, "message": e.message}
    try:
        ok = cs.update_contact(ctx.account_id, int(m.group("id")), **fields) if fields else \
            cs.get_contact(ctx.account_id, int(m.group("id"))) is not None
    except Exception as e:
        if dbcompat.is_unique_violation(e):
            return 409, {"error": "duplicate_phone"}
        raise
    if ok and custom:
        contact_fields.save(ctx.account_id, int(m.group("id")), custom)
    return (200, {"success": True}) if ok else (404, {"error": "Contact not found."})


@route("DELETE", r"/api/whatsapp/contacts/(?P<id>\d+)", "acct:crm.delete")
def contacts_delete(ctx, m, q, body):
    ok = cs.delete_contact(ctx.account_id, int(m.group("id")))
    return (200, {"success": True}) if ok else (404, {"error": "Contact not found."})


def _with_window(conv: Dict[str, Any], look_up: bool = False) -> Dict[str, Any]:
    """window_open / window_expires_at (UTC): free text is possible only while the window is open."""
    end = messaging.window_expires_at(conv) if (look_up or conv.get("last_inbound_at")) else None
    return dict(conv, window_expires_at=end.isoformat() + "Z" if end else None,
                window_open=bool(end and datetime.utcnow() < end))


@route("GET", r"/api/whatsapp/conversations", "acct:crm.read")
def conv_list(ctx, m, q, body):
    mine = ctx.user["id"] if q.get("assigned") == "me" else None
    rows = cs.list_conversations(ctx.account_id, status=q.get("status", ""), assigned_user_id=mine,
                                 include_empty=q.get("include_empty") in ("1", "true", "yes"),
                                 contact_id=_int(q.get("contact_id")))
    if q.get("needs_human") in ("1", "true", "yes"):
        rows = [r for r in rows if r.get("needs_human")]
    return 200, {"conversations": [_with_window(r) for r in rows]}


@route("PUT", r"/api/whatsapp/conversations/(?P<id>\d+)/assign", "acct:crm.write")
def conversation_assign(ctx, m, q, body):
    raw = body.get("user_id")
    uid = None if raw in (None, "", 0) else _int(raw)
    if raw not in (None, "", 0) and uid is None:
        return 400, {"error": "invalid_user_id"}
    if uid is not None and not cs.get_membership_role(ctx.account_id, uid):
        return 400, {"error": "not_a_member", "message": "That user is not in this account."}
    ok = cs.assign_conversation(ctx.account_id, int(m.group("id")), uid)
    return (200, {"success": True}) if ok else (404, {"error": "Conversation not found."})


@route("GET", r"/api/whatsapp/conversations/(?P<id>\d+)", "acct:crm.read")
def conv_get(ctx, m, q, body):
    conv = cs.get_conversation(ctx.account_id, int(m.group("id")))
    return (200, _with_window(conv, look_up=True)) if conv else (404, {"error": "Conversation not found."})


@route("GET", r"/api/whatsapp/conversations/(?P<id>\d+)/messages", "acct:crm.read")
def conv_messages(ctx, m, q, body):
    cid = int(m.group("id"))
    if not cs.get_conversation(ctx.account_id, cid):
        return 404, {"error": "Conversation not found."}
    return 200, {"messages": media.attach(ctx.account_id, cs.list_messages(ctx.account_id, cid, limit=_int(q.get("limit"), 100)))}


@route("POST", r"/api/whatsapp/conversations/(?P<id>\d+)/messages", "acct:crm.write")
def conv_send(ctx, m, q, body):
    text = str(body.get("body", "")).strip()
    media_id = body.get("media_id")
    if not text and not media_id:
        return 400, {"error": "Message body is required."}
    conv = cs.get_conversation(ctx.account_id, int(m.group("id")))
    if not conv:
        return 404, {"error": "Conversation not found."}
    contact = cs.get_contact(ctx.account_id, conv["contact_id"])
    try:
        res = messaging.send(ctx.account_id, contact, text, sent_by="staff", media_id=media_id)
    except messaging.Blocked as b:
        return 409, {"success": False, "error": b.code, "message": b.message}
    assistant.staff_replied(ctx.account_id, conv["id"])
    return (200 if res.get("success") else 502), {"success": bool(res.get("success")), "message_id": res.get("message_id"),
                                                  "status": res.get("status"), "error": res.get("error")}


@route("POST", r"/api/whatsapp/conversations/(?P<id>\d+)/read", "acct:crm.write")
def conv_read(ctx, m, q, body):
    ok = cs.mark_conversation_read(ctx.account_id, int(m.group("id")))
    return (200, {"success": True}) if ok else (404, {"error": "Conversation not found."})


@route("GET", r"/api/whatsapp/deals", "acct:crm.read")
def deals_list(ctx, m, q, body):
    return 200, {"deals": cs.list_deals(ctx.account_id)}


@route("POST", r"/api/whatsapp/deals", "acct:crm.write")
def deals_create(ctx, m, q, body):
    title = str(body.get("title", "")).strip()
    if not title:
        return 400, {"error": "Deal title is required."}
    try:
        value = float(body.get("value", 0.0))
    except (TypeError, ValueError):
        return 400, {"error": "Deal value must be a number."}
    if value < 0 or value != value or value in (float("inf"), float("-inf")):
        return 400, {"error": "invalid_value", "message": "Deal value cannot be negative."}
    cur_in = str(body.get("currency") or "").strip()
    if cur_in and not is_valid_currency(cur_in):
        return 400, {"error": "invalid_currency", "message": "Currency must be a valid ISO code such as INR or USD."}
    if str(body.get("stage", "lead")) not in DEAL_STAGES:
        return 400, {"error": "invalid_stage", "allowed": DEAL_STAGES}
    try:
        did = cs.create_deal(ctx.account_id, title, value, stage=body.get("stage", "lead"),
                             contact_id=_int(body.get("contact_id")), currency=(body.get("currency") or None),
                             expected_close=body.get("expected_close", ""), notes=body.get("notes", ""))
    except ValueError:
        return 404, {"error": "Contact not found."}
    cur_code = cur_in.upper() or (cs.get_account(ctx.account_id) or {}).get("default_currency") or "INR"
    return 201, {"success": True, "id": did, "currency": cur_code, "message": "Deal created successfully."}


@route("PUT", r"/api/whatsapp/deals/(?P<id>\d+)/stage", "acct:crm.write")
def deals_stage(ctx, m, q, body):
    stage = str(body.get("stage", "")).strip()
    if not stage:
        return 400, {"error": "Stage is required."}
    if stage not in DEAL_STAGES:
        return 400, {"error": "invalid_stage", "allowed": DEAL_STAGES}
    ok = cs.update_deal_stage(ctx.account_id, int(m.group("id")), stage)
    return (200, {"success": True}) if ok else (404, {"error": "Deal not found."})


@route("DELETE", r"/api/whatsapp/deals/(?P<id>\d+)", "acct:crm.delete")
def deals_delete(ctx, m, q, body):
    ok = cs.delete_deal(ctx.account_id, int(m.group("id")))
    return (200, {"success": True}) if ok else (404, {"error": "Deal not found."})


def _template_choice(account_id: str, body: Dict[str, Any]):
    """(template row, params) or raise messaging.Blocked."""
    tpl = messaging.approved_template(account_id, str(body.get("template_name") or ""),
                                      str(body.get("template_language") or ""))
    params = body.get("template_params") or []
    if not isinstance(params, list) or len(params) < tpl["variables"] or any(not str(p).strip() for p in params):
        raise messaging.Blocked("missing_variables", f"This template needs {tpl['variables']} values.")
    return tpl, [str(p) for p in params]


@route("GET", r"/api/whatsapp/broadcasts", "acct:crm.read")
def bc_list(ctx, m, q, body):
    rows = cs.list_broadcasts(ctx.account_id)
    with db.get_connection() as conn:
        counts = conn.execute("SELECT broadcast_id, status, COUNT(*) AS n FROM messages WHERE account_id = ? "
                              "AND broadcast_id IS NOT NULL GROUP BY broadcast_id, status", (ctx.account_id,)).fetchall()
    by = {}
    for r in counts:
        by.setdefault(r["broadcast_id"], {})[r["status"]] = r["n"]
    for row in rows:
        c = by.get(row["id"])
        if c is None:
            continue
        row["queued_count"] = c.get("queued", 0)
        row["failed_count"] = c.get("failed", 0)
        row["read_count"] = c.get("read", 0)
        row["delivered_count"] = c.get("delivered", 0) + row["read_count"]
        row["sent_count"] = c.get("sent", 0) + c.get("mock", 0) + row["delivered_count"]
        row["status"] = "queued" if row["queued_count"] else "completed"
    return 200, {"broadcasts": rows}


@route("GET", r"/api/whatsapp/broadcasts/(?P<id>\d+)/recipients", "acct:crm.read")
def bc_recipients(ctx, m, q, body):
    bid = int(m.group("id"))
    if not cs.get_broadcast(ctx.account_id, bid):
        return 404, {"error": "Broadcast not found."}
    with db.get_connection() as conn:
        rows = conn.execute("SELECT msg.contact_id, c.name, c.phone, msg.status, msg.error_message FROM messages msg "
                            "JOIN contacts c ON c.id = msg.contact_id AND c.account_id = msg.account_id "
                            "WHERE msg.account_id = ? AND msg.broadcast_id = ? ORDER BY msg.id", (ctx.account_id, bid)).fetchall()
    return 200, {"recipients": [dict(r) for r in rows]}


@route("POST", r"/api/whatsapp/broadcasts", "acct:broadcasts.run")
def bc_create(ctx, m, q, body):
    name = str(body.get("name", "")).strip()
    if not name or not body.get("template_name"):
        return 400, {"error": "template_required", "message": "Campaign name and an approved template are required."}
    try:
        tpl, params = _template_choice(ctx.account_id, body)
        file = messaging.media_for(ctx.account_id, tpl, body.get("media_id"))
    except messaging.Blocked as b:
        return 400, {"error": b.code, "message": b.message}
    bid = cs.create_broadcast(ctx.account_id, name, tpl["body"], target_tag=str(body.get("target_tag") or "all"),
                              template_name=tpl["name"], template_language=tpl["language"], template_params=params)
    if file:
        with db.get_connection() as conn:
            conn.execute("UPDATE broadcasts SET media_id = ? WHERE id = ? AND account_id = ?", (file["id"], bid, ctx.account_id))
            conn.commit()
    if body.get("auto_send"):
        return 201, {"success": True, "id": bid, "executed": True,
                     "stats": WhatsAppClient(ctx.account_id).execute_broadcast(bid)}
    return 201, {"success": True, "id": bid, "message": "Broadcast created."}


@route("POST", r"/api/whatsapp/broadcasts/preview", "acct:broadcasts.run")
def bc_preview(ctx, m, q, body):
    try:
        tpl = messaging.approved_template(ctx.account_id, str(body.get("template_name") or ""),
                                          str(body.get("template_language") or ""))
    except messaging.Blocked as b:
        return 400, {"error": b.code, "message": b.message}
    return 200, WhatsAppClient(ctx.account_id).preview_broadcast(tpl, str(body.get("target_tag") or "all"))


@route("POST", r"/api/whatsapp/broadcasts/(?P<id>\d+)/run", "acct:broadcasts.run")
def bc_run(ctx, m, q, body):
    stats = WhatsAppClient(ctx.account_id).execute_broadcast(int(m.group("id")))
    if not stats.get("success"):
        if stats.get("code") == "already_run":
            return 409, stats
        return 404 if "not found" in stats.get("error", "") else 400, stats
    return 200, {"success": True, "stats": stats}


AI_PROVIDERS = {"gemini", "openai", "mock"}
TRIGGER_TYPES = {"welcome", "keyword", "blog_publish"}
DEAL_STAGES = ["lead", "qualified", "proposal", "negotiation", "won", "lost"]


@route("GET", r"/api/whatsapp/automations", "acct:crm.read")
def auto_list(ctx, m, q, body):
    return 200, {"automations": cs.list_automations(ctx.account_id)}


@route("POST", r"/api/whatsapp/automations", "acct:automations.manage")
def auto_create(ctx, m, q, body):
    name, trig, tpl = (("" if body.get(k) is None else str(body.get(k))).strip() for k in ("name", "trigger_type", "message_template"))
    extra = {}
    if trig == "blog_publish":      # goes to people outside the 24-hour window, so it needs an approved template
        try:
            template, params = _template_choice(ctx.account_id, body)
            messaging.media_for(ctx.account_id, template, None)      # an automatic alert has no file to attach
        except messaging.Blocked as b:
            return 400, {"error": b.code, "message": b.message}
        tpl = template["body"] or template["name"]
        extra = {"template_name": template["name"], "template_language": template["language"], "template_params": params}
    if not name or not trig or not tpl:
        return 400, {"error": "Name, trigger type, and message template are required."}
    if trig not in TRIGGER_TYPES:
        return 400, {"error": "invalid_trigger", "allowed": sorted(TRIGGER_TYPES)}
    if trig == "keyword" and not str(body.get("trigger_keyword") or "").strip():
        return 400, {"error": "keyword_required", "message": "A keyword rule needs trigger_keyword."}
    aid = cs.create_automation(ctx.account_id, name, trig, tpl, trigger_keyword=str(body.get("trigger_keyword") or ""),
                               action_type=str(body.get("action_type") or "send_message"),
                               is_active=bool(body.get("is_active", True)), **extra)
    return 201, {"success": True, "id": aid, "message": "Automation rule created."}


@route("PUT", r"/api/whatsapp/automations/(?P<id>\d+)/toggle", "acct:automations.manage")
def auto_toggle(ctx, m, q, body):
    ok = cs.toggle_automation(ctx.account_id, int(m.group("id")), bool(body.get("is_active", True)))
    return (200, {"success": True}) if ok else (404, {"error": "Automation not found."})


@route("DELETE", r"/api/whatsapp/automations/(?P<id>\d+)", "acct:automations.manage")
def auto_delete(ctx, m, q, body):
    ok = cs.delete_automation(ctx.account_id, int(m.group("id")))
    return (200, {"success": True}) if ok else (404, {"error": "Automation not found."})


@route("POST", r"/api/whatsapp/simulate-incoming", "acct:wa.config")
def simulate_incoming(ctx, m, q, body):
    """Dev tool: feeds a fake inbound message into THIS account. Off unless WHATSAPP_MOCK=1."""
    if not mock_enabled():
        return 404, {"error": "API endpoint POST /api/whatsapp/simulate-incoming not found."}
    phone = str(body.get("phone", "")).lstrip("+")
    if not phone:
        return 400, {"error": "phone is required."}
    val = {"messages": [{"from": phone, "id": f"wamid.sim_{cs._now()}", "type": "text",
                         "text": {"body": str(body.get("message", "Hello"))}}],
           "contacts": [{"wa_id": phone, "profile": {"name": body.get("name") or f"Lead {phone[-4:]}"}}]}
    msgs, _ = WhatsAppClient(ctx.account_id)._process_change(val)
    return 200, {"success": True, "simulated": True, "processed_messages": msgs}


from server import routes_phase1  # noqa: E402,F401  (registers the Phase 1 routes)

"""Where a published post goes. By default GitPulse itself is the live source: the website reads posts from the
public API, and after publishing we ask it to refresh. Committing to the website repository is a per-account
setting that is off unless someone turns it on."""
import ipaddress
import json
import os
import urllib.request
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import crm_store as cs
import database as db
from engine import alerts, secrets_box

REFRESH_PATH = "/api/revalidate"
SECRET_HEADER = "X-Revalidate-Secret"
TIMEOUT = 5


class SettingsError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):      # a redirect would carry the secret elsewhere
        return None


def _row(account_id: str) -> Dict[str, Any]:
    with db.get_connection() as conn:
        row = conn.execute("SELECT publish_via_git, site_url, revalidate_secret_enc FROM account_settings "
                           "WHERE account_id = ?", (account_id,)).fetchone()
    return dict(row) if row else {"publish_via_git": 0, "site_url": "", "revalidate_secret_enc": ""}


def get_public(account_id: str) -> Dict[str, Any]:
    row = _row(account_id)
    return {"publish_via_git": bool(row["publish_via_git"]), "site_url": row["site_url"],
            "has_revalidate_secret": bool(row["revalidate_secret_enc"])}


def git_enabled(account_id: str) -> bool:
    return bool(_row(account_id)["publish_via_git"])


def _site_url(value: Any) -> str:
    url = str(value or "").strip().rstrip("/")
    if not url:
        return ""
    parts = urlparse(url)
    host = parts.hostname or ""
    if os.environ.get("ALLOW_LOCAL_SITE") == "1" and host in ("localhost", "127.0.0.1"):
        return url      # local development only
    try:
        ipaddress.ip_address(host)
        public_name = False
    except ValueError:
        public_name = "." in host and not host.endswith((".local", ".internal", ".localhost"))
    if parts.scheme != "https" or parts.username or parts.query or parts.fragment or not public_name:
        raise SettingsError("The website address must look like https://www.example.com.")
    return url


def save(account_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Only the keys sent are changed. An empty secret keeps the stored one."""
    changes: Dict[str, Any] = {}
    if "publish_via_git" in data:
        changes["publish_via_git"] = 1 if data["publish_via_git"] is True else 0
    if "site_url" in data:
        changes["site_url"] = _site_url(data["site_url"])
    secret = str(data.get("revalidate_secret") or "").strip()
    if secret:
        if not 16 <= len(secret) <= 200 or not secret.isascii() or not secret.isprintable():
            raise SettingsError("The refresh secret must be 16 to 200 plain characters.")
        try:
            changes["revalidate_secret_enc"] = secrets_box.encrypt(secret, account_id)
        except secrets_box.SecretsBoxError:
            raise SettingsError("Secrets cannot be stored: the server has no encryption key.")
    cs.save_account_settings(account_id)      # makes sure the row exists, changes nothing else
    if changes:
        with db.get_connection() as conn:
            conn.execute(f"UPDATE account_settings SET {', '.join(k + ' = ?' for k in changes)} WHERE account_id = ?",
                         (*changes.values(), account_id))
            conn.commit()
    return get_public(account_id)


def post_url(account_id: str, project_id: int, slug: str, origin: str = "") -> str:
    site = _row(account_id)["site_url"]
    return f"{site}/blog/{slug}" if site else f"{origin}/api/public/projects/{project_id}/posts/{slug}"


def refresh_site(account_id: str, slug: str) -> Optional[bool]:
    """Ask the website to show the change now. None: not set up. A failure never undoes a publish."""
    row = _row(account_id)
    if not row["site_url"] or not row["revalidate_secret_enc"]:
        return None
    try:
        secret = secrets_box.decrypt(row["revalidate_secret_enc"], account_id)
        request = urllib.request.Request(
            row["site_url"] + REFRESH_PATH, data=json.dumps({"slug": slug}).encode(), method="POST",
            headers={"Content-Type": "application/json", SECRET_HEADER: secret, "User-Agent": "GitPulse"})
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=TIMEOUT) as response:
            if response.status == 200:
                return True
    except Exception:      # noqa: BLE001  nothing from the request is logged: it holds the secret
        pass
    alerts.raise_alert(account_id, "blog_failed", "The post is published, but the website did not accept the refresh "
                       "request. It updates on its own within a few minutes. Check the website address and secret.",
                       link="blog")
    return False

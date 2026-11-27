"""Where a published post lives. GitPulse is the source: the account's website reads posts from the public API and
shows each at <website>/blog/<slug>. Publishing never commits to a repository."""
import ipaddress
from typing import Any
from urllib.parse import urlparse

import crm_store as cs
import database as db


def clean_website(value: Any) -> str:
    """'' or a public https address, without a trailing slash."""
    url = str(value or "").strip().rstrip("/")[:200]
    if not url:
        return ""
    try:
        parts = urlparse(url)
        host = parts.hostname or ""
    except ValueError:
        parts, host = None, ""
    try:
        ipaddress.ip_address(host)
        host = ""
    except ValueError:
        pass
    if (not parts or parts.scheme != "https" or parts.username or parts.query or parts.fragment or "." not in host
            or host.endswith((".local", ".internal", ".localhost")) or any(c in url for c in " \"'<>\\")):
        raise ValueError("The website address must look like https://www.example.com.")
    return url


def website_for(account_id: str, project_id=None) -> str:
    """The website's own address, else the account's, else ''."""
    project = db.get_project(int(project_id)) if project_id else None
    if project and project.get("account_id") == account_id and project.get("website_url"):
        return project["website_url"]
    return (cs.get_account(account_id) or {}).get("website_url") or ""


def post_url(account_id: str, slug: str, project_id=None) -> str:
    """The post's page on its website, or '' while no address is saved."""
    site = website_for(account_id, project_id)
    return f"{site}/blog/{slug}" if site else ""

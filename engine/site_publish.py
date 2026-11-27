"""Where a published post lives. GitPulse is the source: the account's website reads posts from the public API and
shows each at <website>/blog/<slug>. Publishing never commits to a repository."""
import ipaddress
from typing import Any
from urllib.parse import urlparse

import crm_store as cs


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


def post_url(account_id: str, slug: str) -> str:
    """The page on the account's website, or '' while no website address is saved."""
    site = (cs.get_account(account_id) or {}).get("website_url") or ""
    return f"{site}/blog/{slug}" if site else ""

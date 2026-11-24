"""
GitPulse CMS - Repository & Docs Context Ingestion (RAG & Internal Linking)
Extracts context from target repository README/docs via GitHub API,
and constructs internal linking suggestions to prior published posts.
"""

import base64
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from database import list_posts

def fetch_repo_readme(repo: str, token: str = "") -> str:
    """Fetch and decode repository README from GitHub API."""
    if not token or not repo or "/" not in repo:
        return ""

    url = f"https://api.github.com/repos/{repo.strip()}/readme"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitPulse-CMS-DocIngestion/1.0"
    }
    if token:
        headers["Authorization"] = f"token {token.strip()}"

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_b64 = data.get("content", "")
            if content_b64:
                return base64.b64decode(content_b64).decode("utf-8", errors="ignore")
    except Exception:
        pass
    return ""

def summarize_readme_context(readme_text: str, max_chars: int = 1200) -> str:
    """Extract key technical highlights from README to guide AI relevance."""
    if not readme_text:
        return ""

    # Strip badges and complex HTML
    clean = re.sub(r'\[!\[.*?\]\(.*?\)\]\(.*?\)', '', readme_text)
    clean = re.sub(r'<[^>]+>', '', clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()

    return clean[:max_chars]

def get_internal_linking_suggestions(project_id: int, current_slug: str = "", limit: int = 3) -> List[Dict[str, str]]:
    """Retrieve prior published articles for natural internal SEO cross-linking."""
    all_posts = list_posts(project_id=project_id, limit=20)
    suggestions = []
    
    for p in all_posts:
        if p["slug"] != current_slug and p.get("status") == "published":
            suggestions.append({
                "title": p["title"],
                "slug": p["slug"],
                "url": f"/blog/{p['slug']}"
            })
        if len(suggestions) >= limit:
            break

    return suggestions

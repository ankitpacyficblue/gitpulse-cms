"""
GitPulse CMS - Public Headless Content Delivery API
Serves dynamic blog posts, OpenGraph SVG banners, RSS 2.0 XML feeds,
and XML sitemaps to client websites without requiring repository builds.
"""

import json
import re
from typing import Dict, Any, Tuple, Optional
from database import get_project, list_posts, list_published_posts, get_post_by_slug, increment_post_views
from engine import media
from engine.image_generator import generate_hero_svg

_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")


def _summary(project_id: int, p: Dict[str, Any]) -> Dict[str, Any]:
    tags = json.loads(p["tags"]) if isinstance(p.get("tags"), str) else (p.get("tags") or [])
    meta = json.loads(p["meta_seo"]) if isinstance(p.get("meta_seo"), str) else (p.get("meta_seo") or {})
    cover = meta.get("cover")
    if not cover:      # posts published before the cover was recorded
        found = _IMAGE.search(p.get("content_markdown") or "")
        cover = {"url": found.group(2), "alt": found.group(1)} if found else None
    return {"id": p["id"], "title": p["title"], "slug": p["slug"], "excerpt": p["excerpt"], "tags": tags,
            "reading_time": meta.get("reading_time", 5), "published_at": p["published_at"], "cover_image": cover,
            "seo": {"title": p["title"], "description": meta.get("description") or p["excerpt"]},
            "og_image_url": f"/api/public/projects/{project_id}/posts/{p['slug']}/og-image.svg"}


def handle_public_request(path: str, query: Dict[str, str], client_ip: str = "") -> Tuple[int, str, str]:
    """
    Handle unauthenticated public headless blog requests.
    Returns: (status_code, content_type, response_body_string)
    """
    parts = path.strip("/").split("/")
    # /api/public/media/<token>: a file linked from a published post. 302 with the target as the body.
    if len(parts) == 4 and parts[:3] == ["api", "public", "media"]:
        try:
            link = media.public_link(parts[3])
        except media.MediaError:
            return 503, "application/json", json.dumps({"error": "Storage unavailable."})
        if not link:
            return 404, "application/json", json.dumps({"error": "File not found."})
        return 302, "text/plain", link
    # Expected: /api/public/projects/<id>/...
    if len(parts) < 4 or parts[0] != "api" or parts[1] != "public" or parts[2] != "projects":
        return 404, "application/json", json.dumps({"error": "Invalid public endpoint."})

    try:
        project_id = int(parts[3])
    except ValueError:
        return 400, "application/json", json.dumps({"error": "Invalid project ID."})

    project = get_project(project_id)
    if not project:
        return 404, "application/json", json.dumps({"error": "Project not found."})

    sub_path = parts[4] if len(parts) > 4 else ""

    # 1. GET /api/public/projects/<id>/posts
    if sub_path == "posts" and len(parts) == 5:
        newest = {}
        for p in list_published_posts(project_id):
            newest.setdefault(p["slug"], p)      # a republished title replaces the earlier post
        return 200, "application/json", json.dumps(
            {"project": project["name"], "posts": [_summary(project_id, p) for p in newest.values()]})

    # 2. GET /api/public/projects/<id>/posts/<slug>
    if sub_path == "posts" and len(parts) == 6:
        slug = parts[5]
        post = get_post_by_slug(project_id, slug)
        if not post or post.get("status") != "published":
            return 404, "application/json", json.dumps({"error": f"Article '{slug}' not found."})

        # Track view
        increment_post_views(post["id"], ip_hash=client_ip)

        meta = json.loads(post["meta_seo"]) if isinstance(post.get("meta_seo"), str) else (post.get("meta_seo") or {})
        return 200, "application/json", json.dumps(dict(
            _summary(project_id, post), content_markdown=post["content_markdown"], body_format="markdown",
            meta_seo=meta, github_pr_url=post.get("github_pr_url"), github_commit_sha=post.get("github_commit_sha")))

    # 3. GET /api/public/projects/<id>/posts/<slug>/og-image.svg
    if sub_path == "posts" and len(parts) == 7 and parts[6] == "og-image.svg":
        slug = parts[5]
        post = get_post_by_slug(project_id, slug)
        title = post["title"] if post else "Technical Deep Dive"
        author = project.get("author_name", "Editorial Team")
        svg = generate_hero_svg(title=title, category=project.get("name", "Engineering"), author=author)
        return 200, "image/svg+xml; charset=utf-8", svg

    # 4. GET /api/public/projects/<id>/rss.xml
    if sub_path == "rss.xml":
        all_posts = list_posts(project_id=project_id, limit=25)
        published = [p for p in all_posts if p.get("status") == "published"]
        items_xml = ""
        for p in published:
            items_xml += f"""
    <item>
      <title>{p['title']}</title>
      <link>/blog/{p['slug']}</link>
      <description><![CDATA[{p['excerpt']}]]></description>
      <pubDate>{p['published_at'] or ''}</pubDate>
      <guid>/blog/{p['slug']}</guid>
    </item>"""
        rss_xml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>{project['name']} Blog</title>
    <link>https://github.com/{project['github_repo']}</link>
    <description>Daily technical insights and engineering updates from {project['name']}.</description>
    {items_xml}
  </channel>
</rss>"""
        return 200, "application/xml; charset=utf-8", rss_xml

    return 404, "application/json", json.dumps({"error": "Unknown public endpoint."})

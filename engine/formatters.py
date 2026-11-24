"""
GitPulse CMS - Formatters & Templates
Handles slug generation, frontmatter rendering, reading time computation,
and framework-specific file path formatting (Next.js, Astro, Hugo, Jekyll, Docusaurus).
"""

import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text or "post"

def calculate_reading_time(markdown_content: str, words_per_minute: int = 220) -> int:
    """Calculate reading time in minutes."""
    words = len(re.findall(r'\b\w+\b', markdown_content))
    return max(1, round(words / words_per_minute))

def format_frontmatter(template: str, variables: Dict[str, Any]) -> str:
    """
    Render frontmatter template using variable dictionary.
    Replaces {variable_name} placeholders cleanly.
    """
    rendered = template
    tags = variables.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [t.strip() for t in tags.split(",") if t.strip()]

    tags_json = json.dumps(tags)
    
    replacements = {
        "{title}": str(variables.get("title", "")).replace('"', '\\"'),
        "{excerpt}": str(variables.get("excerpt", "")).replace('"', '\\"'),
        "{date}": str(variables.get("date", datetime.utcnow().strftime("%Y-%m-%d"))),
        "{date_iso}": str(variables.get("date_iso", datetime.utcnow().isoformat())),
        "{author}": str(variables.get("author", "Editorial Team")).replace('"', '\\"'),
        "{slug}": str(variables.get("slug", "")),
        "{tags_json}": tags_json,
        "{reading_time}": str(variables.get("reading_time", 5))
    }

    for placeholder, val in replacements.items():
        rendered = rendered.replace(placeholder, val)
        
    return rendered.strip()

def build_target_filepath(project: Dict[str, Any], slug: str, post_date: Optional[str] = None) -> str:
    """
    Build target path in repository according to framework convention.
    - Jekyll requires: _posts/YYYY-MM-DD-title.md
    - Docusaurus typically: blog/YYYY-MM-DD-title.md or blog/slug.md
    - Astro: src/content/blog/slug.md
    - Next.js: content/posts/slug.mdx
    """
    content_dir = project.get("content_dir", "content/posts").strip("/")
    ext = project.get("file_extension", ".md")
    if not ext.startswith("."):
        ext = "." + ext

    framework = project.get("target_framework", "").lower()
    date_str = post_date or datetime.utcnow().strftime("%Y-%m-%d")

    if framework == "jekyll":
        filename = f"{date_str}-{slug}{ext}"
    else:
        filename = f"{slug}{ext}"

    if content_dir:
        return f"{content_dir}/{filename}"
    return filename

def assemble_post_document(frontmatter_yaml: str, markdown_content: str) -> str:
    """Assemble final full document ready for commit."""
    frontmatter = frontmatter_yaml.strip()
    body = markdown_content.strip()
    return f"{frontmatter}\n\n{body}\n"

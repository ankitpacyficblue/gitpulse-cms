"""
GitPulse CMS - Configuration Management
Centralized configuration, environment variable resolution, and default presets.
"""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent

# Support Vercel serverless /tmp ephemeral storage for local SQLite fallback
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DATA_DIR = Path("/tmp/gitpulse_data")
else:
    DATA_DIR = BASE_DIR / "data"

DATABASE_PATH = Path(os.environ["GITPULSE_DB_PATH"]) if os.environ.get("GITPULSE_DB_PATH") else DATA_DIR / "gitpulse.db"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Default Server Config
SERVER_HOST = os.environ.get("GITPULSE_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("GITPULSE_PORT", "8420"))

# Default Secrets & Tokens (can be set via Web UI or ENV)
DEFAULT_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
DEFAULT_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_AI_PROVIDER = os.environ.get("DEFAULT_AI_PROVIDER", "gemini") # gemini | openai | anthropic | mock

# Framework presets
FRAMEWORK_PRESETS = {
    "nextjs": {
        "name": "Next.js (App Router / Contentlayer / Velite)",
        "content_dir": "content/posts",
        "file_extension": ".mdx",
        "frontmatter_format": "yaml",
        "frontmatter_template": """---
title: "{title}"
description: "{excerpt}"
date: "{date}"
author: "{author}"
tags: {tags_json}
coverImage: "/images/blog/{slug}.jpg"
published: true
---"""
    },
    "astro": {
        "name": "Astro (Content Collections)",
        "content_dir": "src/content/blog",
        "file_extension": ".md",
        "frontmatter_format": "yaml",
        "frontmatter_template": """---
title: "{title}"
description: "{excerpt}"
pubDate: "{date}"
heroImage: "/blog-placeholder.jpg"
tags: {tags_json}
draft: false
---"""
    },
    "hugo": {
        "name": "Hugo Static Site",
        "content_dir": "content/posts",
        "file_extension": ".md",
        "frontmatter_format": "yaml",
        "frontmatter_template": """---
title: "{title}"
date: {date_iso}
draft: false
tags: {tags_json}
summary: "{excerpt}"
---"""
    },
    "jekyll": {
        "name": "Jekyll / GitHub Pages",
        "content_dir": "_posts",
        "file_extension": ".md",
        "frontmatter_format": "yaml",
        "frontmatter_template": """---
layout: post
title: "{title}"
date: {date_iso}
categories: {tags_json}
excerpt: "{excerpt}"
---"""
    },
    "docusaurus": {
        "name": "Docusaurus (Blog Plugin)",
        "content_dir": "blog",
        "file_extension": ".md",
        "frontmatter_format": "yaml",
        "frontmatter_template": """---
slug: {slug}
title: "{title}"
authors: [{author}]
tags: {tags_json}
date: {date}
---"""
    },
    "generic": {
        "name": "Generic Markdown / Custom",
        "content_dir": "content/blog",
        "file_extension": ".md",
        "frontmatter_format": "yaml",
        "frontmatter_template": """---
title: "{title}"
date: "{date}"
excerpt: "{excerpt}"
tags: {tags_json}
---"""
    }
}

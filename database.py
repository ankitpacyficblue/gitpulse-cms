"""
GitPulse CMS - SQLite Database Layer
Handles persistent storage with WAL mode, robust transaction management, and ORM-like accessors.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import DATABASE_PATH, FRAMEWORK_PRESETS

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    """Create tables if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Projects Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            github_repo TEXT NOT NULL,
            github_branch TEXT NOT NULL DEFAULT 'main',
            github_token TEXT DEFAULT '',
            target_framework TEXT NOT NULL DEFAULT 'nextjs',
            content_dir TEXT NOT NULL DEFAULT 'content/posts',
            file_extension TEXT NOT NULL DEFAULT '.mdx',
            frontmatter_template TEXT NOT NULL,
            topic TEXT NOT NULL,
            target_audience TEXT NOT NULL DEFAULT 'Developers and Tech Enthusiasts',
            tone TEXT NOT NULL DEFAULT 'Authoritative, practical, and engaging',
            keywords TEXT NOT NULL DEFAULT '',
            author_name TEXT NOT NULL DEFAULT 'Editorial Team',
            publishing_mode TEXT NOT NULL DEFAULT 'pr', -- 'pr' or 'direct'
            publish_time TEXT NOT NULL DEFAULT '09:00',
            is_active INTEGER NOT NULL DEFAULT 1,
            last_run_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # Posts Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            slug TEXT NOT NULL,
            excerpt TEXT NOT NULL,
            content_markdown TEXT NOT NULL,
            frontmatter_yaml TEXT NOT NULL,
            target_path TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            meta_seo TEXT NOT NULL DEFAULT '{}',
            image_prompt TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft', -- draft, scheduled, published, failed
            github_commit_sha TEXT,
            github_pr_url TEXT,
            github_pr_number INTEGER,
            error_message TEXT,
            published_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """)

        # System Logs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            post_id INTEGER,
            level TEXT NOT NULL DEFAULT 'INFO',
            message TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """)

        # Settings Table (key-value)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            created_at TEXT NOT NULL
        )
        """)

        # Active User Sessions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            expires_at REAL NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # Login Attempts (for Brute Force & Malicious Login Restriction)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            username TEXT NOT NULL,
            attempt_time REAL NOT NULL,
            success INTEGER NOT NULL DEFAULT 0
        )
        """)

        # Index for fast lockout queries
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_user ON login_attempts (ip_address, username, attempt_time)
        """)

        # Post Views Analytics Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            viewed_at TEXT NOT NULL,
            ip_hash TEXT NOT NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
        """)

        # Safe Column Migrations for Existing Databases
        project_cols = [c[1] for c in cursor.execute("PRAGMA table_info(projects)").fetchall()]
        if "auto_publish" not in project_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN auto_publish INTEGER NOT NULL DEFAULT 1")
        if "forbidden_words" not in project_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN forbidden_words TEXT NOT NULL DEFAULT ''")
        if "webhook_secret" not in project_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN webhook_secret TEXT NOT NULL DEFAULT ''")
        if "zero_redeploy_enabled" not in project_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN zero_redeploy_enabled INTEGER NOT NULL DEFAULT 1")
        if "blog_page_path" not in project_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN blog_page_path TEXT NOT NULL DEFAULT 'public/blog/index.html'")

        post_cols = [c[1] for c in cursor.execute("PRAGMA table_info(posts)").fetchall()]
        if "og_image_svg" not in post_cols:
            cursor.execute("ALTER TABLE posts ADD COLUMN og_image_svg TEXT DEFAULT ''")
        if "seo_score" not in post_cols:
            cursor.execute("ALTER TABLE posts ADD COLUMN seo_score INTEGER DEFAULT 100")
        if "seo_issues" not in post_cols:
            cursor.execute("ALTER TABLE posts ADD COLUMN seo_issues TEXT DEFAULT '[]'")
        if "views" not in post_cols:
            cursor.execute("ALTER TABLE posts ADD COLUMN views INTEGER DEFAULT 0")

        user_cols = [c[1] for c in cursor.execute("PRAGMA table_info(users)").fetchall()]
        if "totp_secret" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT DEFAULT ''")
        if "totp_enabled" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER DEFAULT 0")

        conn.commit()

# --- Project Operations ---

def list_projects() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, 
                   COUNT(post.id) as total_posts,
                   SUM(CASE WHEN post.status = 'published' THEN 1 ELSE 0 END) as published_posts
            FROM projects p
            LEFT JOIN posts post ON p.id = post.project_id
            GROUP BY p.id
            ORDER BY p.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_project(project_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_project(data: Dict[str, Any]) -> int:
    framework = data.get("target_framework", "generic")
    preset = FRAMEWORK_PRESETS.get(framework, FRAMEWORK_PRESETS["generic"])
    
    now = datetime.utcnow().isoformat()
    content_dir = data.get("content_dir") or preset["content_dir"]
    file_extension = data.get("file_extension") or preset["file_extension"]
    frontmatter_template = data.get("frontmatter_template") or preset["frontmatter_template"]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO projects (
                name, github_repo, github_branch, github_token,
                target_framework, content_dir, file_extension,
                frontmatter_template, topic, target_audience, tone,
                keywords, author_name, publishing_mode, publish_time,
                is_active, auto_publish, forbidden_words, webhook_secret,
                zero_redeploy_enabled, blog_page_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("name", "New Project"),
            data.get("github_repo", "").strip(),
            data.get("github_branch", "main").strip(),
            data.get("github_token", "").strip(),
            framework,
            content_dir.strip("/"),
            file_extension,
            frontmatter_template,
            data.get("topic", "").strip(),
            data.get("target_audience", "Developers and Tech Enthusiasts").strip(),
            data.get("tone", "Authoritative, practical, and engaging").strip(),
            data.get("keywords", "").strip(),
            data.get("author_name", "Editorial Team").strip(),
            data.get("publishing_mode", "pr"),
            data.get("publish_time", "09:00").strip(),
            1 if data.get("is_active", True) else 0,
            1 if data.get("auto_publish", True) else 0,
            data.get("forbidden_words", "").strip(),
            data.get("webhook_secret", "").strip(),
            1 if data.get("zero_redeploy_enabled", True) else 0,
            data.get("blog_page_path", "public/blog/index.html").strip(),
            now,
            now
        ))
        conn.commit()
        return cursor.lastrowid

def update_project(project_id: int, data: Dict[str, Any]) -> bool:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE projects SET
                name = COALESCE(?, name),
                github_repo = COALESCE(?, github_repo),
                github_branch = COALESCE(?, github_branch),
                github_token = COALESCE(?, github_token),
                target_framework = COALESCE(?, target_framework),
                content_dir = COALESCE(?, content_dir),
                file_extension = COALESCE(?, file_extension),
                frontmatter_template = COALESCE(?, frontmatter_template),
                topic = COALESCE(?, topic),
                target_audience = COALESCE(?, target_audience),
                tone = COALESCE(?, tone),
                keywords = COALESCE(?, keywords),
                author_name = COALESCE(?, author_name),
                publishing_mode = COALESCE(?, publishing_mode),
                publish_time = COALESCE(?, publish_time),
                is_active = COALESCE(?, is_active),
                auto_publish = COALESCE(?, auto_publish),
                forbidden_words = COALESCE(?, forbidden_words),
                webhook_secret = COALESCE(?, webhook_secret),
                zero_redeploy_enabled = COALESCE(?, zero_redeploy_enabled),
                blog_page_path = COALESCE(?, blog_page_path),
                updated_at = ?
            WHERE id = ?
        """, (
            data.get("name"),
            data.get("github_repo"),
            data.get("github_branch"),
            data.get("github_token"),
            data.get("target_framework"),
            data.get("content_dir"),
            data.get("file_extension"),
            data.get("frontmatter_template"),
            data.get("topic"),
            data.get("target_audience"),
            data.get("tone"),
            data.get("keywords"),
            data.get("author_name"),
            data.get("publishing_mode"),
            data.get("publish_time"),
            data.get("is_active"),
            data.get("auto_publish"),
            data.get("forbidden_words"),
            data.get("webhook_secret"),
            data.get("zero_redeploy_enabled"),
            data.get("blog_page_path"),
            now,
            project_id
        ))
        conn.commit()
        return cursor.rowcount > 0

def update_project_last_run(project_id: int):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE projects SET last_run_at = ?, updated_at = ? WHERE id = ?", (now, now, project_id))
        conn.commit()

def delete_project(project_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        return cursor.rowcount > 0

# --- Post Operations ---

def create_post(data: Dict[str, Any]) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO posts (
                project_id, title, slug, excerpt, content_markdown,
                frontmatter_yaml, target_path, tags, meta_seo, image_prompt,
                og_image_svg, seo_score, seo_issues,
                status, github_commit_sha, github_pr_url, github_pr_number,
                error_message, published_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["project_id"],
            data["title"],
            data["slug"],
            data.get("excerpt", ""),
            data["content_markdown"],
            data.get("frontmatter_yaml", ""),
            data["target_path"],
            json.dumps(data.get("tags", [])) if isinstance(data.get("tags"), list) else data.get("tags", "[]"),
            json.dumps(data.get("meta_seo", {})) if isinstance(data.get("meta_seo"), dict) else data.get("meta_seo", "{}"),
            data.get("image_prompt", ""),
            data.get("og_image_svg", ""),
            data.get("seo_score", 100),
            json.dumps(data.get("seo_issues", [])) if isinstance(data.get("seo_issues"), list) else data.get("seo_issues", "[]"),
            data.get("status", "draft"),
            data.get("github_commit_sha"),
            data.get("github_pr_url"),
            data.get("github_pr_number"),
            data.get("error_message"),
            data.get("published_at"),
            now
        ))
        conn.commit()
        return cursor.lastrowid

def get_post_by_slug(project_id: int, slug: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, proj.name as project_name, proj.github_repo
            FROM posts p
            JOIN projects proj ON p.project_id = proj.id
            WHERE p.project_id = ? AND p.slug = ?
        """, (project_id, slug))
        row = cursor.fetchone()
        return dict(row) if row else None

def increment_post_views(post_id: int, ip_hash: str = ""):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))
        if ip_hash:
            cursor.execute("INSERT INTO post_views (post_id, viewed_at, ip_hash) VALUES (?, ?, ?)", (post_id, now, ip_hash))
        conn.commit()

def update_post_content(post_id: int, title: str, excerpt: str, content_markdown: str, frontmatter_yaml: str, tags: list):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE posts SET
                title = ?,
                excerpt = ?,
                content_markdown = ?,
                frontmatter_yaml = ?,
                tags = ?
            WHERE id = ?
        """, (
            title,
            excerpt,
            content_markdown,
            frontmatter_yaml,
            json.dumps(tags) if isinstance(tags, list) else tags,
            post_id
        ))
        conn.commit()

def get_post(post_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, proj.name as project_name, proj.github_repo
            FROM posts p
            JOIN projects proj ON p.project_id = proj.id
            WHERE p.id = ?
        """, (post_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def list_posts(project_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if project_id:
            cursor.execute("""
                SELECT p.*, proj.name as project_name, proj.github_repo
                FROM posts p
                JOIN projects proj ON p.project_id = proj.id
                WHERE p.project_id = ?
                ORDER BY p.id DESC LIMIT ?
            """, (project_id, limit))
        else:
            cursor.execute("""
                SELECT p.*, proj.name as project_name, proj.github_repo
                FROM posts p
                JOIN projects proj ON p.project_id = proj.id
                ORDER BY p.id DESC LIMIT ?
            """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_recent_post_titles(project_id: int, limit: int = 30) -> List[str]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM posts WHERE project_id = ? ORDER BY id DESC LIMIT ?", (project_id, limit))
        return [row["title"] for row in cursor.fetchall()]

def update_post_status(post_id: int, status: str, commit_sha: str = None, pr_url: str = None, pr_number: int = None, error: str = None):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        published_at = now if status == "published" else None
        cursor.execute("""
            UPDATE posts SET
                status = ?,
                github_commit_sha = COALESCE(?, github_commit_sha),
                github_pr_url = COALESCE(?, github_pr_url),
                github_pr_number = COALESCE(?, github_pr_number),
                error_message = ?,
                published_at = COALESCE(?, published_at)
            WHERE id = ?
        """, (status, commit_sha, pr_url, pr_number, error, published_at, post_id))
        conn.commit()

# --- Logging & Audit ---

def log_event(message: str, level: str = "INFO", project_id: Optional[int] = None, post_id: Optional[int] = None, metadata: Optional[Dict] = None):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO system_logs (project_id, post_id, level, message, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            post_id,
            level,
            message,
            json.dumps(metadata or {}),
            now
        ))
        conn.commit()

def list_logs(limit: int = 100) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT l.*, p.name as project_name
            FROM system_logs l
            LEFT JOIN projects p ON l.project_id = p.id
            ORDER BY l.id DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

# --- Settings ---

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (key, value, now))
        conn.commit()

def get_all_settings() -> Dict[str, str]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in cursor.fetchall()}

# --- Seed Sample Projects ---

def seed_demo_data():
    """Seed initial high-value sample projects if DB is empty."""
    projects = list_projects()
    if projects:
        return

    sample_projects = [
        {
            "name": "CloudScale DevOps Platform",
            "github_repo": "cloudscale-ops/documentation-portal",
            "github_branch": "main",
            "target_framework": "nextjs",
            "content_dir": "content/posts",
            "file_extension": ".mdx",
            "topic": "Kubernetes orchestration, Terraform automation, zero-trust cloud security, and CI/CD pipelines",
            "target_audience": "Senior Site Reliability Engineers, DevOps Leads, and Cloud Architects",
            "tone": "Deeply technical, architectural, clear, and accompanied by practical manifests or configs",
            "keywords": "kubernetes, terraform, gitops, ci/cd, cloud security, sre, docker",
            "author_name": "CloudScale Engineering",
            "publishing_mode": "pr",
            "publish_time": "09:00",
            "is_active": True
        },
        {
            "name": "AI Engineer Pulse",
            "github_repo": "ai-pulse-community/engineering-blog",
            "github_branch": "main",
            "target_framework": "astro",
            "content_dir": "src/content/blog",
            "file_extension": ".md",
            "topic": "LLM fine-tuning, RAG architecture, agentic AI workflows, vector databases, and AI eval frameworks",
            "target_audience": "AI Engineers, Machine Learning Researchers, and Full-Stack AI Builders",
            "tone": "Cutting-edge, insightful, benchmark-driven, and forward-looking",
            "keywords": "llm, agents, rag, vector database, prompt engineering, langchain, openai, gemini",
            "author_name": "AI Pulse Editorial",
            "publishing_mode": "pr",
            "publish_time": "08:30",
            "is_active": True
        },
        {
            "name": "Frontend Craftsmanship",
            "github_repo": "frontend-collective/dev-insights",
            "github_branch": "main",
            "target_framework": "docusaurus",
            "content_dir": "blog",
            "file_extension": ".md",
            "topic": "React 19 Server Components, Web Vitals performance, Tailwind CSS v4, TypeScript 5.x patterns",
            "target_audience": "Modern Frontend Developers, Tech Leads, and Web Performance Engineers",
            "tone": "Clean, educational, benchmarked, with practical code examples",
            "keywords": "react, typescript, nextjs, web vitals, performance, css, javascript",
            "author_name": "Frontend Collective",
            "publishing_mode": "direct",
            "publish_time": "10:00",
            "is_active": True
        }
    ]

    for p in sample_projects:
        create_project(p)

    log_event("Initialized database and seeded starter projects.", "INFO")

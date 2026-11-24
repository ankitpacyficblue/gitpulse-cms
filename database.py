"""
GitPulse CMS - SQLite Database Layer
Handles persistent storage with WAL mode, robust transaction management, and ORM-like accessors.
"""

import sqlite3
import json
import os
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
        
        # Clients / Organizations Table (Multi-tenant grouping)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_email TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """)

        # Projects Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
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
        if "client_id" not in project_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN client_id INTEGER REFERENCES clients(id)")
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

        # Users: account-era columns
        if "email" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
        if "is_active" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "is_platform_admin" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_platform_admin INTEGER NOT NULL DEFAULT 0")

        # Accounts, memberships, per-account WhatsApp and CRM tables
        import crm_store
        crm_store.init_schema(conn)

        conn.commit()

# --- Client / Multi-Tenant Operations ---

def list_clients() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, 
                   COUNT(p.id) as total_projects
            FROM clients c
            LEFT JOIN projects p ON c.id = p.client_id
            GROUP BY c.id
            ORDER BY c.name ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_client(client_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_client(name: str, contact_email: str = "") -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO clients (name, contact_email, created_at) VALUES (?, ?, ?)",
                       (name.strip(), contact_email.strip(), now))
        conn.commit()
        client_id = cursor.lastrowid

        # Sync to Supabase if configured
        try:
            sb = get_supabase_client()
            if sb.is_configured():
                sb.table("clients").insert({"name": name.strip(), "contact_email": contact_email.strip()})
        except Exception:
            pass

        return client_id

def delete_client(client_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE projects SET client_id = NULL WHERE client_id = ?", (client_id,))
        cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        conn.commit()
        return cursor.rowcount > 0

# --- Project Operations ---

def list_projects(client_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT p.*, 
                   c.name as client_name,
                   COUNT(post.id) as total_posts,
                   SUM(CASE WHEN post.status = 'published' THEN 1 ELSE 0 END) as published_posts
            FROM projects p
            LEFT JOIN clients c ON p.client_id = c.id
            LEFT JOIN posts post ON p.id = post.project_id
        """
        params = []
        if client_id is not None:
            query += " WHERE p.client_id = ?"
            params.append(client_id)
        query += " GROUP BY p.id ORDER BY p.id DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def get_project(project_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, c.name as client_name
            FROM projects p
            LEFT JOIN clients c ON p.client_id = c.id
            WHERE p.id = ?
        """, (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_project(data: Dict[str, Any]) -> int:
    framework = data.get("target_framework", "generic")
    preset = FRAMEWORK_PRESETS.get(framework, FRAMEWORK_PRESETS["generic"])
    
    now = datetime.utcnow().isoformat()
    content_dir = data.get("content_dir") or preset["content_dir"]
    file_extension = data.get("file_extension") or preset["file_extension"]
    frontmatter_template = data.get("frontmatter_template") or preset["frontmatter_template"]

    raw_client_id = data.get("client_id")
    client_id = None
    if raw_client_id not in (None, "", "null"):
        try:
            client_id = int(raw_client_id)
        except (ValueError, TypeError):
            client_id = None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO projects (
                client_id, name, github_repo, github_branch, github_token,
                target_framework, content_dir, file_extension,
                frontmatter_template, topic, target_audience, tone,
                keywords, author_name, publishing_mode, publish_time,
                is_active, auto_publish, forbidden_words, webhook_secret,
                zero_redeploy_enabled, blog_page_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_id,
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
        project_id = cursor.lastrowid

        # Async or direct write to Supabase cloud if active
        try:
            sb = get_supabase_client()
            if sb.is_configured():
                sb.table("projects").insert({
                    "name": data.get("name", "New Project"),
                    "github_repo": data.get("github_repo", "").strip(),
                    "github_branch": data.get("github_branch", "main").strip(),
                    "target_framework": framework,
                    "content_dir": content_dir.strip("/"),
                    "file_extension": file_extension,
                    "frontmatter_template": frontmatter_template,
                    "topic": data.get("topic", "").strip(),
                    "target_audience": data.get("target_audience", "Developers and Tech Enthusiasts").strip(),
                    "tone": data.get("tone", "Authoritative, practical, and engaging").strip(),
                    "keywords": data.get("keywords", "").strip(),
                    "author_name": data.get("author_name", "Editorial Team").strip(),
                    "publishing_mode": data.get("publishing_mode", "pr"),
                    "publish_time": data.get("publish_time", "09:00").strip(),
                    "is_active": bool(data.get("is_active", True)),
                    "auto_publish": bool(data.get("auto_publish", True)),
                    "forbidden_words": data.get("forbidden_words", "").strip(),
                    "webhook_secret": data.get("webhook_secret", "").strip(),
                    "zero_redeploy_enabled": bool(data.get("zero_redeploy_enabled", True)),
                    "blog_page_path": data.get("blog_page_path", "public/blog/index.html").strip()
                })
        except Exception:
            pass

        return project_id

def update_project(project_id: int, data: Dict[str, Any]) -> bool:
    now = datetime.utcnow().isoformat()
    raw_client_id = data.get("client_id")
    client_id = None
    if raw_client_id not in (None, "", "null"):
        try:
            client_id = int(raw_client_id)
        except (ValueError, TypeError):
            client_id = None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE projects SET
                client_id = COALESCE(?, client_id),
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
            client_id,
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

# --- Supabase Cloud PostgreSQL Sync & Bridge ---

def get_supabase_client():
    from engine.supabase_client import SupabaseClient
    url = os.environ.get("SUPABASE_URL") or get_setting("supabase_url", "https://suvmyyonlqyipzgnmony.supabase.co")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or get_setting("supabase_key", "")
    return SupabaseClient(url=url, key=key)

def test_supabase_connection() -> Dict[str, Any]:
    sb = get_supabase_client()
    ok, msg = sb.test_connection()
    return {
        "configured": sb.is_configured(),
        "url": sb.base_url,
        "connected": ok,
        "message": msg
    }

def sync_all_to_supabase() -> Dict[str, Any]:
    sb = get_supabase_client()
    if not sb.is_configured():
        return {"success": False, "error": "Supabase key is not configured. Please enter your Service Role or Anon key in Settings."}

    synced_clients = 0
    synced_projects = 0
    synced_posts = 0

    try:
        # Sync clients
        for c in list_clients():
            sb.table("clients").insert({
                "name": c["name"],
                "contact_email": c.get("contact_email", "")
            })
            synced_clients += 1

        # Sync projects
        for p in list_projects():
            sb.table("projects").insert({
                "name": p["name"],
                "github_repo": p["github_repo"],
                "github_branch": p.get("github_branch", "main"),
                "target_framework": p.get("target_framework", "nextjs"),
                "content_dir": p.get("content_dir", "content/posts"),
                "file_extension": p.get("file_extension", ".mdx"),
                "frontmatter_template": p.get("frontmatter_template", ""),
                "topic": p.get("topic", ""),
                "target_audience": p.get("target_audience", ""),
                "tone": p.get("tone", ""),
                "keywords": p.get("keywords", ""),
                "author_name": p.get("author_name", "Editorial Team"),
                "publishing_mode": p.get("publishing_mode", "pr"),
                "publish_time": p.get("publish_time", "09:00"),
                "is_active": bool(p.get("is_active", 1)),
                "auto_publish": bool(p.get("auto_publish", 1)),
                "forbidden_words": p.get("forbidden_words", ""),
                "webhook_secret": p.get("webhook_secret", ""),
                "zero_redeploy_enabled": bool(p.get("zero_redeploy_enabled", 1)),
                "blog_page_path": p.get("blog_page_path", "public/blog/index.html")
            })
            synced_projects += 1

        # Sync posts
        for post in list_posts(limit=100):
            sb.table("posts").insert({
                "project_id": post["project_id"],
                "title": post["title"],
                "slug": post["slug"],
                "excerpt": post.get("excerpt", ""),
                "content_markdown": post.get("content_markdown", ""),
                "frontmatter_yaml": post.get("frontmatter_yaml", ""),
                "target_path": post.get("target_path", ""),
                "status": post.get("status", "draft"),
                "seo_score": post.get("seo_score", 100),
                "github_commit_sha": post.get("github_commit_sha"),
                "github_pr_url": post.get("github_pr_url")
            })
            synced_posts += 1

        return {
            "success": True,
            "message": f"Successfully synced {synced_clients} clients, {synced_projects} projects, and {synced_posts} posts to Supabase cloud."
        }
    except Exception as e:
        return {"success": False, "error": f"Supabase sync failed: {str(e)}"}

# ====================================================================
# WhatsApp Automation & CRM Engine (ArnasDon/wacrm Architecture)
# ====================================================================

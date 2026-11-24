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

        # --- WhatsApp Automation & CRM Tables (ArnasDon/wacrm Architecture) ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            phone_number_id TEXT NOT NULL DEFAULT '',
            waba_id TEXT NOT NULL DEFAULT '',
            access_token TEXT NOT NULL DEFAULT '',
            verify_token TEXT NOT NULL DEFAULT 'gitpulse_webhook_verify',
            business_name TEXT NOT NULL DEFAULT 'GitPulse WhatsApp',
            phone_number TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT DEFAULT '',
            tags TEXT NOT NULL DEFAULT '["Lead"]',
            notes TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'open',
            assigned_to TEXT NOT NULL DEFAULT 'Support Team',
            unread_count INTEGER NOT NULL DEFAULT 0,
            last_message_at TEXT,
            last_message_preview TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            direction TEXT NOT NULL,
            message_type TEXT NOT NULL DEFAULT 'text',
            body TEXT NOT NULL,
            media_url TEXT DEFAULT '',
            wa_message_id TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'sent',
            error_message TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            value REAL NOT NULL DEFAULT 0.0,
            currency TEXT NOT NULL DEFAULT 'USD',
            stage TEXT NOT NULL DEFAULT 'lead',
            expected_close TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            template_body TEXT NOT NULL,
            target_tag TEXT NOT NULL DEFAULT 'all',
            total_recipients INTEGER NOT NULL DEFAULT 0,
            sent_count INTEGER NOT NULL DEFAULT 0,
            delivered_count INTEGER NOT NULL DEFAULT 0,
            read_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'draft',
            scheduled_at TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS automations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            trigger_keyword TEXT DEFAULT '',
            action_type TEXT NOT NULL DEFAULT 'send_message',
            message_template TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            executions_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # Performance indexes for WhatsApp CRM
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts (phone)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_contact ON conversations (contact_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_wa_id ON messages (wa_message_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals (stage)")

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
    seed_whatsapp_demo_data()

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

# --- WhatsApp Meta Cloud API Configuration ---

def get_whatsapp_config(client_id: Optional[int] = None) -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if client_id:
            cursor.execute("SELECT * FROM whatsapp_configs WHERE client_id = ? ORDER BY id DESC LIMIT 1", (client_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        cursor.execute("SELECT * FROM whatsapp_configs WHERE client_id IS NULL ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
        # Default fallback
        return {
            "id": None,
            "client_id": client_id,
            "phone_number_id": "109876543210123",
            "waba_id": "987654321098765",
            "access_token": "mock_meta_wa_token",
            "verify_token": "gitpulse_webhook_verify",
            "business_name": "GitPulse WhatsApp Business",
            "phone_number": "+1 (555) 019-2834",
            "is_active": 1
        }

def save_whatsapp_config(phone_number_id: str, access_token: str, waba_id: str = "",
                         verify_token: str = "gitpulse_webhook_verify",
                         business_name: str = "GitPulse WhatsApp",
                         phone_number: str = "", client_id: Optional[int] = None) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM whatsapp_configs WHERE client_id IS ?", (client_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute("""
            UPDATE whatsapp_configs SET 
                phone_number_id = ?, waba_id = ?, access_token = ?, verify_token = ?,
                business_name = ?, phone_number = ?, is_active = 1, updated_at = ?
            WHERE id = ?
            """, (phone_number_id.strip(), waba_id.strip(), access_token.strip(),
                  verify_token.strip(), business_name.strip(), phone_number.strip(), now, row["id"]))
            conn.commit()
            return row["id"]
        else:
            cursor.execute("""
            INSERT INTO whatsapp_configs (client_id, phone_number_id, waba_id, access_token,
                                          verify_token, business_name, phone_number, is_active,
                                          created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (client_id, phone_number_id.strip(), waba_id.strip(), access_token.strip(),
                  verify_token.strip(), business_name.strip(), phone_number.strip(), now, now))
            conn.commit()
            return cursor.lastrowid

# --- Contacts Management (CRM Audience) ---

def list_contacts(client_id: Optional[int] = None, search: str = "", tag: str = "") -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM contacts WHERE 1=1"
        params = []
        if client_id is not None:
            query += " AND (client_id = ? OR client_id IS NULL)"
            params.append(client_id)
        if search:
            query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])
        if tag:
            query += " AND tags LIKE ?"
            params.append(f"%{tag}%")
        query += " ORDER BY updated_at DESC, id DESC"
        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            try:
                d["tags"] = json.loads(d.get("tags") or "[]")
            except Exception:
                d["tags"] = ["Lead"]
            results.append(d)
        return results

def get_contact(contact_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:
            d["tags"] = ["Lead"]
        return d

def get_contact_by_phone(phone: str, client_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    clean_phone = phone.strip().replace(" ", "").replace("-", "")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contacts WHERE REPLACE(REPLACE(phone, ' ', ''), '-', '') = ? LIMIT 1", (clean_phone,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:
            d["tags"] = ["Lead"]
        return d

def create_contact(name: str, phone: str, email: str = "", tags: Any = None,
                   notes: str = "", client_id: Optional[int] = None) -> int:
    now = datetime.utcnow().isoformat()
    if tags is None:
        tags_json = '["Lead"]'
    elif isinstance(tags, list):
        tags_json = json.dumps(tags)
    else:
        tags_json = json.dumps([str(tags)])

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO contacts (client_id, name, phone, email, tags, notes, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (client_id, name.strip(), phone.strip(), email.strip(), tags_json, notes.strip(), now, now))
        conn.commit()
        return cursor.lastrowid

def update_contact(contact_id: int, **kwargs) -> bool:
    now = datetime.utcnow().isoformat()
    allowed = ["name", "phone", "email", "tags", "notes", "status"]
    fields = []
    params = []
    for k, v in kwargs.items():
        if k in allowed:
            if k == "tags" and isinstance(v, list):
                v = json.dumps(v)
            fields.append(f"{k} = ?")
            params.append(v)
    if not fields:
        return False
    fields.append("updated_at = ?")
    params.append(now)
    params.append(contact_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE contacts SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0

def delete_contact(contact_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        return cursor.rowcount > 0

# --- Conversations & Live Inbox Management ---

def list_conversations(client_id: Optional[int] = None, status: str = "") -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
        SELECT conv.*, 
               c.name as contact_name, 
               c.phone as contact_phone, 
               c.email as contact_email,
               c.tags as contact_tags
        FROM conversations conv
        JOIN contacts c ON conv.contact_id = c.id
        WHERE 1=1
        """
        params = []
        if client_id is not None:
            query += " AND (conv.client_id = ? OR conv.client_id IS NULL)"
            params.append(client_id)
        if status:
            query += " AND conv.status = ?"
            params.append(status)
        query += " ORDER BY conv.last_message_at DESC, conv.id DESC"
        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            try:
                d["contact_tags"] = json.loads(d.get("contact_tags") or "[]")
            except Exception:
                d["contact_tags"] = ["Lead"]
            results.append(d)
        return results

def get_conversation(conversation_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT conv.*, 
               c.name as contact_name, 
               c.phone as contact_phone, 
               c.email as contact_email,
               c.tags as contact_tags
        FROM conversations conv
        JOIN contacts c ON conv.contact_id = c.id
        WHERE conv.id = ?
        """, (conversation_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["contact_tags"] = json.loads(d.get("contact_tags") or "[]")
        except Exception:
            d["contact_tags"] = ["Lead"]
        return d

def get_or_create_conversation(contact_id: int, client_id: Optional[int] = None) -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM conversations WHERE contact_id = ? LIMIT 1", (contact_id,))
        row = cursor.fetchone()
        if row:
            return get_conversation(row["id"])
        
        now = datetime.utcnow().isoformat()
        cursor.execute("""
        INSERT INTO conversations (client_id, contact_id, status, assigned_to, unread_count,
                                   last_message_at, last_message_preview, created_at, updated_at)
        VALUES (?, ?, 'open', 'Team', 0, ?, 'New conversation', ?, ?)
        """, (client_id, contact_id, now, now, now))
        conn.commit()
        return get_conversation(cursor.lastrowid)

def mark_conversation_read(conversation_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE conversations SET unread_count = 0 WHERE id = ?", (conversation_id,))
        conn.commit()
        return cursor.rowcount > 0

# --- Messages (WhatsApp Chat History) ---

def list_messages(conversation_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM messages 
        WHERE conversation_id = ? 
        ORDER BY id ASC 
        LIMIT ?
        """, (conversation_id, limit))
        return [dict(row) for row in cursor.fetchall()]

def create_message(conversation_id: int, contact_id: int, direction: str, body: str,
                   message_type: str = "text", media_url: str = "", wa_message_id: str = "",
                   status: str = "sent", client_id: Optional[int] = None,
                   error_message: str = "") -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO messages (conversation_id, client_id, contact_id, direction, message_type,
                              body, media_url, wa_message_id, status, error_message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (conversation_id, client_id, contact_id, direction, message_type,
              body.strip(), media_url.strip(), wa_message_id.strip(), status, error_message, now))
        msg_id = cursor.lastrowid

        # Update conversation metadata
        preview = (body[:60] + "...") if len(body) > 60 else body
        if direction == "inbound":
            cursor.execute("""
            UPDATE conversations SET 
                last_message_at = ?, 
                last_message_preview = ?,
                unread_count = unread_count + 1,
                updated_at = ?
            WHERE id = ?
            """, (now, preview, now, conversation_id))
        else:
            cursor.execute("""
            UPDATE conversations SET 
                last_message_at = ?, 
                last_message_preview = ?,
                updated_at = ?
            WHERE id = ?
            """, (now, preview, now, conversation_id))
        conn.commit()
        return msg_id

def update_message_status(wa_message_id: str, status: str) -> bool:
    if not wa_message_id:
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET status = ? WHERE wa_message_id = ?", (status, wa_message_id))
        conn.commit()
        return cursor.rowcount > 0

# --- Deals & Sales Pipeline Kanban ---

def list_deals(client_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
        SELECT d.*, 
               c.name as contact_name, 
               c.phone as contact_phone,
               c.email as contact_email
        FROM deals d
        LEFT JOIN contacts c ON d.contact_id = c.id
        WHERE 1=1
        """
        params = []
        if client_id is not None:
            query += " AND (d.client_id = ? OR d.client_id IS NULL)"
            params.append(client_id)
        query += " ORDER BY d.id DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def create_deal(title: str, value: float, stage: str = "lead", contact_id: Optional[int] = None,
                currency: str = "USD", expected_close: str = "", notes: str = "",
                client_id: Optional[int] = None) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO deals (client_id, contact_id, title, value, currency, stage, expected_close, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (client_id, contact_id, title.strip(), float(value), currency, stage, expected_close, notes.strip(), now, now))
        conn.commit()
        return cursor.lastrowid

def update_deal_stage(deal_id: int, stage: str) -> bool:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE deals SET stage = ?, updated_at = ? WHERE id = ?", (stage.lower().strip(), now, deal_id))
        conn.commit()
        return cursor.rowcount > 0

def delete_deal(deal_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
        conn.commit()
        return cursor.rowcount > 0

# --- Broadcast Campaigns ---

def list_broadcasts(client_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM broadcasts WHERE 1=1"
        params = []
        if client_id is not None:
            query += " AND (client_id = ? OR client_id IS NULL)"
            params.append(client_id)
        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def get_broadcast(broadcast_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM broadcasts WHERE id = ?", (broadcast_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_broadcast(name: str, template_body: str, target_tag: str = "all",
                     scheduled_at: str = "", client_id: Optional[int] = None) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO broadcasts (client_id, name, template_body, target_tag, total_recipients,
                                sent_count, delivered_count, read_count, status, scheduled_at, created_at)
        VALUES (?, ?, ?, ?, 0, 0, 0, 0, 'draft', ?, ?)
        """, (client_id, name.strip(), template_body.strip(), target_tag.strip(), scheduled_at, now))
        conn.commit()
        return cursor.lastrowid

def update_broadcast_stats(broadcast_id: int, total: int = 0, sent: int = 0,
                           delivered: int = 0, read: int = 0, status: str = "completed") -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE broadcasts SET 
            total_recipients = ?, sent_count = ?, delivered_count = ?, read_count = ?, status = ?
        WHERE id = ?
        """, (total, sent, delivered, read, status, broadcast_id))
        conn.commit()
        return cursor.rowcount > 0

# --- No-Code Automations Engine ---

def list_automations(client_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM automations WHERE 1=1"
        params = []
        if client_id is not None:
            query += " AND (client_id = ? OR client_id IS NULL)"
            params.append(client_id)
        query += " ORDER BY id ASC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def create_automation(name: str, trigger_type: str, message_template: str,
                      trigger_keyword: str = "", action_type: str = "send_message",
                      is_active: bool = True, client_id: Optional[int] = None) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO automations (client_id, name, trigger_type, trigger_keyword, action_type,
                                message_template, is_active, executions_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (client_id, name.strip(), trigger_type.strip(), trigger_keyword.strip().lower(),
              action_type.strip(), message_template.strip(), 1 if is_active else 0, now, now))
        conn.commit()
        return cursor.lastrowid

def toggle_automation(automation_id: int, is_active: bool) -> bool:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE automations SET is_active = ?, updated_at = ? WHERE id = ?",
                       (1 if is_active else 0, now, automation_id))
        conn.commit()
        return cursor.rowcount > 0

def delete_automation(automation_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM automations WHERE id = ?", (automation_id,))
        conn.commit()
        return cursor.rowcount > 0

def increment_automation_execution(automation_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE automations SET executions_count = executions_count + 1 WHERE id = ?", (automation_id,))
        conn.commit()
        return cursor.rowcount > 0

# --- Seed WhatsApp CRM Sample Data ---

def seed_whatsapp_demo_data():
    """Seed initial high-value WhatsApp CRM contacts, chats, deals, and automations if empty."""
    contacts = list_contacts()
    if contacts:
        return

    # 1. Config
    save_whatsapp_config(
        phone_number_id="109876543210123",
        access_token="mock_meta_wa_token",
        waba_id="987654321098765",
        verify_token="gitpulse_webhook_verify",
        business_name="GitPulse Official WhatsApp",
        phone_number="+1 (555) 019-2834"
    )

    # 2. Contacts
    c1 = create_contact(
        name="Sarah Jenkins",
        phone="+14155552671",
        email="sarah.jenkins@cloudscale.io",
        tags=["VIP", "Customer"],
        notes="VP Growth @ CloudScale DevOps. Looking to automate publishing across 4 engineering blogs."
    )
    c2 = create_contact(
        name="Alex Rivera",
        phone="+16465558912",
        email="arivera@aipulse.dev",
        tags=["Customer", "Lead"],
        notes="Head of Engineering @ AI Pulse. Wants MDX + Next.js automated GitHub pipeline."
    )
    c3 = create_contact(
        name="Michael Chang",
        phone="+12065554321",
        email="m.chang@devflow.tech",
        tags=["Lead", "Trial"],
        notes="Requested a live demo of the zero-redeploy 1-click blog embed."
    )
    c4 = create_contact(
        name="Elena Rostova",
        phone="+447911123456",
        email="elena@healthops.co.uk",
        tags=["Lead"],
        notes="Inbound lead from the AI & Longevity blog post."
    )

    # 3. Conversations & Messages
    conv1 = get_or_create_conversation(c1)
    create_message(conv1["id"], c1, "inbound", "Hi GitPulse team! We loved the automated Kubernetes blog post published today. Can we customize the author bio?", status="read", wa_message_id="wamid.HBgLMTQxNTU1NTI2NzEVFQIAEhggM0E0Nzc4N0Y")
    create_message(conv1["id"], c1, "outbound", "Hi Sarah! Absolutely! You can update the author_name directly in the Connected Repos tab or through your repository frontmatter template. Would you like a demo of the 1-click blog embed?", status="read", wa_message_id="wamid.HBgLMTQxNTU1NTI2NzEVFQIAEhggM0E0Nzc4OEY")
    create_message(conv1["id"], c1, "inbound", "That would be fantastic! Also, could you share the pricing for adding 3 more team repositories?", status="delivered", wa_message_id="wamid.HBgLMTQxNTU1NTI2NzEVFQIAEhggM0E0Nzc4OUY")

    conv2 = get_or_create_conversation(c2)
    create_message(conv2["id"], c2, "inbound", "pricing", status="read", wa_message_id="wamid.HBgLMTY0NjU1NTg5MTIVFQIAEhggM0E0Nzc5MEY")
    create_message(conv2["id"], c2, "outbound", "Hello Alex! 🚀 GitPulse CMS + WhatsApp Automation pricing:\n• Starter: $49/mo (3 Repos, 500 WA Messages)\n• Pro: $149/mo (10 Repos, Unlimited WA CRM)\n• Enterprise: Custom SLA & Dedicated Supabase DB.\nReply with 'demo' to schedule a live walkthrough!", status="read", wa_message_id="wamid.HBgLMTY0NjU1NTg5MTIVFQIAEhggM0E0Nzc5MUY")

    # 4. Pipeline Deals (Kanban)
    create_deal(title="CloudScale 10-Repo Enterprise Expansion", value=12500.0, stage="proposal", contact_id=c1, currency="USD", expected_close="2026-12-15", notes="Contract review in progress with legal team.")
    create_deal(title="AI Pulse Pro Plan & Custom MDX Pipeline", value=4200.0, stage="negotiation", contact_id=c2, currency="USD", expected_close="2026-11-30", notes="Finalizing annual billing agreement.")
    create_deal(title="DevFlow 1-Click Blog Embed Setup", value=1800.0, stage="qualified", contact_id=c3, currency="USD", expected_close="2026-12-05", notes="Demo scheduled for Thursday 2 PM.")
    create_deal(title="HealthOps SaaS Content Trial", value=950.0, stage="lead", contact_id=c4, currency="USD", expected_close="2026-12-20", notes="Subscribed to weekly longevity updates.")
    create_deal(title="Q3 Closed: CloudScale Starter Implementation", value=3600.0, stage="won", contact_id=c1, currency="USD", expected_close="2026-10-01", notes="Successfully deployed and running daily.")

    # 5. Broadcasts
    b_id = create_broadcast(
        name="Q4 Product Launch: Instant WhatsApp Publishing & Next.js 15",
        template_body="🎉 Huge update! GitPulse now supports instant WhatsApp Broadcasts and Next.js 15 App Router blog automation. Read the announcement: https://gitpulse-cms.vercel.app",
        target_tag="all"
    )
    update_broadcast_stats(b_id, total=4, sent=4, delivered=4, read=3, status="completed")

    # 6. Automations
    create_automation(
        name="New Inbound Lead Welcome Greeting",
        trigger_type="welcome",
        trigger_keyword="",
        action_type="send_message",
        message_template="Hi {{name}}! 👋 Welcome to GitPulse. Thanks for reaching out! How can our automated GitHub blog publishing and CRM help your company grow?",
        is_active=True
    )
    create_automation(
        name="Instant Pricing & Plans Auto-Responder",
        trigger_type="keyword",
        trigger_keyword="pricing, price, quote, cost, plans, plan",
        action_type="send_message",
        message_template="Hey! 📊 GitPulse pricing starts at $49/mo for 3 connected repos and WhatsApp automation. Check it out at https://gitpulse-cms.vercel.app or reply 'demo' to book a live walkthrough!",
        is_active=True
    )
    create_automation(
        name="Auto-Broadcast Published Blog to WhatsApp VIPs",
        trigger_type="blog_publish",
        trigger_keyword="",
        action_type="send_message",
        message_template="📰 *New Article Live*: '{{title}}' is now published on GitHub!\n\nRead the full post here: {{url}}",
        is_active=True
    )

    log_event("Initialized WhatsApp CRM and seeded contacts, chats, deals, and automations.", "INFO")


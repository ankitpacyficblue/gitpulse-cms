"""
GitPulse CMS - REST API Controller
Handles JSON endpoints for project management, post lifecycle,
GitHub verification, manual triggers, and system configuration.
"""

import json
from typing import Dict, Any, Tuple, Optional
from database import (
    list_projects,
    get_project,
    create_project,
    update_project,
    delete_project,
    list_posts,
    get_post,
    create_post,
    update_post_status,
    list_logs,
    get_all_settings,
    set_setting,
    get_setting
)
from config import FRAMEWORK_PRESETS, DEFAULT_AI_PROVIDER
from engine.pipeline import run_publication_pipeline
from engine.github_client import GitHubClient
from engine.auth import (
    authenticate_user,
    revoke_session,
    validate_session,
    update_user_password,
    verify_password,
    get_user_by_id,
    get_user_by_username
)
from engine.totp import (
    generate_totp_secret,
    verify_totp_code,
    get_totp_uri
)
from engine.templates_embed import generate_one_time_blog_html
from engine.seo_linter import lint_article
from database import update_post_content, get_connection
from scheduler.cron_worker import scheduler

def handle_api_request(
    method: str,
    path: str,
    query_params: Dict[str, str],
    body_data: Optional[Dict[str, Any]],
    current_user: Optional[Dict[str, Any]] = None,
    client_ip: str = "127.0.0.1",
    user_agent: str = ""
) -> Tuple[int, Dict[str, Any]]:
    """
    Route API requests and return (status_code, json_dict).
    Guards protected administrative endpoints with session verification.
    """
    body = body_data or {}

    # --- Public Authentication Endpoints ---

    if path == "/api/auth/login" and method == "POST":
        username = body.get("username", "")
        password = body.get("password", "")
        totp_code = body.get("totp_code", "").strip()

        if not username or not password:
            return 400, {"error": "Username and password are required."}

        # Check if user has TOTP 2FA enabled
        target_user = get_user_by_username(username)
        if target_user and target_user.get("totp_enabled") and not totp_code:
            # First phase: verify password before asking for TOTP
            if not verify_password(password, target_user["salt"], target_user["password_hash"]):
                return 401, {"error": "Invalid username or password."}
            return 200, {
                "requires_2fa": True,
                "message": "Enter the 6-digit code from your authenticator app to complete sign-in."
            }

        if target_user and target_user.get("totp_enabled") and totp_code:
            if not verify_totp_code(target_user["totp_secret"], totp_code):
                return 401, {"error": "Invalid 2-Factor Authentication code."}

        ok, token, user_dict, err = authenticate_user(username, password, client_ip, user_agent)
        if not ok:
            return 401, {"error": err or "Authentication failed.", "locked": "locked" in (err or "").lower()}

        return 200, {
            "token": token,
            "user": user_dict,
            "message": "Login successful."
        }

    if path == "/api/auth/logout" and method == "POST":
        token = body.get("token") or (current_user.get("token") if current_user else None)
        if token:
            revoke_session(token)
        return 200, {"message": "Logged out successfully."}

    # Public presets (for UI initialization)
    if path == "/api/presets" and method == "GET":
        return 200, FRAMEWORK_PRESETS

    # --- Protected Endpoints (Require Authentication) ---
    if not current_user:
        return 401, {"error": "Authentication required. Please log in.", "code": "UNAUTHORIZED"}

    # Current user info
    if path == "/api/auth/me" and method == "GET":
        u = get_user_by_id(current_user["id"])
        full_u = get_user_by_username(u["username"])
        return 200, {
            "user": {
                "id": u["id"],
                "username": u["username"],
                "role": u["role"],
                "totp_enabled": bool(full_u.get("totp_enabled"))
            }
        }

    # 2FA Management Endpoints
    if path == "/api/auth/2fa/setup" and method == "GET":
        new_secret = generate_totp_secret()
        uri = get_totp_uri(current_user["username"], new_secret)
        return 200, {"secret": new_secret, "otpauth_uri": uri}

    if path == "/api/auth/2fa/enable" and method == "POST":
        secret = body.get("secret", "")
        code = body.get("code", "")
        if not verify_totp_code(secret, code):
            return 400, {"error": "Verification failed: 6-digit code did not match."}

        with get_connection() as conn:
            conn.execute("UPDATE users SET totp_secret = ?, totp_enabled = 1 WHERE id = ?", (secret, current_user["id"]))
            conn.commit()
        return 200, {"message": "Two-Factor Authentication (2FA) successfully activated!"}

    if path == "/api/auth/2fa/disable" and method == "POST":
        password = body.get("password", "")
        u = get_user_by_id(current_user["id"])
        full_u = get_user_by_username(u["username"])
        if not verify_password(password, full_u["salt"], full_u["password_hash"]):
            return 400, {"error": "Invalid password."}

        with get_connection() as conn:
            conn.execute("UPDATE users SET totp_secret = '', totp_enabled = 0 WHERE id = ?", (current_user["id"],))
            conn.commit()
        return 200, {"message": "Two-Factor Authentication has been disabled."}

    # Change password
    if path == "/api/auth/change-password" and method == "POST":
        current_pw = body.get("current_password", "")
        new_pw = body.get("new_password", "")
        if not current_pw or not new_pw:
            return 400, {"error": "Current and new passwords are required."}
        if len(new_pw) < 8:
            return 400, {"error": "New password must be at least 8 characters long."}

        user_db = get_user_by_id(current_user["id"])
        full_user = get_user_by_username(user_db["username"])
        if not verify_password(current_pw, full_user["salt"], full_user["password_hash"]):
            return 400, {"error": "Current password is incorrect."}

        update_user_password(current_user["id"], new_pw)
        return 200, {"message": "Password changed successfully. Please log in again."}

    # System Status
    if path == "/api/status" and method == "GET":
        projects = list_projects()
        posts = list_posts(limit=100)
        published_count = sum(1 for p in posts if p.get("status") == "published")
        return 200, {
            "status": "online",
            "scheduler_active": scheduler.is_alive(),
            "projects_count": len(projects),
            "total_posts": len(posts),
            "published_posts": published_count,
            "ai_provider": get_setting("ai_provider", DEFAULT_AI_PROVIDER)
        }

    # Presets
    if path == "/api/presets" and method == "GET":
        return 200, FRAMEWORK_PRESETS

    # List & Create Projects
    if path == "/api/projects" and method == "GET":
        return 200, {"projects": list_projects()}

    if path == "/api/projects" and method == "POST":
        if not body.get("name") or not body.get("github_repo") or not body.get("topic"):
            return 400, {"error": "Missing required fields: 'name', 'github_repo', and 'topic' are mandatory."}
        project_id = create_project(body)
        return 201, {"id": project_id, "message": "Project registered successfully."}

    # Project Operations (by ID)
    if path.startswith("/api/projects/"):
        parts = path.strip("/").split("/")
        project_id_str = parts[2]
        if not project_id_str.isdigit():
            return 400, {"error": "Invalid project ID."}
        project_id = int(project_id_str)

        # GET /api/projects/:id
        if len(parts) == 3 and method == "GET":
            p = get_project(project_id)
            if not p:
                return 404, {"error": "Project not found."}
            return 200, p

        # PUT /api/projects/:id
        if len(parts) == 3 and method == "PUT":
            ok = update_project(project_id, body)
            if not ok:
                return 404, {"error": "Project not found or no changes made."}
            return 200, {"message": "Project updated successfully."}

        # DELETE /api/projects/:id
        if len(parts) == 3 and method == "DELETE":
            ok = delete_project(project_id)
            if not ok:
                return 404, {"error": "Project not found."}
            return 200, {"message": "Project deleted."}

        # POST /api/projects/:id/trigger (Run now)
        if len(parts) == 4 and parts[3] == "trigger" and method == "POST":
            force = body.get("force_publish", True)
            try:
                res = run_publication_pipeline(project_id, force_publish=force)
                return 200, res
            except Exception as e:
                return 500, {"error": str(e)}

        # POST /api/projects/:id/test-github
        if len(parts) == 4 and parts[3] == "test-github" and method == "POST":
            proj = get_project(project_id)
            if not proj:
                return 404, {"error": "Project not found."}
            token = proj.get("github_token") or get_setting("github_token", "")
            client = GitHubClient(token=token)
            ok, msg = client.test_connection(proj["github_repo"])
            return (200 if ok else 400), {"connected": ok, "message": msg}

        # POST /api/projects/:id/install-blog-page (Zero-Redeploy one-time installer)
        if len(parts) == 4 and parts[3] == "install-blog-page" and method == "POST":
            proj = get_project(project_id)
            if not proj:
                return 404, {"error": "Project not found."}
            token = proj.get("github_token") or get_setting("github_token", "")
            client = GitHubClient(token=token)
            page_path = proj.get("blog_page_path", "public/blog/index.html")
            cms_url = body.get("cms_base_url", "")
            html_content = generate_one_time_blog_html(project_id, proj["name"], cms_url)
            commit_msg = f"feat(blog): install zero-redeploy dynamic blog page at {page_path}"
            
            if not token or token == "mock":
                return 200, {
                    "success": True,
                    "path": page_path,
                    "commit_sha": "sim-install-commit-a1b2",
                    "html_preview": html_content[:300],
                    "message": f"Simulated zero-redeploy blog installer to {proj['github_repo']}:{page_path}."
                }
            
            ok, sha, err = client.commit_file(proj["github_repo"], page_path, html_content, proj["github_branch"], commit_msg)
            if ok:
                return 200, {
                    "success": True,
                    "path": page_path,
                    "commit_sha": sha,
                    "message": f"Successfully installed zero-redeploy blog to {proj['github_repo']} at {page_path}."
                }
            return 500, {"success": False, "error": err or "Failed to commit blog page."}

    # Posts Endpoints
    if path == "/api/posts" and method == "GET":
        proj_id = int(query_params.get("project_id")) if query_params.get("project_id") else None
        limit = int(query_params.get("limit", 50))
        return 200, {"posts": list_posts(project_id=proj_id, limit=limit)}

    if path.startswith("/api/posts/"):
        parts = path.strip("/").split("/")
        post_id_str = parts[2]
        if not post_id_str.isdigit():
            return 400, {"error": "Invalid post ID."}
        post_id = int(post_id_str)

        # GET /api/posts/:id
        if len(parts) == 3 and method == "GET":
            post = get_post(post_id)
            if not post:
                return 404, {"error": "Post not found."}
            return 200, post

        # PUT /api/posts/:id (Editorial Staging content update)
        if len(parts) == 3 and method == "PUT":
            post = get_post(post_id)
            if not post:
                return 404, {"error": "Post not found."}
            proj = get_project(post["project_id"])
            title = body.get("title", post["title"])
            excerpt = body.get("excerpt", post["excerpt"])
            content_markdown = body.get("content_markdown", post["content_markdown"])
            frontmatter_yaml = body.get("frontmatter_yaml", post["frontmatter_yaml"])
            tags = body.get("tags", post["tags"])
            
            update_post_content(post_id, title, excerpt, content_markdown, frontmatter_yaml, tags)
            lint = lint_article(title, excerpt, content_markdown, proj.get("forbidden_words", ""))
            
            with get_connection() as conn:
                conn.execute("UPDATE posts SET seo_score = ?, seo_issues = ? WHERE id = ?", (lint["score"], json.dumps(lint["issues"]), post_id))
                conn.commit()
            return 200, {"message": "Article updated in staging queue.", "seo_score": lint["score"], "seo_issues": lint["issues"]}

        # POST /api/posts/:id/approve (Approve & Publish staged article)
        if len(parts) == 4 and parts[3] == "approve" and method == "POST":
            post = get_post(post_id)
            if not post:
                return 404, {"error": "Post not found."}
            project = get_project(post["project_id"])
            token = project.get("github_token") or get_setting("github_token", "")
            client = GitHubClient(token=token)

            from engine.formatters import assemble_post_document
            full_doc = assemble_post_document(post["frontmatter_yaml"], post["content_markdown"])

            pub_res = client.publish_post(
                repo=project["github_repo"],
                branch=project["github_branch"],
                target_path=post["target_path"],
                file_content=full_doc,
                post_title=post["title"],
                post_excerpt=post["excerpt"],
                post_tags=json.loads(post["tags"]) if isinstance(post["tags"], str) else [],
                mode=project.get("publishing_mode", "pr")
            )

            if pub_res.get("success"):
                update_post_status(
                    post_id=post_id,
                    status="published",
                    commit_sha=pub_res.get("commit_sha"),
                    pr_url=pub_res.get("pr_url"),
                    pr_number=pub_res.get("pr_number")
                )
                return 200, {"success": True, "pub_result": pub_res, "message": "Article approved and published to GitHub!"}
            else:
                update_post_status(post_id=post_id, status="failed", error=pub_res.get("error"))
                return 500, {"success": False, "error": pub_res.get("error")}
            if not post:
                return 404, {"error": "Post not found."}
            return 200, post

        # POST /api/posts/:id/publish (Publish an existing post)
        if len(parts) == 4 and parts[3] == "publish" and method == "POST":
            post = get_post(post_id)
            if not post:
                return 404, {"error": "Post not found."}
            project = get_project(post["project_id"])
            token = project.get("github_token") or get_setting("github_token", "")
            client = GitHubClient(token=token)

            from engine.formatters import assemble_post_document
            full_doc = assemble_post_document(post["frontmatter_yaml"], post["content_markdown"])
            
            pub_res = client.publish_post(
                repo=project["github_repo"],
                branch=project["github_branch"],
                target_path=post["target_path"],
                file_content=full_doc,
                post_title=post["title"],
                post_excerpt=post["excerpt"],
                post_tags=json.loads(post["tags"]) if isinstance(post["tags"], str) else [],
                mode=project.get("publishing_mode", "pr")
            )

            if pub_res.get("success"):
                update_post_status(
                    post_id=post_id,
                    status="published",
                    commit_sha=pub_res.get("commit_sha"),
                    pr_url=pub_res.get("pr_url"),
                    pr_number=pub_res.get("pr_number")
                )
                return 200, {"success": True, "pub_result": pub_res}
            else:
                update_post_status(post_id=post_id, status="failed", error=pub_res.get("error"))
                return 500, {"success": False, "error": pub_res.get("error")}

    # System Logs
    if path == "/api/logs" and method == "GET":
        limit = int(query_params.get("limit", 60))
        return 200, {"logs": list_logs(limit=limit)}

    # Settings
    if path == "/api/settings" and method == "GET":
        return 200, get_all_settings()

    if path == "/api/settings" and method == "POST":
        for k, v in body.items():
            set_setting(k, str(v))
        return 200, {"message": "Settings updated successfully."}

    return 404, {"error": f"API endpoint {method} {path} not found."}

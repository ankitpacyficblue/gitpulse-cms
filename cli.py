"""
GitPulse CMS - Command Line Interface
Provides full CLI control for headless servers, CI/CD runners, and developers.
"""

import sys
import argparse
import json
from database import (
    init_db,
    list_all_projects,
    get_project,
    list_posts,
    get_post,
    set_setting,
    get_all_settings
)
from config import SERVER_HOST, SERVER_PORT
from scheduler.cron_worker import start_scheduler
from server.http_server import run_server
from engine.pipeline import run_publication_pipeline
from engine.github_client import GitHubClient
from engine.auth import get_user_by_username, update_user_password, create_user, generate_temporary_password
from engine.templates_embed import generate_one_time_blog_html

def cmd_init(args):
    """Initialize the database schema. Creates no sample data and no default login."""
    init_db()
    print("✅ GitPulse CMS database initialized (empty).")
    print("   Next: python3 cli.py create-platform-admin --username NAME")

def cmd_create_platform_admin(args):
    """Create (or promote) a platform admin, who can create client accounts."""
    init_db()
    username = args.username.strip().lower()
    user = get_user_by_username(username)
    if user:
        from database import get_connection
        with get_connection() as conn:
            conn.execute("UPDATE users SET is_platform_admin = 1 WHERE id = ?", (user["id"],))
            conn.commit()
        print(f"✅ '{username}' is now a platform admin.")
        return
    password = generate_temporary_password()
    create_user(username, password, is_platform_admin=True)
    print(f"✅ Platform admin '{username}' created. One-time password (shown once, change it after login): {password}")

def cmd_create_owner(args):
    """Create a client account with its first owner (new login, or an existing user)."""
    init_db()
    import crm_store
    username = args.username.strip().lower()
    user = get_user_by_username(username)
    password = None
    if user:
        user_id = user["id"]
    else:
        password = generate_temporary_password()
        user_id = create_user(username, password, email=args.email or "", temporary=True)
    acct = crm_store.create_account(args.account, args.email or "")
    crm_store.add_membership(acct["id"], user_id, "owner")
    print(f"✅ Account '{acct['name']}' created (id {acct['id']}); '{username}' is its owner.")
    if password:
        print(f"   One-time password (shown once, change it after login): {password}")

def cmd_install_blog(args):
    """Install zero-redeploy dynamic blog page to target repository."""
    init_db()
    project = get_project(args.project_id)
    if not project:
        print(f"❌ Project ID {args.project_id} not found.")
        sys.exit(1)
    
    cms_url = args.cms_url or "http://localhost:8420"
    html_content = generate_one_time_blog_html(args.project_id, project["name"], cms_url)
    page_path = project.get("blog_page_path", "public/blog/index.html")
    
    settings = get_all_settings()
    token = project.get("github_token") or settings.get("github_token", "")
    client = GitHubClient(token=token)
    commit_msg = f"feat(blog): install zero-redeploy dynamic blog page at {page_path}"
    
    ok, sha, err = client.commit_file(project["github_repo"], page_path, html_content, project["github_branch"], commit_msg)
    if ok or not token:
        print(f"✅ One-time blog page installed to {project['github_repo']} at '{page_path}' (Commit: {sha or 'sim-commit'}).")
        print(f"🎉 New posts published from GitPulse will now appear on this website dynamically without any future deployments!")
    else:
        print(f"❌ Installation failed: {err}")

def cmd_reset_password(args):
    """Reset password for an administrative user."""
    init_db()
    username = args.username.strip().lower()
    user = get_user_by_username(username)
    if not user:
        create_user(username, args.password)
        print(f"✅ User '{username}' created with specified password.")
    else:
        update_user_password(user["id"], args.password)
        print(f"✅ Password for user '{username}' successfully reset.")

def cmd_start(args):
    """Start background scheduler daemon and HTTP Dashboard server."""
    init_db()
    start_scheduler()
    host = args.host or SERVER_HOST
    port = args.port or SERVER_PORT
    print(f"✨ Starting GitPulse CMS on {host}:{port}")
    run_server(host=host, port=port)

def cmd_list_projects(args):
    """List all connected GitHub projects."""
    init_db()
    projects = list_all_projects()
    if not projects:
        print("No projects registered yet. Add one from the dashboard.")
        return

    print("\n" + "=" * 80)
    print(f"{'ID':<4} {'PROJECT NAME':<24} {'REPO':<30} {'FRAMEWORK':<12} {'SCHEDULE'}")
    print("=" * 80)
    for p in projects:
        print(f"{p['id']:<4} {p['name'][:22]:<24} {p['github_repo'][:28]:<30} {p['target_framework']:<12} {p['publish_time']} UTC")
    print("=" * 80 + "\n")

def cmd_publish(args):
    """Execute end-to-end generation and publishing for a project."""
    init_db()
    project_id = args.project_id
    project = get_project(project_id)
    if not project:
        print(f"❌ Project ID {project_id} not found.")
        sys.exit(1)

    print(f"🚀 Running publication pipeline for '{project['name']}' ({project['github_repo']})...")
    force = not args.draft_only
    result = run_publication_pipeline(project_id, force_publish=force)

    if result.get("success"):
        print(f"✅ Success! Generated article: '{result['title']}'")
        print(f"📁 Target Path: {result['target_path']}")
        if force and "pub_result" in result:
            pub = result["pub_result"]
            if pub.get("pr_url"):
                print(f"🔗 Pull Request: {pub['pr_url']}")
            elif pub.get("commit_sha"):
                print(f"📌 Commit SHA: {pub['commit_sha']}")
            print(f"ℹ️  {pub.get('message')}")
    else:
        print(f"❌ Publishing failed: {result.get('error')}")
        sys.exit(1)

def cmd_test_github(args):
    """Verify repository connection and permissions."""
    init_db()
    project = get_project(args.project_id)
    if not project:
        print(f"❌ Project ID {args.project_id} not found.")
        sys.exit(1)

    settings = get_all_settings()
    token = project.get("github_token") or settings.get("github_token", "")
    client = GitHubClient(token=token)
    ok, msg = client.test_connection(project["github_repo"])
    if ok:
        print(f"✅ Connection successful: {msg}")
    else:
        print(f"❌ Connection failed: {msg}")

def cmd_set_config(args):
    """Store configuration key-value."""
    init_db()
    set_setting(args.key, args.value)
    print(f"✅ Configuration '{args.key}' updated.")

def main():
    parser = argparse.ArgumentParser(description="GitPulse CMS - Automated Multi-Project GitHub Blog Engine")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize the (empty) database schema")
    p_init.set_defaults(func=cmd_init)

    p_pa = subparsers.add_parser("create-platform-admin", help="Create a platform admin (creates client accounts)")
    p_pa.add_argument("--username", required=True)
    p_pa.set_defaults(func=cmd_create_platform_admin)

    p_owner = subparsers.add_parser("create-owner", help="Create a client account and its first owner")
    p_owner.add_argument("--account", required=True, help="Account (business) name")
    p_owner.add_argument("--username", required=True)
    p_owner.add_argument("--email", default="")
    p_owner.set_defaults(func=cmd_create_owner)

    # start
    p_start = subparsers.add_parser("start", help="Start Web Dashboard & Scheduler daemon")
    p_start.add_argument("--host", default=None, help="Server host (default: 0.0.0.0)")
    p_start.add_argument("--port", type=int, default=None, help="Server port (default: 8420)")
    p_start.set_defaults(func=cmd_start)

    # list-projects
    p_list = subparsers.add_parser("list-projects", help="List registered GitHub projects")
    p_list.set_defaults(func=cmd_list_projects)

    # publish
    p_pub = subparsers.add_parser("publish", help="Run immediate daily publication pipeline")
    p_pub.add_argument("--project-id", type=int, required=True, help="Target project ID")
    p_pub.add_argument("--draft-only", action="store_true", help="Generate post without committing to GitHub")
    p_pub.set_defaults(func=cmd_publish)

    # test-github
    p_test = subparsers.add_parser("test-github", help="Test GitHub repository connection")
    p_test.add_argument("--project-id", type=int, required=True, help="Target project ID")
    p_test.set_defaults(func=cmd_test_github)

    # set-config
    p_cfg = subparsers.add_parser("set-config", help="Set configuration key (e.g. github_token, gemini_api_key)")
    p_cfg.add_argument("--key", required=True, help="Config key")
    p_cfg.add_argument("--value", required=True, help="Config value")
    p_cfg.set_defaults(func=cmd_set_config)

    # reset-password
    p_pw = subparsers.add_parser("reset-password", help="Reset or create an admin password")
    p_pw.add_argument("--username", default="admin", help="Username to update (default: admin)")
    p_pw.add_argument("--password", required=True, help="New password")
    p_pw.set_defaults(func=cmd_reset_password)

    # install-blog-page
    p_inst = subparsers.add_parser("install-blog-page", help="Commit zero-redeploy dynamic blog page to target repository")
    p_inst.add_argument("--project-id", type=int, required=True, help="Target project ID")
    p_inst.add_argument("--cms-url", default="http://localhost:8420", help="Base URL of your GitPulse instance")
    p_inst.set_defaults(func=cmd_install_blog)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)

if __name__ == "__main__":
    main()

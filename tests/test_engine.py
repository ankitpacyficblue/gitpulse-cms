"""
GitPulse CMS - Comprehensive Unit & Integration Test Suite
Verifies database operations, topic ideation, AI generation,
formatters, GitHub client simulation, authentication,
malicious login restrictions (lockout), and protected REST API routing.
"""

import unittest
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import (
    init_db,
    seed_demo_data,
    list_projects,
    get_project,
    create_project,
    create_post,
    list_posts,
    get_recent_post_titles
)
from engine.formatters import slugify, calculate_reading_time, format_frontmatter, build_target_filepath
from engine.topic_planner import plan_daily_topic
from engine.ai_generator import AIGenerator
from engine.github_client import GitHubClient
from engine.pipeline import run_publication_pipeline
from engine.auth import (
    hash_password,
    verify_password,
    authenticate_user,
    create_session,
    validate_session,
    revoke_session,
    init_default_admin,
    check_login_lockout,
    create_user
)
from server.routes_api import handle_api_request

class TestGitPulseCMS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_demo_data()
        init_default_admin()

    def test_database_and_projects(self):
        projects = list_projects()
        self.assertGreaterEqual(len(projects), 3)
        p = projects[0]
        self.assertIn("github_repo", p)
        self.assertIn("target_framework", p)

    def test_formatters_slugify(self):
        self.assertEqual(slugify("Mastering Kubernetes in 2026!"), "mastering-kubernetes-in-2026")
        self.assertEqual(slugify("React 19 & Server Actions: Deep Dive"), "react-19-server-actions-deep-dive")

    def test_reading_time(self):
        sample_text = "word " * 440
        self.assertEqual(calculate_reading_time(sample_text), 2)

    def test_frontmatter_rendering(self):
        template = "---\ntitle: \"{title}\"\ndate: \"{date}\"\ntags: {tags_json}\n---"
        rendered = format_frontmatter(template, {
            "title": "My Post",
            "date": "2026-11-24",
            "tags": ["AI", "DevOps"]
        })
        self.assertIn('title: "My Post"', rendered)
        self.assertIn('tags: ["AI", "DevOps"]', rendered)

    def test_filepath_generation_per_framework(self):
        # Astro
        astro_proj = {"content_dir": "src/content/blog", "file_extension": ".md", "target_framework": "astro"}
        path_astro = build_target_filepath(astro_proj, "my-post", "2026-11-24")
        self.assertEqual(path_astro, "src/content/blog/my-post.md")

        # Jekyll requires date prefix
        jekyll_proj = {"content_dir": "_posts", "file_extension": ".md", "target_framework": "jekyll"}
        path_jekyll = build_target_filepath(jekyll_proj, "my-post", "2026-11-24")
        self.assertEqual(path_jekyll, "_posts/2026-11-24-my-post.md")

    def test_topic_planner(self):
        projects = list_projects()
        project = projects[0]
        plan = plan_daily_topic(project)
        self.assertIn("title", plan)
        self.assertIn("primary_keyword", plan)
        self.assertIn("archetype", plan)

    def test_ai_generator(self):
        generator = AIGenerator(provider="local")
        plan = {
            "title": "Mastering Zero-Trust Security",
            "primary_keyword": "Zero-Trust",
            "keywords": ["Security", "Kubernetes", "IAM"],
            "angle": "Architectural guide"
        }
        project = {"topic": "Cloud Security", "target_audience": "DevOps Engineers", "name": "Security Blog"}
        article = generator.generate_article(plan, project)

        self.assertIn("title", article)
        self.assertIn("content_markdown", article)
        self.assertIn("## Introduction", article["content_markdown"])
        self.assertIn("slug", article)
        self.assertGreaterEqual(len(article["tags"]), 1)

    def test_github_client_simulation(self):
        client = GitHubClient(token="mock")
        res = client.publish_post(
            repo="test-owner/test-repo",
            branch="main",
            target_path="content/posts/test.md",
            file_content="test content",
            post_title="Test Title",
            post_excerpt="Test Excerpt",
            post_tags=["test"],
            mode="pr"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["mode"], "pr")
        self.assertIn("github.com/test-owner/test-repo/pull/", res["pr_url"])

    def test_end_to_end_pipeline(self):
        projects = list_projects()
        project_id = projects[0]["id"]
        result = run_publication_pipeline(project_id, force_publish=True)

        self.assertTrue(result["success"])
        self.assertIn("post_id", result)
        self.assertIn("target_path", result)
        self.assertEqual(result["status"], "published")

        posts = list_posts(project_id=project_id)
        self.assertGreaterEqual(len(posts), 1)

    # --- Authentication & Malicious Login Restriction Tests ---

    def test_password_hashing_and_verification(self):
        salt, hash_val = hash_password("SuperSecret2026!")
        self.assertTrue(verify_password("SuperSecret2026!", salt, hash_val))
        self.assertFalse(verify_password("WrongPassword!", salt, hash_val))

    def test_brute_force_malicious_login_restriction(self):
        """Simulate malicious brute-force attack and verify lockout triggers."""
        test_ip = "192.168.1.99"
        test_user = "attacker_target"
        create_user(test_user, "RealPassword123!")

        # 1. First 4 failed attempts should fail normally
        for _ in range(4):
            ok, token, _, err = authenticate_user(test_user, "BadPass!", ip_address=test_ip)
            self.assertFalse(ok)
            self.assertEqual(err, "Invalid username or password.")

        # Not yet locked out after 4 attempts
        locked, _ = check_login_lockout(test_ip, test_user)
        self.assertFalse(locked)

        # 2. 5th failed attempt reaches the threshold
        ok, token, _, err = authenticate_user(test_user, "BadPass!", ip_address=test_ip)
        self.assertFalse(ok)

        # 3. 6th attempt MUST be blocked by brute-force lockout restriction
        ok, token, _, err = authenticate_user(test_user, "RealPassword123!", ip_address=test_ip)
        self.assertFalse(ok)
        self.assertIn("Account temporarily locked", err)

        # Verify lockout check directly
        is_locked, remaining_sec = check_login_lockout(test_ip, test_user)
        self.assertTrue(is_locked)
        self.assertGreater(remaining_sec, 0)

    def test_session_lifecycle_and_logout(self):
        """Test login, session token validation, and logout revocation."""
        ok, token, user_data, err = authenticate_user("admin", "GitPulse@Admin2026!", ip_address="127.0.0.1")
        self.assertTrue(ok)
        self.assertIsNotNone(token)
        self.assertEqual(user_data["username"], "admin")

        # Validate active session
        session_user = validate_session(token)
        self.assertIsNotNone(session_user)
        self.assertEqual(session_user["username"], "admin")

        # Revoke session (logout)
        revoke_session(token)

        # Session must now be invalid
        self.assertIsNone(validate_session(token))

    def test_api_auth_guard(self):
        """Protected API routes must reject unauthenticated requests with 401."""
        # Unauthenticated request to /api/projects
        code, data = handle_api_request("GET", "/api/projects", {}, None, current_user=None)
        self.assertEqual(code, 401)
        self.assertEqual(data.get("code"), "UNAUTHORIZED")

        # Authenticated request with user
        fake_user = {"id": 1, "username": "admin", "role": "admin"}
        code, data = handle_api_request("GET", "/api/projects", {}, None, current_user=fake_user)
        self.assertEqual(code, 200)
        self.assertIn("projects", data)

        # Public presets endpoint remains accessible
        code, data = handle_api_request("GET", "/api/presets", {}, None, current_user=None)
        self.assertEqual(code, 200)
        self.assertIn("nextjs", data)

if __name__ == "__main__":
    unittest.main()

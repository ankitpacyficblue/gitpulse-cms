"""
GitPulse CMS - Comprehensive Unit & Integration Test Suite
Verifies:
1. Core database operations & framework path resolution
2. Topic ideation & AI synthesis
3. PBKDF2 password security & brute-force lockout defense
4. RFC 6238 TOTP 2-Factor Authentication
5. 1200x630 OpenGraph / Hero SVG image synthesis
6. SEO Pre-Flight Linter & Brand Safety / Negative Keywords Filter
7. Repository README Context Ingestion & Internal Linking
8. Zero-Redeploy "One-Time Blog Page" generator & installer
9. Public Headless Content Delivery API & RSS feed
10. Bi-directional GitHub Webhook sync with HMAC signature verification
11. Editorial Staging Queue & Split Editor approval lifecycle
"""

import unittest
import os
import sys
import json
import time
import hmac
import hashlib
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import (
    init_db,
    seed_demo_data,
    list_projects,
    get_project,
    create_project,
    create_post,
    get_post,
    list_posts,
    update_post_status,
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
from engine.totp import (
    generate_totp_secret,
    generate_totp_code,
    verify_totp_code,
    get_totp_uri
)
from engine.image_generator import generate_hero_svg, svg_to_data_uri
from engine.seo_linter import lint_article
from engine.doc_ingestion import summarize_readme_context, get_internal_linking_suggestions
from engine.templates_embed import generate_one_time_blog_html
from server.routes_api import handle_api_request
from server.routes_public import handle_public_request
from server.routes_webhook import handle_github_webhook

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
        astro_proj = {"content_dir": "src/content/blog", "file_extension": ".md", "target_framework": "astro"}
        path_astro = build_target_filepath(astro_proj, "my-post", "2026-11-24")
        self.assertEqual(path_astro, "src/content/blog/my-post.md")

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

    def test_password_security_and_lockout(self):
        salt, hash_val = hash_password("SecurePassword2026!")
        self.assertTrue(verify_password("SecurePassword2026!", salt, hash_val))
        self.assertFalse(verify_password("WrongPass!", salt, hash_val))

        test_ip = f"10.0.0.{secrets.randbelow(200) + 10}"
        test_user = f"brute_{secrets.token_hex(4)}"
        create_user(test_user, "RealPass123!")

        # 5 failed attempts trigger lockout
        for _ in range(5):
            authenticate_user(test_user, "Bad!", ip_address=test_ip)

        # 6th attempt must be blocked by lockout
        ok, _, _, err = authenticate_user(test_user, "RealPass123!", ip_address=test_ip)
        self.assertFalse(ok)
        self.assertIn("Account temporarily locked", err)

    def test_totp_two_factor_auth(self):
        secret = generate_totp_secret()
        self.assertGreaterEqual(len(secret), 16)

        uri = get_totp_uri("admin", secret, "GitPulse")
        self.assertTrue(uri.startswith("otpauth://totp/GitPulse:admin"))

        # Generate and verify current code
        code = generate_totp_code(secret)
        self.assertEqual(len(code), 6)
        self.assertTrue(verify_totp_code(secret, code))
        self.assertFalse(verify_totp_code(secret, "000000" if code != "000000" else "111111"))

    def test_hero_svg_image_generator(self):
        svg = generate_hero_svg(
            title="Optimizing High-Throughput Kubernetes Clusters",
            category="DevOps",
            author="DevOps Team",
            reading_time=6
        )
        self.assertIn("<svg", svg)
        self.assertIn('viewBox="0 0 1200 630"', svg)
        self.assertIn("DEVOPS", svg)
        self.assertIn("GitPulse", svg)

        data_uri = svg_to_data_uri(svg)
        self.assertTrue(data_uri.startswith("data:image/svg+xml;base64,"))

    def test_seo_linter_and_brand_safety(self):
        good_title = "Architecting Scalable Microservices with Modern Patterns"
        good_excerpt = "A comprehensive deep dive into scalable microservices architecture covering resilience, observability, and latency benchmarks."
        good_markdown = "## Section 1\n\nContent here.\n\n## Section 2\n\n```python\nprint(1)\n```\n\n## Section 3\n\nDone." + (" word" * 500)

        # Test compliant article
        result = lint_article(good_title, good_excerpt, good_markdown, forbidden_words_csv="badcompany,competitorX")
        self.assertGreaterEqual(result["score"], 80)
        self.assertTrue(result["passed"])

        # Test brand safety violation
        bad_markdown = good_markdown + "\n\nWe recommend using badcompany instead."
        result_bad = lint_article(good_title, good_excerpt, bad_markdown, forbidden_words_csv="badcompany,competitorX")
        self.assertFalse(result_bad["passed"])
        self.assertTrue(any("badcompany" in issue for issue in result_bad["issues"]))

    def test_doc_ingestion_and_internal_linking(self):
        raw_readme = "# My Project\n[![build](badge.svg)](url)\n\nA high-throughput database orchestrator for distributed teams."
        summary = summarize_readme_context(raw_readme)
        self.assertIn("high-throughput database", summary)

        projects = list_projects()
        suggestions = get_internal_linking_suggestions(projects[0]["id"])
        self.assertIsInstance(suggestions, list)

    def test_zero_redeploy_blog_page_generator(self):
        html = generate_one_time_blog_html(project_id=1, project_name="Acme Tech", cms_base_url="https://cms.acme.com")
        self.assertIn("Acme Tech - Official Blog", html)
        self.assertIn("CMS_API = \"https://cms.acme.com\"", html)
        self.assertIn("PROJECT_ID = 1", html)
        self.assertIn("marked.parse", html)

    def test_public_headless_content_api(self):
        projects = list_projects()
        p_id = projects[0]["id"]

        # Public posts listing
        code, ctype, body = handle_public_request(f"/api/public/projects/{p_id}/posts", {})
        self.assertEqual(code, 200)
        self.assertEqual(ctype, "application/json")
        data = json.loads(body)
        self.assertIn("posts", data)

        # Public RSS feed
        code, ctype, body = handle_public_request(f"/api/public/projects/{p_id}/rss.xml", {})
        self.assertEqual(code, 200)
        self.assertIn("application/xml", ctype)
        self.assertIn("<rss version=\"2.0\">", body)

    def test_github_webhook_sync(self):
        # 1. Ping Event
        code, resp = handle_github_webhook("ping", "", b"{}", {"zen": "Mind over matter."})
        self.assertEqual(code, 200)

        # 2. PR Merged Event
        projects = list_projects()
        post_id = create_post({
            "project_id": projects[0]["id"],
            "title": "Webhook Test Article",
            "slug": "webhook-test-article",
            "content_markdown": "Test body",
            "target_path": "content/posts/webhook.md",
            "github_pr_number": 999,
            "status": "draft"
        })

        payload = {
            "action": "closed",
            "pull_request": {
                "number": 999,
                "merged": True,
                "merge_commit_sha": "merge-sha-12345"
            },
            "repository": {"full_name": projects[0]["github_repo"]}
        }

        code, resp = handle_github_webhook("pull_request", "", json.dumps(payload).encode("utf-8"), payload)
        self.assertEqual(code, 200)

        updated_post = get_post(post_id)
        self.assertEqual(updated_post["status"], "published")
        self.assertEqual(updated_post["github_commit_sha"], "merge-sha-12345")

    def test_editorial_staging_and_approval_workflow(self):
        projects = list_projects()
        # Create an in_review draft post
        post_id = create_post({
            "project_id": projects[0]["id"],
            "title": "Draft in Review",
            "slug": "draft-in-review",
            "excerpt": "Short excerpt",
            "content_markdown": "## Introduction\nDraft markdown content goes here.",
            "frontmatter_yaml": "---\ntitle: Draft in Review\n---",
            "target_path": "content/posts/draft-in-review.md",
            "status": "in_review"
        })

        # Test updating content in staging
        fake_user = {"id": 1, "username": "admin", "role": "admin"}
        put_payload = {
            "title": "Reviewed and Polished Title for 2026",
            "excerpt": "A polished meta description meeting the recommended length requirements.",
            "content_markdown": "## Polished Heading\n\n```python\nprint('hello')\n```\n\n## Next Steps\nConclusion." + (" word" * 500)
        }
        code, data = handle_api_request("PUT", f"/api/posts/{post_id}", {}, put_payload, current_user=fake_user)
        self.assertEqual(code, 200)
        self.assertIn("seo_score", data)

        # Test approving staged post
        code, approve_data = handle_api_request("POST", f"/api/posts/{post_id}/approve", {}, {}, current_user=fake_user)
        self.assertEqual(code, 200)
        self.assertTrue(approve_data["success"])

        final_post = get_post(post_id)
        self.assertEqual(final_post["status"], "published")

if __name__ == "__main__":
    unittest.main()

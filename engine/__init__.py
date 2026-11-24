"""
GitPulse CMS Engine
"""

from engine.pipeline import run_publication_pipeline
from engine.topic_planner import plan_daily_topic
from engine.ai_generator import AIGenerator
from engine.github_client import GitHubClient
from engine.formatters import slugify, calculate_reading_time, build_target_filepath
from engine.auth import (
    authenticate_user,
    validate_session,
    revoke_session,
    init_default_admin,
    create_user,
    update_user_password,
    check_login_lockout
)
from engine.totp import (
    generate_totp_secret,
    verify_totp_code,
    get_totp_uri
)
from engine.image_generator import (
    generate_hero_svg,
    svg_to_data_uri
)
from engine.seo_linter import lint_article
from engine.templates_embed import generate_one_time_blog_html
from engine.doc_ingestion import fetch_repo_readme, get_internal_linking_suggestions

__all__ = [
    "run_publication_pipeline",
    "plan_daily_topic",
    "AIGenerator",
    "GitHubClient",
    "slugify",
    "calculate_reading_time",
    "build_target_filepath",
    "authenticate_user",
    "validate_session",
    "revoke_session",
    "init_default_admin",
    "create_user",
    "update_user_password",
    "check_login_lockout",
    "generate_totp_secret",
    "verify_totp_code",
    "get_totp_uri",
    "generate_hero_svg",
    "svg_to_data_uri",
    "lint_article",
    "generate_one_time_blog_html",
    "fetch_repo_readme",
    "get_internal_linking_suggestions"
]

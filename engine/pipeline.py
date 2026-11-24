"""
GitPulse CMS - End-to-End Content Pipeline
Orchestrates topic ideation, AI generation, frontmatter formatting,
and automated GitHub commit / PR publication for any connected repository.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import json

from database import (
    get_project,
    create_post,
    update_post_status,
    update_project_last_run,
    log_event,
    get_setting
)
from config import (
    DEFAULT_GITHUB_TOKEN,
    DEFAULT_AI_PROVIDER,
    DEFAULT_GEMINI_API_KEY,
    DEFAULT_OPENAI_API_KEY
)
from engine.topic_planner import plan_daily_topic
from engine.ai_generator import AIGenerator
from engine.formatters import (
    format_frontmatter,
    build_target_filepath,
    assemble_post_document
)
from engine.github_client import GitHubClient

def run_publication_pipeline(project_id: int, force_publish: bool = True) -> Dict[str, Any]:
    """
    Executes complete end-to-end publishing workflow for a target project.
    """
    project = get_project(project_id)
    if not project:
        raise ValueError(f"Project #{project_id} not found.")

    log_event(f"Starting publication cycle for '{project['name']}' ({project['github_repo']}).", "INFO", project_id=project_id)

    # 1. Topic Planning
    topic_plan = plan_daily_topic(project)
    log_event(f"Planned topic: '{topic_plan['title']}' [Archetype: {topic_plan['archetype']}]", "INFO", project_id=project_id)

    # 2. AI Content Generation
    ai_provider = get_setting("ai_provider", DEFAULT_AI_PROVIDER)
    ai_key = get_setting(f"{ai_provider}_api_key", "")
    if not ai_key:
        if ai_provider == "gemini":
            ai_key = DEFAULT_GEMINI_API_KEY
        elif ai_provider == "openai":
            ai_key = DEFAULT_OPENAI_API_KEY

    generator = AIGenerator(provider=ai_provider, api_key=ai_key)
    article = generator.generate_article(topic_plan, project)

    # 3. Target Filepath & Frontmatter Formatting
    post_date = datetime.utcnow().strftime("%Y-%m-%d")
    target_path = build_target_filepath(project, article["slug"], post_date)

    frontmatter_vars = {
        "title": article["title"],
        "excerpt": article["excerpt"],
        "date": post_date,
        "date_iso": datetime.utcnow().isoformat(),
        "author": project.get("author_name", "Editorial Team"),
        "slug": article["slug"],
        "tags": article["tags"],
        "reading_time": article.get("meta_seo", {}).get("reading_time", 5)
    }

    frontmatter_yaml = format_frontmatter(project["frontmatter_template"], frontmatter_vars)
    full_document = assemble_post_document(frontmatter_yaml, article["content_markdown"])

    # 4. Save Post Record in DB
    post_id = create_post({
        "project_id": project_id,
        "title": article["title"],
        "slug": article["slug"],
        "excerpt": article["excerpt"],
        "content_markdown": article["content_markdown"],
        "frontmatter_yaml": frontmatter_yaml,
        "target_path": target_path,
        "tags": article["tags"],
        "meta_seo": article["meta_seo"],
        "image_prompt": article["image_prompt"],
        "status": "scheduled" if not force_publish else "publishing"
    })

    if not force_publish:
        log_event(f"Post #{post_id} saved as draft / scheduled.", "INFO", project_id=project_id, post_id=post_id)
        update_project_last_run(project_id)
        return {
            "success": True,
            "post_id": post_id,
            "title": article["title"],
            "target_path": target_path,
            "status": "scheduled"
        }

    # 5. Publish to GitHub
    github_token = project.get("github_token") or get_setting("github_token", DEFAULT_GITHUB_TOKEN)
    client = GitHubClient(token=github_token)

    pub_result = client.publish_post(
        repo=project["github_repo"],
        branch=project["github_branch"],
        target_path=target_path,
        file_content=full_document,
        post_title=article["title"],
        post_excerpt=article["excerpt"],
        post_tags=article["tags"],
        mode=project.get("publishing_mode", "pr")
    )

    if pub_result.get("success"):
        update_post_status(
            post_id=post_id,
            status="published",
            commit_sha=pub_result.get("commit_sha"),
            pr_url=pub_result.get("pr_url"),
            pr_number=pub_result.get("pr_number")
        )
        update_project_last_run(project_id)
        log_msg = f"Published post #{post_id} to {project['github_repo']}. {pub_result.get('message')}"
        log_event(log_msg, "INFO", project_id=project_id, post_id=post_id, metadata=pub_result)
        return {
            "success": True,
            "post_id": post_id,
            "title": article["title"],
            "target_path": target_path,
            "status": "published",
            "pub_result": pub_result
        }
    else:
        err_msg = pub_result.get("error", "Unknown GitHub publishing error")
        update_post_status(post_id=post_id, status="failed", error=err_msg)
        log_event(f"Failed to publish post #{post_id}: {err_msg}", "ERROR", project_id=project_id, post_id=post_id)
        return {
            "success": False,
            "post_id": post_id,
            "title": article["title"],
            "error": err_msg
        }

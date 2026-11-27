"""
GitPulse CMS - End-to-End Content Pipeline
Orchestrates topic ideation, README context ingestion, AI generation,
SEO & brand safety linting, OpenGraph banner synthesis, and GitHub delivery.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import json
import os

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
from engine import site_publish
from engine.doc_ingestion import fetch_repo_readme, summarize_readme_context, get_internal_linking_suggestions
from engine.seo_linter import lint_article
from engine.image_generator import generate_hero_svg

def run_publication_pipeline(project_id: int, force_publish: bool = False) -> Dict[str, Any]:
    """
    Executes complete publication cycle with context ingestion, SEO linting,
    hero image synthesis, and publication or editorial staging.
    """
    project = get_project(project_id)
    if not project:
        raise ValueError(f"Project #{project_id} not found.")
    if not project.get("topic"):      # a website connected by name and address only
        project = dict(project, topic=project["name"], keywords=project.get("keywords") or project["name"])

    log_event(f"Starting publication cycle for '{project['name']}'.", "INFO", project_id=project_id)

    # 1. Target Repo Context Ingestion (RAG)
    # Each project publishes with its own token; the platform-wide token is deliberately not used,
    # so one account cannot publish to a repo through another tenant's or the operator's credentials.
    import crm_store
    account_id = project.get("account_id") or ""
    github_token = project.get("github_token") or crm_store.get_account_github_token(account_id)
    readme_raw = fetch_repo_readme(project["github_repo"], github_token)
    repo_summary = summarize_readme_context(readme_raw)
    internal_links = get_internal_linking_suggestions(project_id)

    # 2. Topic Planning
    topic_plan = plan_daily_topic(project)
    log_event(f"Planned topic: '{topic_plan['title']}' [Archetype: {topic_plan['archetype']}]", "INFO", project_id=project_id)

    # Enrich topic plan with repository context and internal link suggestions
    enriched_project = dict(project)
    if repo_summary:
        enriched_project["topic"] = f"{project['topic']}\n\nTarget Repo Codebase Context:\n{repo_summary}"

    # 3. AI Content Generation
    # The account's own provider/key wins; otherwise the platform setting is the fallback.
    acct_provider, acct_key = crm_store.get_account_ai(account_id)
    ai_provider = acct_provider or get_setting("ai_provider", DEFAULT_AI_PROVIDER)
    ai_key = acct_key if (acct_key and acct_provider == ai_provider) else get_setting(f"{ai_provider}_api_key", "")
    if not ai_key:
        if ai_provider == "gemini":
            ai_key = DEFAULT_GEMINI_API_KEY
        elif ai_provider == "openai":
            ai_key = DEFAULT_OPENAI_API_KEY

    from engine import assistant
    knowledge = assistant.get_knowledge(account_id) if account_id else None
    business = assistant.knowledge_text(knowledge) if knowledge else ""
    if business:
        enriched_project["business_knowledge"] = business
        enriched_project["banned_claims"] = knowledge["banned_claims"]
        enriched_project["topic"] = project["topic"]

    generator = AIGenerator(provider=ai_provider, api_key=ai_key)
    article = generator.generate_article(topic_plan, enriched_project)

    # 4. SEO Pre-Flight Linting & Brand Safety Filter
    lint_results = lint_article(
        title=article["title"],
        excerpt=article["excerpt"],
        content_markdown=article["content_markdown"],
        forbidden_words_csv=project.get("forbidden_words", "")
    )
    log_event(f"SEO Pre-flight score for '{article['title']}': {lint_results['score']}/100.", "INFO", project_id=project_id)

    # 5. Hero & OpenGraph Banner Synthesis (1200x630 SVG)
    hero_svg = generate_hero_svg(
        title=article["title"],
        category=project.get("name", "Engineering"),
        author=project.get("author_name", "Editorial Team"),
        reading_time=article.get("meta_seo", {}).get("reading_time", 5)
    )

    # 6. Target Filepath & Frontmatter Formatting
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

    # Determine initial status:
    # If project requires manual review (auto_publish=0) and not forced, stage for human approval
    auto_publish_enabled = bool(project.get("auto_publish", 1))
    blocked = None
    if knowledge and (business or knowledge["banned_claims"]):
        blocked = assistant.guard(knowledge, "\n".join((article["title"], article["excerpt"], article["content_markdown"])))
    should_publish_now = (force_publish or auto_publish_enabled) and not blocked
    initial_status = "publishing" if should_publish_now else "in_review"

    # 7. Save Post Record in DB
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
        "og_image_svg": hero_svg,
        "seo_score": lint_results["score"],
        "seo_issues": lint_results["issues"],
        "status": initial_status
    })

    from engine import blog_plan
    if not should_publish_now:
        blog_plan.mirror(post_id)
        log_event(f"Post #{post_id} entered Editorial Staging queue ('in_review'). Awaiting human approval.", "INFO", project_id=project_id, post_id=post_id)
        update_project_last_run(project_id)
        return {
            "success": True,
            "post_id": post_id,
            "title": article["title"],
            "target_path": target_path,
            "status": "in_review",
            "blocked": blocked,
            "seo_score": lint_results["score"],
            "message": "Article generated and held in Editorial Staging for review."
        }

    # 8. Make it live: the website reads published posts from GitPulse
    update_post_status(post_id=post_id, status="published")
    blog_plan.mirror(post_id)
    update_project_last_run(project_id)
    log_event(f"Published post #{post_id}.", "INFO", project_id=project_id, post_id=post_id)

    # Cross-Engine WhatsApp Automation: Notify subscribers & VIPs
    try:
        from engine.whatsapp_client import WhatsAppClient
        url = site_publish.post_url(project["account_id"], article["slug"])
        if url:
            WhatsAppClient(project["account_id"]).trigger_blog_publish_alert(article["title"], url)
    except Exception:
        pass
    return {
        "success": True,
        "post_id": post_id,
        "title": article["title"],
        "target_path": target_path,
        "status": "published",
        "seo_score": lint_results["score"],
        "pub_result": {"success": True, "mode": "live"}
    }

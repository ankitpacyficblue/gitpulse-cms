"""
GitPulse CMS - Intelligent Topic Planner
Orchestrates daily topic ideation, avoids duplicate coverage,
rotates editorial angles, and generates structured post outlines.
"""

import random
from typing import Dict, Any, List, Tuple
from database import get_recent_post_titles

EDITORIAL_ARCHETYPES = [
    {
        "type": "deep_dive",
        "angle": "Comprehensive technical guide and architectural breakdown",
        "title_templates": [
            "Architecting Resilient {topic_keyword} in Production",
            "Deep Dive: Mastering {topic_keyword} with Modern Patterns",
            "The Complete Engineering Guide to {topic_keyword}",
            "Under the Hood: How {topic_keyword} Really Works"
        ]
    },
    {
        "type": "optimization",
        "angle": "Benchmarking, performance tuning, and efficiency optimizations",
        "title_templates": [
            "Optimizing {topic_keyword} for Peak Latency and Scale",
            "5 Practical Bottlenecks in {topic_keyword} and How to Fix Them",
            "How We Cut Latency by 40% Using {topic_keyword}",
            "Tuning {topic_keyword}: Production Benchmarks and Lessons Learned"
        ]
    },
    {
        "type": "comparison",
        "angle": "In-depth trade-off analysis and strategic technology evaluation",
        "title_templates": [
            "{topic_keyword}: Evaluating the Trade-offs for Modern Teams",
            "Why We Shifted our Approach to {topic_keyword}",
            "Comparing Approaches to {topic_keyword}: A Pragmatic Guide",
            "The True Cost of Misconfiguring {topic_keyword}"
        ]
    },
    {
        "type": "best_practices",
        "angle": "Checklist, security hardening, and operational resilience",
        "title_templates": [
            "The Production Checklist for {topic_keyword} in 2026",
            "Hardening {topic_keyword}: Zero-Trust Patterns and Guardrails",
            "Top 7 Anti-Patterns in {topic_keyword} and Modern Fixes",
            "Building Fail-Safe Systems with {topic_keyword}"
        ]
    },
    {
        "type": "troubleshooting",
        "angle": "Real-world debugging, incident review, and failure recovery",
        "title_templates": [
            "Debugging {topic_keyword}: What to Do When Systems Misbehave",
            "Postmortem Lessons: Handling Unexpected {topic_keyword} Failures",
            "Diagnostic Playbook for High-Throughput {topic_keyword}",
            "Resilience Engineering: Surviving Outages in {topic_keyword}"
        ]
    }
]

def extract_keywords(keywords_str: str, topic_str: str) -> List[str]:
    """Parse comma/space separated keywords or derive from topic."""
    items = [k.strip() for k in keywords_str.split(",") if k.strip()]
    if not items:
        items = [w.strip() for w in topic_str.split() if len(w) > 4][:5]
    return items or ["Architecture", "Performance", "Security", "Reliability"]

def plan_daily_topic(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formulate a novel daily blog topic tailored to the project.
    Consults recent titles to ensure topical freshness and variety.
    """
    recent_titles = get_recent_post_titles(project["id"], limit=30)
    keywords = extract_keywords(project.get("keywords", ""), project.get("topic", ""))
    
    # Pick a keyword that hasn't dominated recent titles
    least_used_keyword = keywords[0]
    for kw in keywords:
        match_count = sum(1 for title in recent_titles if kw.lower() in title.lower())
        if match_count == 0:
            least_used_keyword = kw
            break

    # Pick an archetype
    archetype = random.choice(EDITORIAL_ARCHETYPES)
    title_template = random.choice(archetype["title_templates"])
    
    title = title_template.format(topic_keyword=least_used_keyword.capitalize())

    # Ensure uniqueness
    counter = 1
    original_title = title
    while title in recent_titles:
        title = f"{original_title} (Part {counter})"
        counter += 1

    return {
        "title": title,
        "archetype": archetype["type"],
        "angle": archetype["angle"],
        "primary_keyword": least_used_keyword,
        "keywords": keywords[:5],
        "target_audience": project.get("target_audience", "Engineering Teams"),
        "tone": project.get("tone", "Practical and Authoritative"),
        "project_topic": project.get("topic", "")
    }

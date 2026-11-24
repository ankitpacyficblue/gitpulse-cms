"""
GitPulse CMS - SEO Pre-Flight Linter & Brand Safety Engine
Evaluates search engine optimization compliance, heading hierarchy,
code syntax fences, and enforces forbidden word/brand safety rules.
"""

import re
from typing import Dict, Any, List

def lint_article(
    title: str,
    excerpt: str,
    content_markdown: str,
    forbidden_words_csv: str = "",
    target_keywords: List[str] = None
) -> Dict[str, Any]:
    """
    Perform rigorous SEO & Brand Safety linting.
    Returns: {"score": int (0-100), "passed": bool, "issues": List[str], "stats": Dict}
    """
    score = 100
    issues = []
    
    # 1. Title Length Audit (Recommended 40 - 65 chars for Google SERP)
    title_len = len(title.strip())
    if title_len < 30:
        score -= 15
        issues.append(f"Title is too short ({title_len} chars). Aim for 40-65 chars for optimal SERP visibility.")
    elif title_len > 70:
        score -= 10
        issues.append(f"Title may truncate in Google search results ({title_len} chars). Recommended under 65 chars.")

    # 2. Excerpt / Meta Description Audit (Recommended 130 - 165 chars)
    excerpt_len = len(excerpt.strip())
    if excerpt_len < 100:
        score -= 15
        issues.append(f"Meta description is too brief ({excerpt_len} chars). Aim for 130-165 chars.")
    elif excerpt_len > 175:
        score -= 10
        issues.append(f"Meta description exceeds optimal length ({excerpt_len} chars). Keep under 165 chars to avoid ellipsis.")

    # 3. Headings Structure (At least 3 H2 tags, proper formatting)
    h2_tags = re.findall(r'^##\s+(.+)$', content_markdown, re.MULTILINE)
    if len(h2_tags) < 3:
        score -= 15
        issues.append(f"Article only contains {len(h2_tags)} H2 sections. High-ranking technical articles should have at least 3-5 structured sections.")

    # 4. Code Blocks Syntax Highlight Identifier
    unlabeled_code_blocks = len(re.findall(r'^```\s*$', content_markdown, re.MULTILINE))
    if unlabeled_code_blocks > 0:
        score -= (unlabeled_code_blocks * 5)
        issues.append(f"Found {unlabeled_code_blocks} code block(s) without language identifiers (e.g. ```python or ```typescript).")

    # 5. Content Length & In-Depth Density
    words = len(re.findall(r'\b\w+\b', content_markdown))
    if words < 400:
        score -= 20
        issues.append(f"Article is too short ({words} words). Minimum recommended depth is 600+ words.")

    # 6. Brand Safety & Forbidden Words Filter (Critical)
    forbidden_violations = []
    if forbidden_words_csv:
        forbidden_list = [w.strip().lower() for w in forbidden_words_csv.split(",") if w.strip()]
        full_text = f"{title}\n{excerpt}\n{content_markdown}".lower()
        for bad_word in forbidden_list:
            if re.search(r'\b' + re.escape(bad_word) + r'\b', full_text):
                forbidden_violations.append(bad_word)

    if forbidden_violations:
        score -= (len(forbidden_violations) * 25)
        for fv in forbidden_violations:
            issues.append(f"🚨 Brand Safety Violation: Found forbidden word '{fv}'.")

    final_score = max(0, min(100, score))
    passed = (final_score >= 75) and (len(forbidden_violations) == 0)

    return {
        "score": final_score,
        "passed": passed,
        "issues": issues,
        "stats": {
            "title_length": title_len,
            "excerpt_length": excerpt_len,
            "word_count": words,
            "h2_sections_count": len(h2_tags),
            "brand_safety_violations": len(forbidden_violations)
        }
    }

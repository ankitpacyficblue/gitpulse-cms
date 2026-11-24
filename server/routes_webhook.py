"""
GitPulse CMS - GitHub Bi-Directional Webhook Receiver
Validates cryptographic HMAC-SHA256 payload signatures and synchronizes
Pull Request lifecycle events (opened, merged, closed) back to the CMS database.
"""

import hmac
import hashlib
import json
from typing import Dict, Any, Tuple
from database import list_posts, update_post_status, log_event, get_setting

def verify_github_signature(payload_bytes: bytes, signature_header: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from GitHub."""
    if not secret:
        # If no secret configured, accept in development mode
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature_header)

def handle_github_webhook(
    event_type: str,
    signature: str,
    raw_body: bytes,
    payload: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    """
    Process incoming GitHub Webhook event.
    """
    webhook_secret = get_setting("github_webhook_secret", "")
    if not verify_github_signature(raw_body, signature, webhook_secret):
        return 403, {"error": "Invalid HMAC signature."}

    if event_type == "ping":
        return 200, {"message": "Webhook ping verified successfully.", "zen": payload.get("zen")}

    if event_type == "pull_request":
        action = payload.get("action")
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number")
        is_merged = pr.get("merged", False)
        repo_name = payload.get("repository", {}).get("full_name")

        # Find matching post in database
        all_posts = list_posts(limit=100)
        matched_post = None
        for p in all_posts:
            if p.get("github_pr_number") == pr_number and (not repo_name or repo_name.lower() in (p.get("github_repo") or "").lower()):
                matched_post = p
                break

        if not matched_post:
            return 200, {"message": f"PR #{pr_number} received, no corresponding GitPulse post record found."}

        post_id = matched_post["id"]
        if action == "closed" and is_merged:
            merge_commit = pr.get("merge_commit_sha")
            update_post_status(post_id, status="published", commit_sha=merge_commit)
            log_event(f"GitHub Webhook: PR #{pr_number} for '{matched_post['title']}' was MERGED on {repo_name}.", "INFO", post_id=post_id)
            return 200, {"message": f"Post #{post_id} updated to 'published' via merge webhook."}

        elif action == "closed" and not is_merged:
            update_post_status(post_id, status="draft", error="PR closed without merging on GitHub.")
            log_event(f"GitHub Webhook: PR #{pr_number} for '{matched_post['title']}' was CLOSED without merge.", "WARN", post_id=post_id)
            return 200, {"message": f"Post #{post_id} marked as closed."}

        return 200, {"message": f"PR action '{action}' received and recorded."}

    return 200, {"message": f"Ignored event type '{event_type}'."}

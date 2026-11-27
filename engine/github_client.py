"""
GitPulse CMS - GitHub REST API Client
Handles repository access validation, direct commit pushes,
branch orchestration, and automated Pull Request creation.
"""

from database import normalize_repo
import base64
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple

NOT_FOUND = "GitHub: repo not found or token has no access."


class GitHubClient:
    def __init__(self, token: str):
        self.token = token.strip()
        self.base_url = "https://api.github.com"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitPulse-CMS-Publisher/1.0"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def test_connection(self, repo: str) -> Tuple[bool, str]:
        """Verify repository accessibility and permissions."""
        if not self.token:
            return False, "GitHub Personal Access Token is not configured."

        repo_clean = normalize_repo(repo)
        if "/" not in repo_clean:
            return False, f"Invalid repository format '{repo}'. Expected 'owner/repo'."

        if self.token == "mock":
            return True, f"Connected to {repo_clean} (Mock Simulation Mode: Push access enabled)."

        url = f"{self.base_url}/repos/{repo_clean}"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                permissions = data.get("permissions", {})
                can_push = permissions.get("push", False)
                return True, f"Connected to {data['full_name']} (Push access: {'Yes' if can_push else 'Read-only'})."
        except urllib.error.HTTPError as e:
            return False, NOT_FOUND if e.code == 404 else f"GitHub HTTP error {e.code}: {e.reason}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def commit_file(
        self,
        repo: str,
        path: str,
        content: str,
        branch: str,
        commit_message: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Commit a single file to a specific branch via GitHub Contents API.
        Returns (success, commit_sha, error_message).
        """
        url = f"{self.base_url}/repos/{repo}/contents/{path}"
        content_bytes = content.encode("utf-8")
        b64_content = base64.b64encode(content_bytes).decode("utf-8")

        # Check if file exists to provide sha for update
        existing_sha = None
        check_url = f"{url}?ref={branch}"
        check_req = urllib.request.Request(check_url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(check_req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                existing_sha = data.get("sha")
        except Exception:
            pass

        payload = {
            "message": commit_message,
            "content": b64_content,
            # No committer/author: GitHub then uses the token owner. Vercel blocks deploys
            # for a commit email it cannot match to a GitHub account.
            "branch": branch
        }
        if existing_sha:
            payload["sha"] = existing_sha

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._get_headers(),
            method="PUT"
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                commit_sha = data.get("commit", {}).get("sha")
                return True, commit_sha, None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            return False, None, NOT_FOUND if e.code == 404 else f"GitHub HTTP {e.code}: {body}"
        except Exception as e:
            return False, None, str(e)

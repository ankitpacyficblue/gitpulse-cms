"""
GitPulse CMS - GitHub REST API Client
Checks that a repository can be reached. GitPulse never writes to a repository.
"""

from database import normalize_repo
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
            "User-Agent": "GitPulse-CMS/1.0"
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

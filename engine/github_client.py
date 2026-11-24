"""
GitPulse CMS - GitHub REST API Client
Handles repository access validation, direct commit pushes,
branch orchestration, and automated Pull Request creation.
"""

import base64
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

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

        repo_clean = repo.strip().strip("/")
        if "/" not in repo_clean:
            return False, f"Invalid repository format '{repo}'. Expected 'owner/repo'."

        url = f"{self.base_url}/repos/{repo_clean}"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                permissions = data.get("permissions", {})
                can_push = permissions.get("push", False)
                return True, f"Connected to {data['full_name']} (Push access: {'Yes' if can_push else 'Read-only'})."
        except urllib.error.HTTPError as e:
            return False, f"GitHub HTTP error {e.code}: {e.reason}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def get_branch_sha(self, repo: str, branch: str = "main") -> Optional[str]:
        """Get the latest commit SHA for a branch."""
        url = f"{self.base_url}/repos/{repo}/git/ref/heads/{branch}"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["object"]["sha"]
        except Exception:
            return None

    def create_branch(self, repo: str, new_branch: str, source_sha: str) -> bool:
        """Create a new ref/branch in the repository."""
        url = f"{self.base_url}/repos/{repo}/git/refs"
        payload = {
            "ref": f"refs/heads/{new_branch}",
            "sha": source_sha
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._get_headers(),
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status in (200, 201)
        except Exception:
            return False

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
            "branch": branch,
            "committer": {
                "name": "GitPulse CMS",
                "email": "bot@gitpulse.cms"
            }
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
            return False, None, f"GitHub HTTP {e.code}: {body}"
        except Exception as e:
            return False, None, str(e)

    def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main"
    ) -> Tuple[bool, Optional[str], Optional[int], Optional[str]]:
        """
        Open a Pull Request on GitHub.
        Returns (success, pr_url, pr_number, error_message).
        """
        url = f"{self.base_url}/repos/{repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._get_headers(),
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return True, data.get("html_url"), data.get("number"), None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            return False, None, None, f"GitHub HTTP {e.code}: {body}"
        except Exception as e:
            return False, None, None, str(e)

    def publish_post(
        self,
        repo: str,
        branch: str,
        target_path: str,
        file_content: str,
        post_title: str,
        post_excerpt: str,
        post_tags: list,
        mode: str = "pr"
    ) -> Dict[str, Any]:
        """
        High-level publication dispatcher:
        Executes either Direct Commit or automated Pull Request workflow.
        Falls back to Mock Simulation when token is absent for safe testing.
        """
        # If no token is provided, simulate publication safely
        if not self.token or self.token == "mock":
            simulated_sha = f"sim-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-a1b2c3d4"
            if mode == "pr":
                simulated_pr_num = 142
                simulated_pr_url = f"https://github.com/{repo}/pull/{simulated_pr_num}"
                return {
                    "success": True,
                    "mode": "pr",
                    "commit_sha": simulated_sha,
                    "pr_url": simulated_pr_url,
                    "pr_number": simulated_pr_num,
                    "simulated": True,
                    "message": f"Simulated PR #{simulated_pr_num} created on {repo} (No live GitHub token provided)."
                }
            else:
                return {
                    "success": True,
                    "mode": "direct",
                    "commit_sha": simulated_sha,
                    "pr_url": None,
                    "pr_number": None,
                    "simulated": True,
                    "message": f"Simulated direct commit {simulated_sha[:8]} on {repo}:{branch}."
                }

        commit_message = f"docs(blog): publish '{post_title}' via GitPulse CMS"

        # Direct commit mode
        if mode == "direct":
            ok, sha, err = self.commit_file(repo, target_path, file_content, branch, commit_message)
            return {
                "success": ok,
                "mode": "direct",
                "commit_sha": sha,
                "pr_url": None,
                "pr_number": None,
                "simulated": False,
                "error": err,
                "message": f"Directly committed to {repo}@{branch}." if ok else f"Failed commit: {err}"
            }

        # Pull Request mode
        base_sha = self.get_branch_sha(repo, branch)
        if not base_sha:
            return {
                "success": False,
                "error": f"Could not retrieve base branch '{branch}' for {repo}."
            }

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        slug_short = target_path.split("/")[-1].replace(".mdx", "").replace(".md", "")[:30]
        feature_branch = f"gitpulse/blog-{slug_short}-{timestamp}"

        # 1. Create feature branch
        if not self.create_branch(repo, feature_branch, base_sha):
            return {
                "success": False,
                "error": f"Failed to create branch '{feature_branch}' on {repo}."
            }

        # 2. Commit file to feature branch
        ok, sha, err = self.commit_file(repo, target_path, file_content, feature_branch, commit_message)
        if not ok:
            return {"success": False, "error": f"Failed to commit post: {err}"}

        # 3. Open Pull Request
        pr_title = f"📝 Blog: {post_title}"
        pr_body = f"""### 🚀 New Daily Blog Post

**Title:** {post_title}
**Target Path:** `{target_path}`
**Tags:** {', '.join(post_tags)}

#### 📌 Overview
{post_excerpt}

---

*Generated & published automatically by **GitPulse CMS**.*
*Review the markdown content above and merge when ready!*
"""
        ok_pr, pr_url, pr_num, pr_err = self.create_pull_request(repo, pr_title, pr_body, feature_branch, branch)
        if not ok_pr:
            return {"success": False, "error": f"Branch created but failed to open PR: {pr_err}"}

        return {
            "success": True,
            "mode": "pr",
            "commit_sha": sha,
            "pr_url": pr_url,
            "pr_number": pr_num,
            "simulated": False,
            "message": f"Pull Request #{pr_num} created successfully on {repo}."
        }

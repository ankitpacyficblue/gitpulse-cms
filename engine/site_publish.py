"""Where a published post goes. GitPulse itself is the live source: websites read posts from the public API (or the
embed script), so publishing needs no commit, release or setup. Committing to the website repository is the older
path, off unless the server sets PUBLISH_VIA_GIT=1."""
import os


def git_enabled() -> bool:
    return os.environ.get("PUBLISH_VIA_GIT") == "1"


def post_url(project_id: int, slug: str, origin: str) -> str:
    """A page a person can read."""
    return f"{origin}/api/public/projects/{project_id}/posts/{slug}/view"

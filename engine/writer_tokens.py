"""Per-account tokens for AI blog writers. A token can upload images and hand in drafts for review; it can
never approve or publish, and sees only what it wrote. Only the token's hash is stored."""
import hashlib
import re
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import crm_store as cs
import database as db
from engine import blog_plan, media

PREFIX = "gpw_"
MAX_TOKENS = 20
MAX_PER_HOUR = 100      # requests per token, so a looping agent cannot fill the shared database
FIELDS = ("title", "topic", "keyword", "publish_at", "body", "images", "meta_description")
_RAW_HTML = re.compile(r"<[a-zA-Z/!?]|\]\(\s*<?\s*(?:javascript|data|vbscript):", re.I)


class WriterError(blog_plan.PlanError):
    pass


def _now() -> str:
    return datetime.utcnow().isoformat()


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ------------------------------------------------------------------ managed by the admin

def list_tokens(account_id: str) -> List[Dict[str, Any]]:
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM writer_tokens WHERE account_id = ? ORDER BY id DESC",
                                              (account_id,)).fetchall()]
    names = {m["user_id"]: m["username"] for m in cs.list_members(account_id)}
    return [{"id": r["id"], "name": r["name"], "prefix": f"{PREFIX}…{r['hint']}", "project_id": r["project_id"],
             "created_at": r["created_at"] + "Z", "created_by_name": names.get(r["created_by"]),
             "last_used_at": r["last_used_at"] + "Z" if r["last_used_at"] else None,
             "revoked_at": r["revoked_at"] + "Z" if r["revoked_at"] else None} for r in rows]


def create(account_id: str, name: Any, user_id: int, project_id: Any = None) -> Dict[str, Any]:
    """The raw token is returned here and nowhere else."""
    name = str(name or "").strip()[:60]
    if not name:
        raise WriterError(400, "name_required", "Name the writer this token is for.")
    if project_id not in (None, "", 0):
        project = db.get_project(int(project_id)) if str(project_id).isdigit() else None
        if not project or project.get("account_id") != account_id:
            raise WriterError(404, "project_not_found", "Blog project not found.")
        project_id = project["id"]
    else:
        project_id = None
    if sum(1 for t in list_tokens(account_id) if not t["revoked_at"]) >= MAX_TOKENS:
        raise WriterError(409, "too_many_tokens", f"An account can have {MAX_TOKENS} active tokens.")
    raw = PREFIX + secrets.token_urlsafe(32)
    with db.get_connection() as conn:
        token_id = conn.execute("INSERT INTO writer_tokens (account_id, name, token_hash, hint, created_by, created_at, "
                                "project_id) VALUES (?,?,?,?,?,?,?)",
                                (account_id, name, _hash(raw), raw[-4:], user_id, _now(), project_id)).lastrowid
        conn.commit()
    return {"token": raw, "item": next(t for t in list_tokens(account_id) if t["id"] == token_id)}


def revoke(account_id: str, token_id: int) -> None:
    with db.get_connection() as conn:
        found = conn.execute("UPDATE writer_tokens SET revoked_at = ? WHERE id = ? AND account_id = ? AND revoked_at = ''",
                             (_now(), token_id, account_id)).rowcount
        conn.commit()
    if not found:
        raise WriterError(404, "token_not_found", "No active token with that id.")


def authenticate(authorization: str) -> Optional[Dict[str, Any]]:
    """The token's writer, with `over_limit` set once it has used up this hour. None: not a valid token."""
    raw = authorization.removeprefix("Bearer ").strip()
    if not raw.startswith(PREFIX):
        return None
    now = time.time()
    with db.get_connection() as conn:
        row = conn.execute("SELECT t.id FROM writer_tokens t JOIN accounts a ON a.id = t.account_id "
                           "WHERE t.token_hash = ? AND t.revoked_at = '' AND a.status = 'active'", (_hash(raw),)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE writer_tokens SET window_count = CASE WHEN window_start > ? THEN window_count + 1 ELSE 1 END, "
                     "window_start = CASE WHEN window_start > ? THEN window_start ELSE ? END, last_used_at = ? WHERE id = ?",
                     (now - 3600, now - 3600, now, _now(), row["id"]))
        writer = dict(conn.execute("SELECT id, account_id, name, project_id, window_count FROM writer_tokens WHERE id = ?",
                                   (row["id"],)).fetchone())
        conn.commit()
    writer["over_limit"] = writer["window_count"] > MAX_PER_HOUR
    return writer


# ------------------------------------------------------------------ used by the writer

def _own_file(writer: Dict[str, Any], **where: Any) -> bool:
    (column, value), = where.items()
    with db.get_connection() as conn:
        return conn.execute(f"SELECT 1 FROM media_files WHERE {column} = ? AND account_id = ? AND writer_token_id = ?",
                            (value, writer["account_id"], writer["id"])).fetchone() is not None


def upload_url(writer: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    if not str(data.get("mime") or "").lower().startswith("image/"):
        raise media.MediaError(400, "type_not_allowed", "A writer token can upload JPEG, PNG or WebP images only.")
    out = media.create_upload(writer["account_id"], None, data)
    with db.get_connection() as conn:
        conn.execute("UPDATE media_files SET writer_token_id = ? WHERE id = ? AND account_id = ?",
                     (writer["id"], out["media_id"], writer["account_id"]))
        conn.commit()
    return out


def confirm(writer: Dict[str, Any], media_id: Any, host: str) -> Dict[str, Any]:
    if not str(media_id).isdigit() or not _own_file(writer, id=int(media_id)):
        raise media.MediaError(404, "media_not_found", "File not found.")
    item = media.confirm(writer["account_id"], media_id, host)
    return {"media_id": item["id"], "name": item["name"], "markdown_url": item["blog_url"]}


def _clean(writer: Dict[str, Any], data: Dict[str, Any], attached: List[int] = ()) -> Dict[str, Any]:
    """`attached`: images already on the post (an admin may have added them), which may be sent back."""
    out = {k: data[k] for k in FIELDS if k in data}
    for key in ("title", "body", "meta_description"):
        if _RAW_HTML.search(str(out.get(key) or "")):
            raise WriterError(400, "html_not_allowed", "Send plain Markdown: no HTML tags or script links.")
    images = out.get("images")
    for image in images if isinstance(images, list) else []:
        media_id = image.get("media_id") if isinstance(image, dict) else None
        if not str(media_id).isdigit() or not (int(media_id) in attached or _own_file(writer, id=int(media_id))):
            raise WriterError(404, "media_not_found", "A writer can attach only images it uploaded.")
    if any(not _own_file(writer, token=t) for t in media.tokens_in(str(out.get("body") or ""))):
        raise WriterError(404, "media_not_found", "The text links to a file this writer did not upload.")
    return out


def _view(item: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("id", "title", "topic", "keyword", "publish_at", "body", "status", "state", "rejected_note",
            "published_at", "post_url", "error", "meta_description")
    project = db.get_project(item["project_id"]) if item["project_id"] else None
    return dict({k: item[k] for k in keys},
                project={"id": project["id"], "name": project["name"]} if project else None,
                images=[{k: i[k] for k in ("media_id", "alt", "cover")} for i in item["images"]])


def _ids(writer: Dict[str, Any]) -> List[int]:
    with db.get_connection() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM blog_plan WHERE account_id = ? AND writer_token_id = ?",
                                              (writer["account_id"], writer["id"])).fetchall()]


def _mine(writer: Dict[str, Any], item_id: int) -> Dict[str, Any]:
    """A post this token created or was given."""
    if item_id not in _ids(writer):
        raise WriterError(404, "not_found", "Planned post not found.")
    return blog_plan.get_item(writer["account_id"], item_id)


def posts(writer: Dict[str, Any]) -> List[Dict[str, Any]]:
    mine = set(_ids(writer))
    return [_view(i) for i in blog_plan.list_items(writer["account_id"]) if i["id"] in mine]


def post(writer: Dict[str, Any], item_id: int) -> Dict[str, Any]:
    return _view(_mine(writer, item_id))


def _default_project(writer: Dict[str, Any]) -> Optional[int]:
    with db.get_connection() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM projects WHERE account_id = ?", (writer["account_id"],)).fetchall()]
    if writer["project_id"] in ids:
        return writer["project_id"]
    return ids[0] if len(ids) == 1 else None


def _by_external(writer: Dict[str, Any], external_id: str) -> Optional[Dict[str, Any]]:
    with db.get_connection() as conn:
        row = conn.execute("SELECT id FROM blog_plan WHERE account_id = ? AND writer_token_id = ? AND external_id = ?",
                           (writer["account_id"], writer["id"], external_id)).fetchone()
    return post(writer, row["id"]) if row else None


def create_draft(writer: Dict[str, Any], data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """(post, created). Always a draft. A repeated external_id returns the first post, so a retry adds nothing."""
    external_id = str(data.get("external_id") or "").strip()[:200]
    if external_id:
        existing = _by_external(writer, external_id)
        if existing:
            return existing, False
    fields = dict(_clean(writer, data), writer_token_id=writer["id"], project_id=_default_project(writer))
    try:
        item_id = blog_plan.create(writer["account_id"], fields, external_id=external_id)["id"]
    except blog_plan.PlanError:
        raise
    except Exception:      # the same external_id arrived twice at once and the unique index refused the second
        existing = _by_external(writer, external_id) if external_id else None
        if not existing:
            raise
        return existing, False
    return post(writer, item_id), True


def revise(writer: Dict[str, Any], item_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Change a draft (rejected ones too) or a post still waiting. Approved text is out of reach."""
    item = _mine(writer, item_id)
    if item["status"] not in ("draft", "needs_approval"):
        raise WriterError(409, "wrong_status", "Only a post that is not yet approved can be changed.")
    fields = _clean(writer, data, [i["media_id"] for i in item["images"]])
    return _view(blog_plan.update(writer["account_id"], item_id, fields))


def submit(writer: Dict[str, Any], item_id: int) -> Dict[str, Any]:
    _mine(writer, item_id)
    return _view(blog_plan.submit(writer["account_id"], item_id))

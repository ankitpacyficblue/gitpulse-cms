"""Per-account tokens for AI blog writers. A token can upload images and hand in drafts for review; it can
never approve or publish, and sees only what it wrote. Only the token's hash is stored."""
import hashlib
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

import crm_store as cs
import database as db
from engine import blog_plan, media

PREFIX = "gpw_"
MAX_TOKENS = 20
MAX_WAITING = 50        # drafts of one account waiting for approval, so a runaway writer cannot flood it
FIELDS = ("title", "topic", "keyword", "publish_at", "project_id", "body", "images")
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
        rows = conn.execute("SELECT id, name, hint, created_at, last_used_at, revoked_at FROM writer_tokens "
                            "WHERE account_id = ? ORDER BY id DESC", (account_id,)).fetchall()
    return [{"id": r["id"], "name": r["name"], "hint": r["hint"], "created_at": r["created_at"] + "Z",
             "last_used_at": r["last_used_at"] + "Z" if r["last_used_at"] else None,
             "revoked_at": r["revoked_at"] + "Z" if r["revoked_at"] else None} for r in rows]


def create(account_id: str, name: Any, user_id: int) -> Dict[str, Any]:
    """The raw token is returned here and nowhere else."""
    name = str(name or "").strip()[:60]
    if not name:
        raise WriterError(400, "name_required", "Name the writer this token is for.")
    if sum(1 for t in list_tokens(account_id) if not t["revoked_at"]) >= MAX_TOKENS:
        raise WriterError(409, "too_many_tokens", f"An account can have {MAX_TOKENS} active tokens.")
    raw = PREFIX + secrets.token_urlsafe(32)
    with db.get_connection() as conn:
        token_id = conn.execute("INSERT INTO writer_tokens (account_id, name, token_hash, hint, created_by, created_at) "
                                "VALUES (?,?,?,?,?,?)", (account_id, name, _hash(raw), raw[-4:], user_id, _now())).lastrowid
        conn.commit()
    return {"id": token_id, "name": name, "token": raw}


def revoke(account_id: str, token_id: int) -> None:
    with db.get_connection() as conn:
        found = conn.execute("UPDATE writer_tokens SET revoked_at = ? WHERE id = ? AND account_id = ? AND revoked_at = ''",
                             (_now(), token_id, account_id)).rowcount
        conn.commit()
    if not found:
        raise WriterError(404, "token_not_found", "No active token with that id.")


def authenticate(authorization: str) -> Optional[Dict[str, Any]]:
    raw = authorization.removeprefix("Bearer ").strip()
    if not raw.startswith(PREFIX):
        return None
    with db.get_connection() as conn:
        row = conn.execute("SELECT t.id, t.account_id, t.name FROM writer_tokens t JOIN accounts a ON a.id = t.account_id "
                           "WHERE t.token_hash = ? AND t.revoked_at = '' AND a.status = 'active'", (_hash(raw),)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE writer_tokens SET last_used_at = ? WHERE id = ?", (_now(), row["id"]))
        conn.commit()
    return dict(row)


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


def _clean(writer: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: data[k] for k in FIELDS if k in data}
    for key in ("title", "body"):
        if _RAW_HTML.search(str(out.get(key) or "")):
            raise WriterError(400, "html_not_allowed", "Send plain Markdown: no HTML tags or script links.")
    images = out.get("images")
    for image in images if isinstance(images, list) else []:
        media_id = image.get("media_id") if isinstance(image, dict) else None
        if not str(media_id).isdigit() or not _own_file(writer, id=int(media_id)):
            raise WriterError(404, "media_not_found", "A writer can attach only images it uploaded.")
    if any(not _own_file(writer, token=t) for t in media.tokens_in(str(out.get("body") or ""))):
        raise WriterError(404, "media_not_found", "The text links to a file this writer did not upload.")
    return out


def _view(writer: Dict[str, Any], item: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("id", "title", "topic", "keyword", "publish_at", "project_id", "body", "state", "rejected_note",
            "published_at", "post_url", "error")
    return dict({k: item[k] for k in keys},
                images=[{k: i[k] for k in ("media_id", "alt", "cover")} for i in item["images"]])


def _ids(writer: Dict[str, Any]) -> List[int]:
    with db.get_connection() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM blog_plan WHERE account_id = ? AND writer_token_id = ?",
                                              (writer["account_id"], writer["id"])).fetchall()]


def posts(writer: Dict[str, Any]) -> List[Dict[str, Any]]:
    mine = set(_ids(writer))
    return [_view(writer, i) for i in blog_plan.list_items(writer["account_id"]) if i["id"] in mine]


def projects(writer: Dict[str, Any]) -> List[Dict[str, Any]]:
    with db.get_connection() as conn:
        rows = conn.execute("SELECT id, name FROM projects WHERE account_id = ? ORDER BY id", (writer["account_id"],)).fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def _check_room(account_id: str) -> None:
    with db.get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM blog_plan WHERE account_id = ? AND status = 'needs_approval'",
                         (account_id,)).fetchone()["n"]
    if n >= MAX_WAITING:
        raise WriterError(409, "too_many_waiting", "Too many posts are waiting for approval. Try again later.")


def submit_draft(writer: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """A new post that goes straight to review."""
    account_id = writer["account_id"]
    fields = _clean(writer, data)
    if not str(fields.get("body") or "").strip():
        raise WriterError(400, "body_required", "Send the post text.")
    _check_room(account_id)
    if not fields.get("project_id") and len(projects(writer)) == 1:
        fields["project_id"] = projects(writer)[0]["id"]
    item_id = blog_plan.create(account_id, fields)["id"]
    with db.get_connection() as conn:
        conn.execute("UPDATE blog_plan SET writer_token_id = ? WHERE id = ? AND account_id = ?",
                     (writer["id"], item_id, account_id))
        conn.commit()
    return _view(writer, blog_plan.submit(account_id, item_id))


def revise(writer: Dict[str, Any], item_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Fix a rejected or still waiting post and send it to review again. Approved text is out of reach."""
    account_id = writer["account_id"]
    if item_id not in _ids(writer):
        raise WriterError(404, "not_found", "Planned post not found.")
    status = blog_plan.get_item(account_id, item_id)["status"]
    if status not in ("draft", "needs_approval"):
        raise WriterError(409, "wrong_status", "Only a post that is not yet approved can be changed.")
    fields = _clean(writer, data)
    if "body" in fields and not str(fields["body"] or "").strip():
        raise WriterError(400, "body_required", "Send the post text.")
    if status == "draft":
        _check_room(account_id)
    item = blog_plan.update(account_id, item_id, fields)
    if item["status"] == "draft":
        item = blog_plan.submit(account_id, item_id)
    return _view(writer, item)

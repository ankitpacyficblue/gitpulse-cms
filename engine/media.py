"""Media library per account, kept in a private Supabase Storage bucket.

The browser uploads straight to storage with a signed link, then confirms; only then does the server
read the size and the first bytes, and delete anything that is not what it claimed to be. Files are
never public, except those a published blog post links to, served through /api/public/media/<token>.

Without MEDIA_SUPABASE_URL, MEDIA_SUPABASE_KEY and MEDIA_BUCKET the library is simply switched off.
These names are deliberately not SUPABASE_*, which would turn on the legacy row mirror."""
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import crm_store as cs
import database as db
from engine import jobs

MB = 1024 * 1024
# mime -> (extension, limit, WhatsApp message type or None)
TYPES = {
    "image/jpeg": ("jpg", 5 * MB, "image"),
    "image/png": ("png", 5 * MB, "image"),
    "image/webp": ("webp", 5 * MB, None),
    "application/pdf": ("pdf", 20 * MB, "document"),
    "video/mp4": ("mp4", 16 * MB, "video"),
}
VIEW_SECONDS = 3600
SEND_SECONDS = 24 * 3600      # Meta fetches the link when it processes the message
PUBLIC_PATH = "/api/public/media/"


class MediaError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(message or code)
        self.status, self.code, self.message = status, code, message


def configured() -> bool:
    return all(os.environ.get(k) for k in ("MEDIA_SUPABASE_URL", "MEDIA_SUPABASE_KEY", "MEDIA_BUCKET"))


def require() -> None:
    if not configured():
        raise MediaError(503, "media_not_configured", "The media library is not set up yet.")


def sniff(head: bytes) -> str:
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head[4:8] == b"ftyp":
        return "video/mp4"
    return ""


# ------------------------------------------------------------------ storage (Supabase Storage REST)

def _base() -> str:
    return os.environ["MEDIA_SUPABASE_URL"].rstrip("/") + "/storage/v1"


def _object(path: str) -> str:
    return urllib.parse.quote(os.environ["MEDIA_BUCKET"] + "/" + path)


def _request(method: str, route: str, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None):
    key = os.environ["MEDIA_SUPABASE_KEY"]
    req = urllib.request.Request(_base() + route, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}", "apikey": key, **(headers or {})})
    return urllib.request.urlopen(req, timeout=20)


def _json(method: str, route: str, payload: Any) -> Any:
    try:
        with _request(method, route, json.dumps(payload).encode(), {"Content-Type": "application/json"}) as resp:
            return json.loads(resp.read().decode() or "{}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise MediaError(502, "storage_error", f"Storage did not answer ({type(e).__name__}).")


def storage_sign_upload(path: str) -> str:
    return _base() + _json("POST", "/object/upload/sign/" + _object(path), {})["url"]


def storage_sign(paths: List[str], seconds: int) -> Dict[str, str]:
    if not paths:
        return {}
    rows = _json("POST", "/object/sign/" + urllib.parse.quote(os.environ["MEDIA_BUCKET"]),
                 {"expiresIn": seconds, "paths": paths})
    return {r["path"]: _base() + r["signedURL"] for r in rows if r.get("signedURL")}


def storage_head(path: str) -> Optional[Tuple[int, bytes]]:
    """(size, first bytes), or None when nothing was uploaded."""
    try:
        with _request("GET", "/object/" + _object(path), headers={"Range": "bytes=0-15"}) as resp:
            total = (resp.headers.get("Content-Range") or "").rpartition("/")[2] or resp.headers.get("Content-Length")
            return int(total), resp.read(16)
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return None
        raise MediaError(502, "storage_error", f"Storage refused the request (HTTP {e.code}).")
    except (urllib.error.URLError, OSError, ValueError, TypeError) as e:
        raise MediaError(502, "storage_error", f"Storage did not answer ({type(e).__name__}).")


def storage_remove(paths: List[str]) -> None:
    _json("DELETE", "/object/" + urllib.parse.quote(os.environ["MEDIA_BUCKET"]), {"prefixes": paths})


def storage_put(path: str, content: bytes, mime: str) -> None:
    try:
        with _request("POST", "/object/" + _object(path), content, {"Content-Type": mime}):
            pass
    except (urllib.error.URLError, OSError) as e:
        raise MediaError(502, "storage_error", f"Storage did not take the file ({type(e).__name__}).")


# ------------------------------------------------------------------ library

def _row(account_id: str, media_id: Any, status: str = "ready") -> Dict[str, Any]:
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM media_files WHERE id = ? AND account_id = ? AND status = ?",
                           (int(media_id) if str(media_id).isdigit() else 0, account_id, status)).fetchone()
    if not row:
        raise MediaError(404, "media_not_found", "File not found.")
    return dict(row)


get = _row


def _insert(account_id: str, name: str, mime: str, size: int, status: str, source: str, user_id: Optional[int]) -> Dict[str, Any]:
    token = secrets.token_urlsafe(24)
    path = f"{account_id}/{token}.{TYPES[mime][0]}"
    with db.get_connection() as conn:
        media_id = conn.execute(
            "INSERT INTO media_files (account_id, name, mime, size, path, token, status, source, is_public, created_by, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,0,?,?)",
            (account_id, name, mime, size, path, token, status, source, user_id, datetime.utcnow().isoformat())).lastrowid
        conn.commit()
    return {"id": media_id, "path": path}


def _drop(account_id: str, row: Dict[str, Any]) -> None:
    storage_remove([row["path"]])
    with db.get_connection() as conn:
        conn.execute("DELETE FROM media_files WHERE id = ? AND account_id = ?", (row["id"], account_id))
        conn.commit()


def create_upload(account_id: str, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    require()
    name = re.sub(r"[\x00-\x1f/\\]", "_", str(data.get("name") or "")).strip()[:150]
    mime = str(data.get("mime") or "").lower()
    size = data.get("size")
    if not name:
        raise MediaError(400, "name_required", "The file needs a name.")
    if mime not in TYPES:
        raise MediaError(400, "type_not_allowed", "Use a JPEG, PNG, WebP, PDF or MP4 file.")
    if not isinstance(size, int) or size <= 0:
        raise MediaError(400, "size_required", "Send the file size in bytes.")
    if size > TYPES[mime][1]:
        raise MediaError(400, "too_large", f"This type can be at most {TYPES[mime][1] // MB} MB.")
    row = _insert(account_id, name, mime, size, "pending", "library", user_id)
    return {"media_id": row["id"], "upload_url": storage_sign_upload(row["path"]), "method": "PUT",
            "headers": {"Content-Type": mime}, "max_bytes": TYPES[mime][1]}


def confirm(account_id: str, media_id: Any, host: str = "") -> Dict[str, Any]:
    require()
    row = _row(account_id, media_id, status="pending")
    found = storage_head(row["path"])
    if not found:
        raise MediaError(409, "not_uploaded", "The file has not arrived in storage yet.")
    size, head = found
    if size > TYPES[row["mime"]][1] or sniff(head) != row["mime"]:
        _drop(account_id, row)
        raise MediaError(400, "file_rejected", "The uploaded file is too large or is not the type it claimed to be.")
    with db.get_connection() as conn:
        conn.execute("UPDATE media_files SET status = 'ready', size = ? WHERE id = ? AND account_id = ?",
                     (size, row["id"], account_id))
        conn.commit()
    return _present(account_id, [dict(row, size=size)], host)[0]


def used_by(account_id: str, row: Dict[str, Any]) -> List[str]:
    out = []
    with db.get_connection() as conn:
        for label, query, arg in (
            ("chat", "SELECT 1 FROM messages WHERE account_id = ? AND media_id = ?", row["id"]),
            ("broadcast", "SELECT 1 FROM broadcasts WHERE account_id = ? AND media_id = ?", row["id"]),
            ("blog", "SELECT 1 FROM blog_plan WHERE account_id = ? AND body LIKE ?", f"%{PUBLIC_PATH}{row['token']}%"),
        ):
            if conn.execute(query + " LIMIT 1", (account_id, arg)).fetchone():
                out.append(label)
    return out


def _present(account_id: str, rows: List[Dict[str, Any]], host: str) -> List[Dict[str, Any]]:
    links = storage_sign([r["path"] for r in rows], VIEW_SECONDS)
    origin = f"https://{host}" if host else ""
    return [{"id": r["id"], "name": r["name"], "mime": r["mime"], "size": r["size"], "created_at": r["created_at"] + "Z",
             "preview_url": links.get(r["path"]), "blog_url": origin + PUBLIC_PATH + r["token"],
             "is_public": bool(r["is_public"]), "whatsapp_type": TYPES[r["mime"]][2],
             "used_by": used_by(account_id, r)} for r in rows]


def list_items(account_id: str, search: str = "", host: str = "") -> List[Dict[str, Any]]:
    require()
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM media_files WHERE account_id = ? AND status = 'ready' AND source = 'library' "
            "ORDER BY id DESC LIMIT 200", (account_id,)).fetchall()]
    wanted = search.strip().lower()
    return _present(account_id, [r for r in rows if wanted in r["name"].lower()], host)


def delete(account_id: str, media_id: Any, force: bool = False) -> None:
    require()
    row = _row(account_id, media_id)
    uses = used_by(account_id, row)
    if uses and not force:
        raise MediaError(409, "in_use", "This file is used in: " + ", ".join(uses) + ".")
    _drop(account_id, row)


def publish_linked(account_id: str, text: str) -> None:
    """A published post makes exactly the files it links to public."""
    tokens = re.findall(re.escape(PUBLIC_PATH) + r"([A-Za-z0-9_-]+)", text)
    if not tokens:
        return
    with db.get_connection() as conn:
        for token in set(tokens):
            conn.execute("UPDATE media_files SET is_public = 1 WHERE account_id = ? AND token = ? AND status = 'ready'",
                         (account_id, token))
        conn.commit()


def public_link(token: str) -> Optional[str]:
    if not configured():
        return None
    with db.get_connection() as conn:
        row = conn.execute("SELECT path FROM media_files WHERE token = ? AND is_public = 1 AND status = 'ready'",
                           (token,)).fetchone()
    if not row:
        return None
    return storage_sign([row["path"]], VIEW_SECONDS).get(row["path"])


def send_link(account_id: str, media_id: Any) -> Dict[str, str]:
    """What WhatsApp needs to send this file: its message type, a short-lived link and the file name."""
    require()
    row = _row(account_id, media_id)
    kind = TYPES[row["mime"]][2]
    if not kind:
        raise MediaError(400, "unsupported_on_whatsapp", "WhatsApp does not take WebP. Use JPEG or PNG.")
    link = storage_sign([row["path"]], SEND_SECONDS).get(row["path"])
    if not link:
        raise MediaError(502, "storage_error", "Storage gave no link for this file.")
    return {"kind": kind, "link": link, "filename": row["name"]}


def attach(account_id: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add {media: {id, name, mime, url}} to messages that carry a file."""
    ids = sorted({m["media_id"] for m in messages if m.get("media_id")})
    if not ids:
        return messages
    with db.get_connection() as conn:
        rows = {r["id"]: dict(r) for r in conn.execute(
            f"SELECT * FROM media_files WHERE account_id = ? AND id IN ({','.join('?' * len(ids))})",
            (account_id, *ids)).fetchall()}
    links: Dict[str, str] = {}
    if configured():
        try:
            links = storage_sign([r["path"] for r in rows.values()], VIEW_SECONDS)
        except MediaError:
            pass        # the conversation still opens; the files just have no link
    for m in messages:
        row = rows.get(m.get("media_id"))
        if row:
            m["media"] = {"id": row["id"], "name": row["name"], "mime": row["mime"], "url": links.get(row["path"])}
    return messages


# ------------------------------------------------------------------ inbound files

def download_from_meta(account_id: str, wa_media_id: str) -> bytes:
    token = cs.get_whatsapp_credentials(account_id)["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    url = "https://graph.facebook.com/v21.0/" + urllib.parse.quote(wa_media_id, safe="")
    with urllib.request.urlopen(urllib.request.Request(url, headers=auth), timeout=15) as resp:
        target = json.loads(resp.read().decode())["url"]
    host = urllib.parse.urlparse(target)
    if host.scheme != "https" or not (host.hostname or "").endswith((".fbsbx.com", ".facebook.com", ".whatsapp.net")):
        raise ValueError("unexpected media host")       # the token must only ever go to Meta
    with urllib.request.urlopen(urllib.request.Request(target, headers=auth), timeout=20) as resp:
        return resp.read(20 * MB + 1)


@jobs.handler("media_fetch")
def _fetch_job(job: Dict[str, Any]) -> None:
    account_id, p = job["account_id"], job["payload"]
    if not configured():
        return
    try:
        content = download_from_meta(account_id, p["wa_media_id"])
        mime = sniff(content[:16])
        if not mime or len(content) > TYPES[mime][1]:
            return          # a type or size the library does not keep; the chat keeps its placeholder
        name = (p.get("filename") or f"received-{p['message_id']}.{TYPES[mime][0]}")[:150]
        row = _insert(account_id, name, mime, len(content), "pending", "inbound", None)
        storage_put(row["path"], content, mime)
    except (MediaError, urllib.error.URLError, OSError, ValueError, KeyError) as e:
        raise jobs.Retry(f"incoming file not stored ({type(e).__name__})")
    with db.get_connection() as conn:
        conn.execute("UPDATE media_files SET status = 'ready' WHERE id = ? AND account_id = ?", (row["id"], account_id))
        conn.execute("UPDATE messages SET media_id = ? WHERE id = ? AND account_id = ?",
                     (row["id"], p["message_id"], account_id))
        conn.commit()

"""The editorial plan per account, and the only automatic publisher.

draft -> needs_approval -> approved -> published (or failed). Only an approved post whose time has
come is sent to the site, once: the job is keyed on the approved version, and a failed or
interrupted publish is not repeated until someone approves it again."""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import crm_store as cs
import database as db
from engine import alerts, assistant, jobs, llm, media
from engine.messaging import IST

EDITABLE = ("title", "topic", "keyword", "publish_at", "project_id", "assignee_id", "body", "images")
MAX_IMAGES = 20


class PlanError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(message or code)
        self.status, self.code, self.message = status, code, message


def _now() -> str:
    return datetime.utcnow().isoformat()


def _parse_time(value: Any) -> str:
    """Any ISO time -> naive UTC. A time without a zone is taken as UTC."""
    if value in (None, ""):
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise PlanError(400, "invalid_publish_at", "publish_at must be an ISO date and time.")
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0).isoformat()


def _view(row: Dict[str, Any], names: Dict[int, str], files: Dict[int, Dict[str, Any]], links: Dict[str, str],
          host: str) -> Dict[str, Any]:
    d = {k: row[k] for k in ("id", "title", "topic", "keyword", "status", "body", "project_id", "assignee_id",
                             "post_url", "error")}
    d["publish_at"] = row["publish_at"] + "Z" if row["publish_at"] else None
    d["assignee_name"] = names.get(row["assignee_id"])
    origin = f"https://{host}" if host else ""
    d["images"] = []
    for image in json.loads(row["images"] or "[]"):
        f = files.get(image["media_id"])
        d["images"].append(dict(image, name=f["name"] if f else None, url=links.get(f["path"]) if f else None,
                                public_url=origin + media.PUBLIC_PATH + f["token"] if f else None))
    d["rejected_note"] = row["rejected_note"] or None
    d["rejected_by_name"] = names.get(row["rejected_by"]) if row["rejected_note"] else None
    d["rejected_at"] = row["rejected_at"] + "Z" if row["rejected_note"] else None
    return d


def _views(account_id: str, rows: List[Dict[str, Any]], host: str) -> List[Dict[str, Any]]:
    wanted = sorted({i["media_id"] for r in rows for i in json.loads(r["images"] or "[]")})
    files: Dict[int, Dict[str, Any]] = {}
    for media_id in wanted:
        try:
            files[media_id] = media.get(account_id, media_id)
        except media.MediaError:
            pass
    links = media.views(list(files.values()))
    names = _names(account_id)
    return [_view(r, names, files, links, host) for r in rows]


def _names(account_id: str) -> Dict[int, str]:
    return {m["user_id"]: m["username"] for m in cs.list_members(account_id)}


def _row(account_id: str, item_id: int) -> Dict[str, Any]:
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM blog_plan WHERE id = ? AND account_id = ?", (item_id, account_id)).fetchone()
    if not row:
        raise PlanError(404, "not_found", "Planned post not found.")
    return dict(row)


def get_item(account_id: str, item_id: int, host: str = "") -> Dict[str, Any]:
    return _views(account_id, [_row(account_id, item_id)], host)[0]


def list_items(account_id: str, status: str = "", assignee_id: Optional[int] = None, host: str = "") -> List[Dict[str, Any]]:
    q, args = "SELECT * FROM blog_plan WHERE account_id = ?", [account_id]
    if status:
        q += " AND status = ?"
        args.append(status)
    if assignee_id is not None:
        q += " AND assignee_id = ?"
        args.append(assignee_id)
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(q + " ORDER BY publish_at, id LIMIT 500", args).fetchall()]
    return _views(account_id, rows, host)


def _clean_images(account_id: str, value: Any) -> str:
    """[{media_id, alt, cover}] -> stored JSON. Only this account's images; at most one cover."""
    if value in (None, ""):
        return "[]"
    if not isinstance(value, list) or len(value) > MAX_IMAGES or not all(isinstance(i, dict) for i in value):
        raise PlanError(400, "invalid_images", f"images must be a list of at most {MAX_IMAGES} entries.")
    out: List[Dict[str, Any]] = []
    for image in value:
        try:
            f = media.get(account_id, image.get("media_id"))
        except media.MediaError:
            raise PlanError(404, "media_not_found", "That image is not in this account's media library.")
        if not f["mime"].startswith("image/"):
            raise PlanError(400, "not_an_image", f"'{f['name']}' is not an image.")
        if any(i["media_id"] == f["id"] for i in out):
            continue
        cover = bool(image.get("cover")) and not any(i["cover"] for i in out)
        out.append({"media_id": f["id"], "alt": str(image.get("alt") or "").strip()[:200], "cover": cover})
    return json.dumps(out)


def _clean(account_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in EDITABLE:
        if key not in data:
            continue
        value = data[key]
        if key == "publish_at":
            out[key] = _parse_time(value)
        elif key == "images":
            out[key] = _clean_images(account_id, value)
        elif key in ("project_id", "assignee_id"):
            if value in (None, "", 0):
                out[key] = None
                continue
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise PlanError(400, "invalid_" + key)
            if key == "project_id":
                project = db.get_project(value)
                if not project or project.get("account_id") != account_id:
                    raise PlanError(404, "project_not_found", "Blog project not found.")
            elif not cs.get_membership_role(account_id, value):
                raise PlanError(404, "assignee_not_found", "That person is not in this account.")
            out[key] = value
        else:
            out[key] = ("" if value is None else str(value))[:100000 if key == "body" else 300].strip()
    return out


def create(account_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    f = _clean(account_id, data)
    if not f.get("title"):
        raise PlanError(400, "title_required", "Give the post a title.")
    now = _now()
    with db.get_connection() as conn:
        cur = conn.execute("""INSERT INTO blog_plan (account_id, project_id, title, topic, keyword, publish_at, status, body,
                              assignee_id, created_at, updated_at, images) VALUES (?,?,?,?,?,?,'draft',?,?,?,?,?)""",
                           (account_id, f.get("project_id"), f["title"], f.get("topic", ""), f.get("keyword", ""),
                            f.get("publish_at", ""), f.get("body", ""), f.get("assignee_id"), now, now, f.get("images", "[]")))
        item_id = cur.lastrowid
        conn.commit()
    return get_item(account_id, item_id)


def _set(account_id: str, item_id: int, expected_status: Optional[str] = None, **fields) -> bool:
    """With expected_status, change only if nobody moved the item meanwhile."""
    fields["updated_at"] = datetime.utcnow().isoformat()
    q = f"UPDATE blog_plan SET {', '.join(k + ' = ?' for k in fields)} WHERE id = ? AND account_id = ?"
    args = [*fields.values(), item_id, account_id]
    if expected_status:
        q += " AND status = ?"
        args.append(expected_status)
    with db.get_connection() as conn:
        changed = conn.execute(q, args).rowcount > 0
        conn.commit()
    return changed


def update(account_id: str, item_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    row = _row(account_id, item_id)
    if row["status"] == "published":
        raise PlanError(409, "already_published", "A published post cannot be edited here.")
    f = {k: v for k, v in _clean(account_id, data).items() if v != row[k]}
    if "title" in f and not f["title"]:
        raise PlanError(400, "title_required", "Give the post a title.")
    if f:
        content = set(f) - {"assignee_id"}          # reassigning does not change what was approved
        if row["status"] == "approved" and content:
            f["status"] = "needs_approval"
        elif row["status"] == "failed":
            f["status"] = "draft"
        _set(account_id, item_id, error="", **f)
    return get_item(account_id, item_id)


def delete(account_id: str, item_id: int) -> None:
    _row(account_id, item_id)
    with db.get_connection() as conn:
        conn.execute("DELETE FROM blog_plan WHERE id = ? AND account_id = ?", (item_id, account_id))
        conn.commit()


def submit(account_id: str, item_id: int) -> Dict[str, Any]:
    row = _row(account_id, item_id)
    if row["status"] not in ("draft", "failed"):
        raise PlanError(409, "wrong_status", f"A post that is '{row['status']}' cannot be submitted.")
    if not row["body"]:
        raise PlanError(409, "empty_body", "Write or draft the post first.")
    _set(account_id, item_id, expected_status=row["status"], status="needs_approval", error="", rejected_note="")
    return get_item(account_id, item_id)


def reject(account_id: str, item_id: int, note: Any, user_id: int) -> Dict[str, Any]:
    row = _row(account_id, item_id)
    note = str(note or "").strip()[:1000]
    if not note:
        raise PlanError(400, "note_required", "Say what needs to change.")
    if row["status"] != "needs_approval" or not _set(account_id, item_id, expected_status="needs_approval", status="draft",
                                                     error="", rejected_note=note, rejected_by=user_id, rejected_at=_now()):
        raise PlanError(409, "wrong_status", "Only a post waiting for approval can be rejected.")
    return get_item(account_id, item_id)


def approve(account_id: str, item_id: int, host: str = "") -> Dict[str, Any]:
    row = _row(account_id, item_id)
    if row["status"] != "needs_approval":
        raise PlanError(409, "wrong_status", "Only a post waiting for approval can be approved.")
    missing = [name for name, key in (("body", "body"), ("blog project", "project_id"), ("publish date", "publish_at"))
               if not row[key]]
    if missing:
        raise PlanError(409, "incomplete", "Add first: " + ", ".join(missing) + ".")
    blocked = _guard(account_id, row)
    if blocked:
        raise PlanError(409, "blocked", f"This post cannot be approved: {blocked}.")
    _post_files(account_id, row)
    if not _set(account_id, item_id, expected_status="needs_approval", status="approved", error="", rejected_note="",
                publish_origin=host[:200]):
        raise PlanError(409, "wrong_status", "The post changed. Reload and try again.")
    return get_item(account_id, item_id)


def _post_files(account_id: str, row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The attached images, after checking that every file the post shows or links to still exists."""
    images = json.loads(row["images"] or "[]")
    tokens = media.tokens_in(row["body"])
    if not images and not tokens:
        return []
    if not media.configured():
        raise PlanError(409, "media_not_configured", "The post has files, but the media library is not set up.")
    linked = media.by_tokens(account_id, tokens)
    if len(linked) != len(tokens):
        raise PlanError(409, "missing_media", "The text links to a file that is not in the media library.")
    out, files = [], list(linked.values())
    for image in images:
        try:
            f = media.get(account_id, image["media_id"])
        except media.MediaError:
            raise PlanError(409, "missing_media", "An attached image is no longer in the media library.")
        out.append(dict(image, token=f["token"]))
        files.append(f)
    try:
        if not all(media.present_in_storage(f) for f in files):
            raise PlanError(409, "missing_media", "A file of this post is missing from storage.")
    except media.MediaError as e:
        raise PlanError(409, e.code, e.message)
    return out


def _public_origin(row: Dict[str, Any]) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or row["publish_origin"]
    return base or (f"https://{host}" if host else "")


def _with_images(account_id: str, row: Dict[str, Any]) -> str:
    """The approved text, with the cover on top and any attached image the text does not place at the end."""
    body, top, end = row["body"], [], []
    images = _post_files(account_id, row)
    origin = _public_origin(row)
    for image in images:
        if media.PUBLIC_PATH + image["token"] in body:
            continue
        if not origin:
            raise PlanError(409, "no_public_address", "Set PUBLIC_BASE_URL so images get a full address.")
        alt = image["alt"].replace("[", "(").replace("]", ")").replace("\n", " ")
        (top if image["cover"] else end).append(f"![{alt}]({origin}{media.PUBLIC_PATH}{image['token']})")
    return "\n\n".join(top + [body] + end)


def _guard(account_id: str, row: Dict[str, Any]) -> Optional[str]:
    """Banned claims always; the price rule only once the account has entered knowledge."""
    knowledge = assistant.get_knowledge(account_id)
    text = f"{row['title']}\n{row['body']}"
    if assistant.knowledge_text(knowledge):
        return assistant.guard(knowledge, text)
    low = text.lower()
    return "banned claim" if any(c.lower() in low for c in knowledge["banned_claims"]) else None


# ------------------------------------------------------------------ AI draft

def draft(account_id: str, item_id: int, then_status: str = "draft") -> Dict[str, Any]:
    from engine.ai_generator import AIGenerator, GenerationError
    row = _row(account_id, item_id)
    if row["status"] in ("approved", "published"):
        raise PlanError(409, "wrong_status", "Edit the post before drafting it again.")
    knowledge = assistant.get_knowledge(account_id)
    project = db.get_project(row["project_id"]) if row["project_id"] else None
    project = project or {}
    context = {
        "topic": f"{row['title']}. {row['topic']}".strip(), "keywords": row["keyword"],
        "tone": knowledge["tone"] or project.get("tone") or "clear and helpful",
        "target_audience": project.get("target_audience") or "prospective customers",
        "banned_claims": knowledge["banned_claims"],
        "business_knowledge": assistant.knowledge_text(knowledge)
        or "(No business facts have been entered. Give general information and state no facts about the business.)",
    }
    provider, key = llm.resolve(account_id)
    try:
        article = AIGenerator(provider=provider, api_key=key).generate_article(
            {"title": row["title"], "primary_keyword": row["keyword"], "keywords": [row["keyword"]], "angle": row["topic"],
             "target_audience": context["target_audience"], "tone": context["tone"]}, context)
    except GenerationError as e:
        raise PlanError(502, "ai_failed", f"No draft was written: {e}.")
    body = article["content_markdown"]
    blocked = _guard(account_id, dict(row, body=body))
    _set(account_id, item_id, expected_status=row["status"], body=body,
         status="draft" if blocked else then_status, error=f"Check before submitting: {blocked}." if blocked else "")
    return get_item(account_id, item_id)


# ------------------------------------------------------------------ the tick

def schedule_due() -> None:
    """Queue publishing of approved posts whose time has come."""
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT b.id, b.account_id, b.updated_at FROM blog_plan b JOIN accounts a ON a.id = b.account_id "
            "WHERE b.status = 'approved' AND b.publish_at != '' AND b.publish_at <= ? AND a.status = 'active'",
            (_now(),)).fetchall()]
    for r in rows:
        jobs.enqueue(r["account_id"], "plan_publish", {"item_id": r["id"], "version": r["updated_at"]},
                     dedupe_key=f"plan:{r['id']}:{r['updated_at']}")


def schedule_drafts() -> None:
    """Today's planned posts that nobody has written get an AI draft, which then waits for approval."""
    now = datetime.now(IST)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT b.id, b.account_id FROM blog_plan b JOIN accounts a ON a.id = b.account_id "
            "WHERE b.status = 'draft' AND b.body = '' AND b.publish_at != '' AND b.publish_at <= ? AND a.status = 'active'",
            (end_of_day.isoformat(),)).fetchall()]
    for r in rows:
        jobs.enqueue(r["account_id"], "plan_draft", {"item_id": r["id"]},
                     dedupe_key=f"plandraft:{r['id']}:{now.strftime('%Y-%m-%d')}")


def _failed(account_id: str, item_id: int, reason: str, mark: bool = True) -> None:
    if mark:
        _set(account_id, item_id, status="failed", error=reason[:300])
    alerts.raise_alert(account_id, "blog_failed", f"A planned post was not published: {reason}",
                       link=f"blog:{item_id}", severity="error")


@jobs.handler("plan_draft")
def _draft_job(job: Dict[str, Any]) -> None:
    account_id, item_id = job["account_id"], job["payload"]["item_id"]
    try:
        row = _row(account_id, item_id)
        if row["status"] != "draft" or row["body"]:
            return
        item = draft(account_id, item_id, then_status="needs_approval")
    except PlanError as e:
        if e.status != 404:
            _failed(account_id, item_id, e.message, mark=False)
        return
    if item["error"]:
        _failed(account_id, item_id, item["error"], mark=False)


@jobs.handler("plan_publish")
def _publish_job(job: Dict[str, Any]) -> None:
    account_id, item_id = job["account_id"], job["payload"]["item_id"]
    try:
        row = _row(account_id, item_id)
    except PlanError:
        return
    # Only the exact version that was approved, and only when its time has come.
    if row["status"] != "approved" or row["updated_at"] != job["payload"]["version"] or row["publish_at"] > _now():
        return
    blocked = _guard(account_id, row)
    if blocked:
        return _failed(account_id, item_id, blocked)
    result = publish(account_id, row)
    if not result.get("success"):
        return _failed(account_id, item_id, str(result.get("error", "publishing error")))
    _set(account_id, item_id, status="published", error="", post_url=result["url"], post_id=result["post_id"])


def publish(account_id: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Commit the approved text, unchanged, through the account's blog project."""
    from engine.formatters import slugify, format_frontmatter, build_target_filepath, assemble_post_document
    from engine.github_client import GitHubClient
    from engine.image_generator import generate_hero_svg
    project = db.get_project(row["project_id"]) if row["project_id"] else None
    if not project or project.get("account_id") != account_id:
        return {"success": False, "error": "The blog project no longer exists."}
    token = project.get("github_token") or cs.get_account_github_token(account_id)
    if not token:
        return {"success": False, "error": "No GitHub token is set for this project or account."}
    try:
        full = _with_images(account_id, row)
    except PlanError as e:
        return {"success": False, "error": e.message}
    title, body = row["title"], row["body"]
    slug = slugify(title)
    day = datetime.now(IST).strftime("%Y-%m-%d")
    excerpt = " ".join(line for line in body.splitlines() if line and not line.startswith("#"))[:155]
    tags = [row["keyword"]] if row["keyword"] else []
    path = build_target_filepath(project, slug, day)
    front = format_frontmatter(project["frontmatter_template"], {
        "title": title, "excerpt": excerpt, "date": day, "date_iso": _now(), "slug": slug, "tags": tags,
        "author": project.get("author_name", "Editorial Team"), "reading_time": max(1, len(body.split()) // 200)})
    post_id = db.create_post({
        "project_id": project["id"], "title": title, "slug": slug, "excerpt": excerpt, "content_markdown": full,
        "frontmatter_yaml": front, "target_path": path, "tags": tags, "meta_seo": {}, "image_prompt": "",
        "og_image_svg": generate_hero_svg(title=title, category=project.get("name", "Blog"),
                                          author=project.get("author_name", "Editorial Team"), reading_time=5),
        "seo_score": 100, "seo_issues": [], "status": "publishing"})
    res = GitHubClient(token=token).publish_post(
        repo=project["github_repo"], branch=project["github_branch"], target_path=path,
        file_content=assemble_post_document(front, full), post_title=title, post_excerpt=excerpt, post_tags=tags,
        mode=project.get("publishing_mode", "pr"))
    if not res.get("success"):
        db.update_post_status(post_id=post_id, status="failed", error=res.get("error", ""))
        return {"success": False, "error": res.get("error", "publishing error")}
    db.update_post_status(post_id=post_id, status="published", commit_sha=res.get("commit_sha"), pr_url=res.get("pr_url"),
                          pr_number=res.get("pr_number"))
    media.publish_linked(account_id, full)
    url = res.get("pr_url") or f"https://github.com/{project['github_repo']}/blob/{project['github_branch']}/{path}"
    try:
        from engine.whatsapp_client import WhatsAppClient
        WhatsAppClient(account_id).trigger_blog_publish_alert(title, url)
    except Exception:  # noqa: BLE001  the post is live; a failed announcement must not mark it failed
        alerts.raise_alert(account_id, "send_failed", "The blog announcement could not be queued.", link="blog")
    return {"success": True, "url": url, "post_id": post_id}


jobs.ON_FAIL["plan_publish"] = lambda job, error: _failed(job["account_id"], job["payload"]["item_id"], error)
jobs.ON_FAIL["plan_draft"] = lambda job, error: _failed(job["account_id"], job["payload"]["item_id"], error, mark=False)

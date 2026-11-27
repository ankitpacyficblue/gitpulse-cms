"""The dashboard and the one posts list, across every account the user may see (docs/UI-REDESIGN.md)."""
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List

import crm_store as cs
import database as db
from engine import access, alerts, blog_plan, media, site_publish
from engine.formatters import slugify

TABS = {"all": "", "draft": "draft", "in_review": "needs_approval", "scheduled": "approved",
        "published": "published", "failed": "failed"}
SORTS = {"publish_at": "publish_at", "published_at": "published_at", "updated_at": "updated_at", "title": "LOWER(title)"}


def _bad(name: str) -> blog_plan.PlanError:
    return blog_plan.PlanError(400, "invalid_parameter", f"'{name}' has a value that is not allowed.")


def accounts_for(user: Dict[str, Any], account: str = "all", need: str = "") -> List[Dict[str, Any]]:
    """The accounts asked for in which the user has `need`, each with their access (`who`). Naming an account
    that is foreign, or where they lack it, is refused."""
    mine = (cs.list_all_accounts(user["id"]) if user.get("is_platform_admin") else cs.list_accounts_for_user(user["id"]))
    if account not in ("", "all"):
        mine = [a for a in mine if a["id"] == account]
        if not mine:
            raise blog_plan.PlanError(403, "forbidden", "You cannot see that account.")
    out = [dict(a, who=access.of(a["id"], user)) for a in mine]
    out = [a for a in out if a["who"] and (not need or access.allows(a["who"], need))]
    if account not in ("", "all") and not out:
        raise blog_plan.PlanError(403, "forbidden", "You do not have access to this section.")
    return out


def _where(accounts: List[Dict[str, Any]]):
    ids = [a["id"] for a in accounts] or [""]
    return [f"account_id IN ({','.join('?' * len(ids))})"], list(ids)


def _rows(where: List[str], args: List[Any], order: str, limit: int, offset: int = 0) -> List[Dict[str, Any]]:
    with db.get_connection() as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM blog_plan WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ? OFFSET ?",
            (*args, limit, offset)).fetchall()]


def _order(column: str, direction: str) -> str:
    key = column.replace("LOWER(", "").rstrip(")")
    return f"CASE WHEN {key} = '' THEN 1 ELSE 0 END, {column} {direction}, id {direction}"


def _count(where: List[str], args: List[Any]) -> int:
    with db.get_connection() as conn:
        return conn.execute(f"SELECT COUNT(*) AS n FROM blog_plan WHERE {' AND '.join(where)}", args).fetchone()["n"]


def _z(value: str):
    return value + "Z" if value else None


def _posts_rows(ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not ids:
        return {}
    with db.get_connection() as conn:
        return {r["id"]: dict(r) for r in conn.execute(
            f"SELECT id, slug, meta_seo, content_markdown FROM posts WHERE id IN ({','.join('?' * len(ids))})",
            ids).fetchall()}


def _cover(view: Dict[str, Any], post: Dict[str, Any]):
    for image in view["images"]:
        if image.get("cover"):
            return {"url": image["url"] or image["public_url"], "alt": image["alt"]}
    if not post:      # older posts have no attached images, only a recorded or embedded cover
        return None
    found = json.loads(post["meta_seo"] or "{}").get("cover")
    if found:
        return found
    match = blog_plan.FIRST_IMAGE.search(post["content_markdown"] or "")
    return {"url": match.group(2), "alt": match.group(1)} if match else None


def _can(who: Dict[str, Any], state: str, missing: List[str]) -> Dict[str, bool]:
    write, publish = access.allows(who, "posts:manage"), access.allows(who, "posts:full")
    live = state == "published"
    return {"edit": publish if live else write,
            "approve": publish and state == "in_review" and not missing,
            "publish_now": publish and state in ("in_review", "scheduled", "failed") and set(missing) <= {"publish_date"},
            "reject": publish and state == "in_review",
            "submit": write and state in ("draft", "rejected", "failed"),
            "delete": write and not live,
            "unpublish": publish and live}


def _present(accounts: List[Dict[str, Any]], rows: List[Dict[str, Any]], host: str, full: bool = False) -> List[Dict[str, Any]]:
    """Rows -> PostSummary (or Post), in the order given."""
    by_account = {a["id"]: a for a in accounts}
    views: Dict[int, Dict[str, Any]] = {}
    projects: Dict[str, Dict[int, str]] = {}
    for account_id in {r["account_id"] for r in rows}:
        views.update({v["id"]: v for v in blog_plan._views(account_id,
                                                          [r for r in rows if r["account_id"] == account_id], host)})
        projects[account_id] = {p["id"]: p["name"] for p in db.list_projects(account_id)}
    posts = _posts_rows([r["post_id"] for r in rows if r["post_id"]])
    out = []
    for row in rows:
        v, account, post = views[row["id"]], by_account[row["account_id"]], posts.get(row["post_id"])
        names = projects[row["account_id"]]
        state = v["state"]
        slug = post["slug"] if post else slugify(row["title"])
        missing = [] if state == "published" else [name for name, absent in (
            ("body", not row["body"]), ("cover", not blog_plan.has_cover(row["images"])),
            ("website", row["project_id"] not in names), ("publish_date", not row["publish_at"])) if absent]
        item = {"id": row["id"], "account_id": row["account_id"], "account_name": account["name"],
                "project_id": row["project_id"], "project_name": names.get(row["project_id"]),
                "title": row["title"], "state": state, "publish_at": v["publish_at"], "published_at": v["published_at"],
                "updated_at": _z(row["updated_at"]),
                "url": (row["post_url"] or site_publish.post_url(row["account_id"], slug)) if state == "published" else "",
                "error": row["error"], "rejected_note": v["rejected_note"], "writer_id": row["writer_token_id"],
                "writer": v["writer"], "assignee_id": row["assignee_id"], "assignee_name": v["assignee_name"],
                "cover": _cover(v, post), "missing": missing, "can": _can(account["who"], state, missing)}
        if full:
            item.update({k: v[k] for k in ("topic", "keyword", "body", "seo_title", "meta_description",
                                           "rejected_by_name", "rejected_at", "images")}, slug=slug)
        out.append(item)
    return out


def _number(params: Dict[str, str], name: str, default: int, top: int = 10 ** 9) -> int:
    raw = params.get(name, "")
    if raw == "":
        return default
    if not (raw.isascii() and raw.isdigit() and 1 <= int(raw) <= top):
        raise _bad(name)
    return int(raw)


def listing(accounts: List[Dict[str, Any]], params: Dict[str, str], host: str = "") -> Dict[str, Any]:
    where, args = _where(accounts)
    for name, column in (("project_id", "project_id"), ("writer_id", "writer_token_id"), ("assignee_id", "assignee_id")):
        value = _number(params, name, 0)
        if value:
            where.append(f"{column} = ?")
            args.append(value)
    when = "CASE WHEN status = 'published' THEN published_at ELSE publish_at END"
    for name, op in (("from", ">="), ("to", "<")):
        if params.get(name):
            try:
                value = blog_plan._parse_time(params[name])
            except blog_plan.PlanError:
                raise _bad(name)
            where.append(f"{when} {op} ? AND {when} != ''")
            args.append(value)
    text = params.get("q", "").strip().lower()[:200]
    if text:
        like = "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        where.append("(LOWER(title) LIKE ? ESCAPE '!' OR LOWER(topic) LIKE ? ESCAPE '!' OR LOWER(keyword) LIKE ? ESCAPE '!')")
        args += [like] * 3
    tab = params.get("tab") or "all"
    if tab not in TABS:
        raise _bad("tab")
    sort = params.get("sort") or ("published_at" if tab == "published" else "publish_at")
    if sort not in SORTS:
        raise _bad("sort")
    direction = params.get("dir") or ("desc" if sort in ("published_at", "updated_at") else "asc")
    if direction not in ("asc", "desc"):
        raise _bad("dir")
    page, size = _number(params, "page", 1), _number(params, "page_size", 25, 100)

    with db.get_connection() as conn:
        by_status = {r["status"]: r["n"] for r in conn.execute(
            f"SELECT status, COUNT(*) AS n FROM blog_plan WHERE {' AND '.join(where)} GROUP BY status", args).fetchall()}
    counts = {name: by_status.get(status, 0) for name, status in TABS.items() if status}
    counts["all"] = sum(by_status.values())
    if TABS[tab]:
        where.append("status = ?")
        args.append(TABS[tab])
    rows = _rows(where, args, _order(SORTS[sort], direction), size, (page - 1) * size)
    return {"items": _present(accounts, rows, host), "total": counts[tab], "page": page, "page_size": size,
            "sort": sort, "dir": direction, "counts": counts}


def detail(accounts: List[Dict[str, Any]], item_id: int, host: str = "") -> Dict[str, Any]:
    where, args = _where(accounts)
    rows = _rows(where + ["id = ?"], args + [item_id], "id", 1)
    if not rows:
        raise blog_plan.PlanError(404, "not_found", "Post not found.")
    return _present(accounts, rows, host, full=True)[0]


def dashboard(accounts: List[Dict[str, Any]], host: str = "") -> Dict[str, Any]:
    where, args = _where(accounts)
    now = datetime.utcnow()
    week, month = (now + timedelta(days=7)).isoformat(), (now - timedelta(days=30)).isoformat()

    def count(extra: str, *more) -> int:
        return _count(where + [extra], args + list(more))

    def pick(status: str, column: str, direction: str, limit: int) -> List[Dict[str, Any]]:
        return _present(accounts, _rows(where + ["status = ?"], args + [status], _order(column, direction), limit), host)

    found: List[Dict[str, Any]] = []
    for account in accounts:
        for alert in alerts.list_alerts(account["id"]):
            if not access.sees_alert(account["who"], alert):
                continue
            system = alert["id"] is None
            if system and any(a["type"] == alert["type"] for a in found):
                continue
            found.append(dict({k: alert[k] for k in ("id", "type", "severity", "message", "link", "count")},
                              account_id="" if system else account["id"],
                              account_name="" if system else account["name"],
                              last_seen=_z(alert["last_seen"] or "")))
    return {"counts": {"in_review": count("status = 'needs_approval'"),
                       "scheduled_7d": count("status = 'approved' AND publish_at <= ?", week),
                       "published_30d": count("status = 'published' AND published_at >= ?", month),
                       "failed": count("status = 'failed'")},
            "approval_queue": pick("needs_approval", "publish_at", "asc", 20),
            "upcoming": pick("approved", "publish_at", "asc", 20),
            "recent": pick("published", "published_at", "desc", 10),
            "alerts": found}


def options(accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, List[Dict[str, Any]]] = {"accounts": [], "projects": [], "writers": [], "members": []}
    for a in accounts:
        out["accounts"].append({"id": a["id"], "name": a["name"],
                                "website_url": (cs.get_account(a["id"]) or {}).get("website_url", ""),
                                "can_write": access.allows(a["who"], "posts:manage"),
                                "can_publish": access.allows(a["who"], "posts:full")})
        out["projects"] += [{"id": p["id"], "name": p["name"], "account_id": a["id"]} for p in db.list_projects(a["id"])]
        with db.get_connection() as conn:
            out["writers"] += [{"id": w["id"], "name": w["name"], "account_id": a["id"]} for w in conn.execute(
                "SELECT id, name FROM writer_tokens WHERE account_id = ? AND revoked_at = '' ORDER BY name",
                (a["id"],)).fetchall()]
        out["members"] += [{"id": m["user_id"], "name": m["username"], "account_id": a["id"]}
                           for m in cs.list_members(a["id"])]
    return out

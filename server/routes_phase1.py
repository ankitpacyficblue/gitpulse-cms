"""Phase 1 API: assistant knowledge, chat hand-off, templates, consent, alerts, entry links, worker tick.

Imported at the end of routes_api, which owns the route table and the access checks."""
import hmac
import os
import re
import secrets
import urllib.parse

import crm_store as cs
import database as db
import dbcompat
from engine import alerts, assistant, blog_plan, contact_fields, jobs, media, messaging, writer_tokens
from engine.whatsapp_client import WhatsAppClient
from engine.permissions import has_permission
from server.routes_api import route


# ------------------------------------------------------------------ worker

@route("GET", r"/api/internal/tick", "public")      # Vercel Cron calls with GET and a Bearer token
@route("POST", r"/api/internal/tick", "public")
def internal_tick(ctx, m, q, body):
    """Runs due jobs. Needs the CRON_SECRET environment value in X-Cron-Secret (or as a Bearer token)."""
    expected = os.environ.get("CRON_SECRET", "")
    given = ctx.headers.get("x-cron-secret") or ctx.headers.get("authorization", "").removeprefix("Bearer ")
    if not expected or not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        return 401, {"error": "unauthorized"}
    return 200, {"success": True, "jobs": jobs.tick()}


# ------------------------------------------------------------------ assistant

@route("GET", r"/api/ai/knowledge", "acct:crm.read")
def knowledge_get(ctx, m, q, body):
    return 200, {"knowledge": assistant.get_knowledge(ctx.account_id)}


@route("PUT", r"/api/ai/knowledge", "acct:ai.manage")
def knowledge_put(ctx, m, q, body):
    try:
        data = assistant.save_knowledge(ctx.account_id, body)
    except ValueError as e:
        return 400, {"error": "invalid_input", "message": str(e)}
    db.log_event("AI assistant knowledge updated.", "INFO", account_id=ctx.account_id)
    return 200, {"success": True, "knowledge": data}


@route("POST", r"/api/ai/test", "acct:ai.manage")
def knowledge_test(ctx, m, q, body):
    question = str(body.get("question") or "").strip()[:1000]
    if not question:
        return 400, {"error": "question is required."}
    out = assistant.answer(ctx.account_id, [("customer", question)])
    return 200, {"reply": out["reply"], "handoff": out["handoff"], "reason": out["reason"], "sent": False}


@route("POST", r"/api/whatsapp/conversations/(?P<id>\d+)/ai", "acct:crm.write")
def conversation_ai(ctx, m, q, body):
    mode = body.get("mode")
    if mode not in ("on", "off"):
        return 400, {"error": "invalid_mode", "allowed": ["on", "off"]}
    ok = assistant.set_mode(ctx.account_id, int(m.group("id")), mode)
    return (200, {"success": True, "mode": mode}) if ok else (404, {"error": "Conversation not found."})


# ------------------------------------------------------------------ templates

@route("GET", r"/api/whatsapp/templates", "acct:crm.read")
def templates_list(ctx, m, q, body):
    with db.get_connection() as conn:
        rows = conn.execute("SELECT name, language, category, status, body, variables, header_format, synced_at FROM wa_templates "
                            "WHERE account_id = ? ORDER BY name, language", (ctx.account_id,)).fetchall()
    return 200, {"templates": [dict(r) for r in rows]}


@route("POST", r"/api/whatsapp/templates/sync", "acct:automations.manage")
def templates_sync(ctx, m, q, body):
    res = WhatsAppClient(ctx.account_id).sync_templates()
    return (200 if res.get("ok") else 400), res


@route("POST", r"/api/whatsapp/conversations/(?P<id>\d+)/template", "acct:crm.write")
def conversation_template(ctx, m, q, body):
    conv = cs.get_conversation(ctx.account_id, int(m.group("id")))
    if not conv:
        return 404, {"error": "Conversation not found."}
    params = body.get("params") or []
    if not isinstance(params, list) or not body.get("name"):
        return 400, {"error": "name, language and a params list are required."}
    try:
        res = messaging.send(ctx.account_id, cs.get_contact(ctx.account_id, conv["contact_id"]), sent_by="staff",
                             template_name=str(body["name"]), template_language=str(body.get("language") or ""),
                             params=[str(p) for p in params], media_id=body.get("media_id"))
    except messaging.Blocked as b:
        return 409, {"success": False, "error": b.code, "message": b.message}
    assistant.staff_replied(ctx.account_id, conv["id"])
    return (200 if res.get("success") else 502), res


# ------------------------------------------------------------------ consent

@route("PUT", r"/api/whatsapp/contacts/(?P<id>\d+)/consent", "acct:automations.manage")
def contact_consent(ctx, m, q, body):
    status, source = str(body.get("status") or ""), str(body.get("source") or "").strip()
    if status not in ("unknown", "opted_in", "opted_out"):
        return 400, {"error": "invalid_consent", "allowed": ["unknown", "opted_in", "opted_out"]}
    if status == "opted_in" and not source:
        return 400, {"error": "source_required", "message": "Say how the contact agreed, for example 'website form'."}
    cid = int(m.group("id"))
    if not messaging.set_consent(ctx.account_id, cid, status, source or "staff", str(body.get("wording") or "")):
        return 404, {"error": "Contact not found."}
    db.log_event(f"Consent of contact #{cid} set to {status} by {ctx.user['username']}.", "INFO", account_id=ctx.account_id)
    return 200, {"success": True, "contact": cs.get_contact(ctx.account_id, cid)}


# ------------------------------------------------------------------ alerts

@route("GET", r"/api/alerts", "acct:crm.read")
def alerts_list(ctx, m, q, body):
    rows = alerts.list_alerts(ctx.account_id, include_resolved=q.get("all") in ("1", "true"))
    return 200, {"alerts": rows, "open": sum(1 for r in rows if not r["resolved_at"] and r["severity"] != "info")}


@route("POST", r"/api/alerts/(?P<id>\d+)/resolve", "acct:crm.write")
def alerts_resolve(ctx, m, q, body):
    ok = alerts.resolve(ctx.account_id, int(m.group("id")))
    return (200, {"success": True}) if ok else (404, {"error": "Alert not found."})


@route("GET", r"/api/admin/alert-counts", "platform")
def alerts_counts(ctx, m, q, body):
    return 200, {"counts": alerts.open_counts()}


# ------------------------------------------------------------------ entry links

def _wa_link(account_id: str, prefill: str) -> str:
    phone = re.sub(r"\D", "", cs.get_whatsapp_public(account_id).get("phone_number", "") or "")
    return f"https://wa.me/{phone}?text={urllib.parse.quote(prefill)}" if phone else ""


LINK_SOURCES = ("website", "ad", "social", "other")


@route("GET", r"/api/entry-links", "acct:crm.read")
def entry_links_list(ctx, m, q, body):
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT id, label, code, prefill, source, campaign FROM entry_links "
                                              "WHERE account_id = ? ORDER BY id", (ctx.account_id,)).fetchall()]
        by_code = {r["entry_code"]: r["n"] for r in conn.execute(
            "SELECT entry_code, COUNT(*) AS n FROM contacts WHERE account_id = ? AND entry_code != '' GROUP BY entry_code",
            (ctx.account_id,)).fetchall()}
        by_source = {r["source"]: r["n"] for r in conn.execute(
            "SELECT source, COUNT(*) AS n FROM contacts WHERE account_id = ? AND source != '' GROUP BY source",
            (ctx.account_id,)).fetchall()}
    for r in rows:
        r["url"] = _wa_link(ctx.account_id, r["prefill"])
        r["enquiries"] = by_code.get(r["code"], 0)
    return 200, {"links": rows, "enquiries_by_source": by_source, "has_number": bool(_wa_link(ctx.account_id, "x"))}


@route("POST", r"/api/entry-links", "acct:automations.manage")
def entry_links_create(ctx, m, q, body):
    label = str(body.get("label") or "").strip()[:100]
    code = str(body.get("code") or "").strip().upper() or secrets.token_hex(3).upper()
    source = str(body.get("source") or "website")
    if not label or not re.fullmatch(r"[A-Z0-9_-]{1,40}", code) or source not in LINK_SOURCES:
        return 400, {"error": "invalid_input", "message": "A label is required; source is website, ad, social or other; "
                                                          "the code is up to 40 letters, digits, - or _."}
    if not _wa_link(ctx.account_id, "x"):
        return 409, {"error": "no_number", "message": "Save this account's WhatsApp number first (WhatsApp setup)."}
    prefill = f"{str(body.get('message') or 'Hi, I would like to know more.').strip()[:300]} (ref: {code})"
    try:
        with db.get_connection() as conn:
            link_id = conn.execute("INSERT INTO entry_links (account_id, label, code, prefill, source, campaign, created_at) "
                                   "VALUES (?,?,?,?,?,?,?)", (ctx.account_id, label, code, prefill, source,
                                   str(body.get("campaign") or "").strip()[:100], cs._now())).lastrowid
            conn.commit()
    except Exception as e:
        if dbcompat.is_unique_violation(e):
            return 409, {"error": "duplicate_code"}
        raise
    return 201, {"success": True, "id": link_id, "code": code, "prefill": prefill, "url": _wa_link(ctx.account_id, prefill)}


@route("DELETE", r"/api/entry-links/(?P<id>\d+)", "acct:automations.manage")
def entry_links_delete(ctx, m, q, body):
    with db.get_connection() as conn:
        ok = conn.execute("DELETE FROM entry_links WHERE id = ? AND account_id = ?",
                          (int(m.group("id")), ctx.account_id)).rowcount > 0
        conn.commit()
    return (200, {"success": True}) if ok else (404, {"error": "Entry link not found."})


# ------------------------------------------------------------------ custom contact fields

def _field_error(e):
    return e.status, {"error": e.code, "message": e.message}


@route("GET", r"/api/contact-fields", "acct:crm.read")
def fields_list(ctx, m, q, body):
    return 200, {"fields": contact_fields.list_fields(ctx.account_id)}


@route("POST", r"/api/contact-fields", "acct:automations.manage")
def fields_create(ctx, m, q, body):
    try:
        return 201, {"success": True, "field": contact_fields.create(ctx.account_id, body)}
    except contact_fields.FieldError as e:
        return _field_error(e)


@route("PATCH", r"/api/contact-fields/(?P<id>\d+)", "acct:automations.manage")
def fields_update(ctx, m, q, body):
    try:
        return 200, {"success": True, "field": contact_fields.update(ctx.account_id, int(m.group("id")), body)}
    except contact_fields.FieldError as e:
        return _field_error(e)


@route("DELETE", r"/api/contact-fields/(?P<id>\d+)", "acct:automations.manage")
def fields_delete(ctx, m, q, body):
    try:
        contact_fields.archive(ctx.account_id, int(m.group("id")))
    except contact_fields.FieldError as e:
        return _field_error(e)
    return 200, {"success": True}


# ------------------------------------------------------------------ blog plan

def _plan(fn, status: int = 200):
    try:
        return status, {"success": True, "item": fn()}
    except blog_plan.PlanError as e:
        return e.status, {"success": False, "error": e.code, "message": e.message}


@route("GET", r"/api/blog/plan", "acct:content.read")
def plan_list(ctx, m, q, body):
    assignee = q.get("assignee_id", "")
    return 200, {"items": blog_plan.list_items(ctx.account_id, status=q.get("status", ""),
                                               assignee_id=int(assignee) if assignee.isdigit() else None,
                                               host=ctx.host), "tick_hours": jobs.TICK_HOURS}


@route("POST", r"/api/blog/plan", "acct:content.write")
def plan_create(ctx, m, q, body):
    if body.get("writer_token_id") and not has_permission(ctx.role, "content.publish"):
        return 403, {"error": "forbidden", "required": "content.publish"}
    return _plan(lambda: blog_plan.create(ctx.account_id, body), 201)


@route("PATCH", r"/api/blog/plan/(?P<id>\d+)", "acct:content.write")
def plan_update(ctx, m, q, body):
    if "writer_token_id" in body and not has_permission(ctx.role, "content.publish"):
        return 403, {"error": "forbidden", "required": "content.publish"}
    return _plan(lambda: blog_plan.update(ctx.account_id, int(m.group("id")), body))


@route("DELETE", r"/api/blog/plan/(?P<id>\d+)", "acct:content.write")
def plan_delete(ctx, m, q, body):
    try:
        blog_plan.delete(ctx.account_id, int(m.group("id")))
    except blog_plan.PlanError as e:
        return e.status, {"success": False, "error": e.code, "message": e.message}
    return 200, {"success": True}


@route("POST", r"/api/blog/plan/(?P<id>\d+)/draft", "acct:content.write")
def plan_draft(ctx, m, q, body):
    return _plan(lambda: blog_plan.draft(ctx.account_id, int(m.group("id"))))


@route("POST", r"/api/blog/plan/(?P<id>\d+)/submit", "acct:content.write")
def plan_submit(ctx, m, q, body):
    return _plan(lambda: blog_plan.submit(ctx.account_id, int(m.group("id"))))


@route("POST", r"/api/blog/plan/(?P<id>\d+)/reject", "acct:content.publish")
def plan_reject(ctx, m, q, body):
    res = _plan(lambda: blog_plan.reject(ctx.account_id, int(m.group("id")), body.get("note"), ctx.user["id"]))
    if res[0] == 200:
        db.log_event(f"Planned post #{m.group('id')} rejected by {ctx.user['username']}: {res[1]['item']['rejected_note']}",
                     "INFO", account_id=ctx.account_id)
    return res


@route("POST", r"/api/blog/plan/(?P<id>\d+)/approve", "acct:content.publish")
def plan_approve(ctx, m, q, body):
    res = _plan(lambda: blog_plan.approve(ctx.account_id, int(m.group("id")), ctx.host))
    if res[0] == 200:
        db.log_event(f"Planned post #{m.group('id')} approved by {ctx.user['username']}.", "INFO", account_id=ctx.account_id)
    return res


# ------------------------------------------------------------------ media library

def _media(action, code=200):
    try:
        return code, action()
    except media.MediaError as e:
        return e.status, {"error": e.code, "message": e.message}


@route("GET", r"/api/media", "acct:crm.read")
def media_list(ctx, m, q, body):
    if not media.configured():
        return 200, {"configured": False, "items": []}
    return _media(lambda: {"configured": True, "items": media.list_items(ctx.account_id, q.get("q", ""), ctx.host)})


@route("POST", r"/api/media/upload-url", "acct:content.write")
def media_upload_url(ctx, m, q, body):
    return _media(lambda: media.create_upload(ctx.account_id, ctx.user["id"], body), 201)


@route("POST", r"/api/media", "acct:content.write")
def media_confirm(ctx, m, q, body):
    return _media(lambda: {"item": media.confirm(ctx.account_id, body.get("media_id"), ctx.host)}, 201)


@route("DELETE", r"/api/media/(?P<id>\d+)", "acct:content.publish")
def media_delete(ctx, m, q, body):
    return _media(lambda: media.delete(ctx.account_id, m.group("id"), force=q.get("force") == "1") or {"success": True})


# ------------------------------------------------------------------ AI writer tokens

def _writer(action, code=200):
    try:
        return code, action()
    except (blog_plan.PlanError, media.MediaError) as e:
        return e.status, {"error": e.code, "message": e.message}


@route("GET", r"/api/writer-tokens", "acct:users.manage")
def writer_token_list(ctx, m, q, body):
    return 200, {"tokens": writer_tokens.list_tokens(ctx.account_id)}


@route("POST", r"/api/writer-tokens", "acct:users.manage")
def writer_token_create(ctx, m, q, body):
    res = _writer(lambda: writer_tokens.create(ctx.account_id, body.get("name"), ctx.user["id"], body.get("project_id")),
                  201)
    if res[0] == 201:
        db.log_event(f"Writer token '{res[1]['item']['name']}' created by {ctx.user['username']}.", "INFO", account_id=ctx.account_id)
    return res


@route("DELETE", r"/api/writer-tokens/(?P<id>\d+)", "acct:users.manage")
def writer_token_revoke(ctx, m, q, body):
    res = _writer(lambda: writer_tokens.revoke(ctx.account_id, int(m.group("id"))) or {"success": True})
    if res[0] == 200:
        db.log_event(f"Writer token #{m.group('id')} revoked by {ctx.user['username']}.", "INFO", account_id=ctx.account_id)
    return res


@route("POST", r"/api/writer/media/upload-url", "writer")
def writer_upload_url(ctx, m, q, body):
    return _writer(lambda: writer_tokens.upload_url(ctx.writer, body), 201)


@route("POST", r"/api/writer/media", "writer")
def writer_media_confirm(ctx, m, q, body):
    return _writer(lambda: writer_tokens.confirm(ctx.writer, body.get("media_id"), ctx.host), 201)


@route("GET", r"/api/writer/posts", "writer")
def writer_posts(ctx, m, q, body):
    return 200, {"items": writer_tokens.posts(ctx.writer)}


@route("GET", r"/api/writer/posts/(?P<id>\d+)", "writer")
def writer_post(ctx, m, q, body):
    return _writer(lambda: {"item": writer_tokens.post(ctx.writer, int(m.group("id")))})


@route("POST", r"/api/writer/posts", "writer")
def writer_create(ctx, m, q, body):
    res = _writer(lambda: dict(zip(("item", "created"), writer_tokens.create_draft(ctx.writer, body))))
    return (201 if res[0] == 200 and res[1]["created"] else res[0]), res[1]


@route("PATCH", r"/api/writer/posts/(?P<id>\d+)", "writer")
def writer_revise(ctx, m, q, body):
    return _writer(lambda: {"item": writer_tokens.revise(ctx.writer, int(m.group("id")), body)})


@route("POST", r"/api/writer/posts/(?P<id>\d+)/submit", "writer")
def writer_submit(ctx, m, q, body):
    return _writer(lambda: {"item": writer_tokens.submit(ctx.writer, int(m.group("id")))})

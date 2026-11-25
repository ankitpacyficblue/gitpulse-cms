"""Phase 1 API: assistant knowledge, chat hand-off, templates, consent, alerts, entry links, worker tick.

Imported at the end of routes_api, which owns the route table and the access checks."""
import hmac
import os
import re
import secrets
import urllib.parse

import crm_store as cs
import database as db
from engine import alerts, assistant, jobs, messaging
from engine.whatsapp_client import WhatsAppClient
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
        rows = conn.execute("SELECT name, language, category, status, body, variables, synced_at FROM wa_templates "
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
                             params=[str(p) for p in params])
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


@route("GET", r"/api/entry-links", "acct:crm.read")
def entry_links_list(ctx, m, q, body):
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT id, label, code, prefill FROM entry_links WHERE account_id = ? "
                                              "ORDER BY id", (ctx.account_id,)).fetchall()]
        counts = {r["source"]: r["n"] for r in conn.execute(
            "SELECT source, COUNT(*) AS n FROM contacts WHERE account_id = ? AND source != '' GROUP BY source",
            (ctx.account_id,)).fetchall()}
    for r in rows:
        r["url"] = _wa_link(ctx.account_id, r["prefill"])
    return 200, {"links": rows, "enquiries_by_source": counts}


@route("POST", r"/api/entry-links", "acct:automations.manage")
def entry_links_create(ctx, m, q, body):
    label = str(body.get("label") or "").strip()[:100]
    code = str(body.get("code") or "").strip().upper() or secrets.token_hex(3).upper()
    if not label or not re.fullmatch(r"[A-Z0-9_-]{1,40}", code) or code in ("AD", "DIRECT"):
        return 400, {"error": "invalid_input", "message": "A label is required; the code is up to 40 letters, digits, - or _."}
    prefill = f"{str(body.get('message') or 'Hi, I would like to know more.').strip()[:300]} (ref: {code})"
    try:
        with db.get_connection() as conn:
            cur = conn.execute("INSERT INTO entry_links (account_id, label, code, prefill, created_at) VALUES (?,?,?,?,?)",
                               (ctx.account_id, label, code, prefill, cs._now()))
            link_id = cur.lastrowid
            conn.commit()
    except Exception as e:
        import dbcompat
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

"""The CRM dashboard (docs/CRM-DASHBOARD-PERMISSIONS.md). Read-only. A block the person may not view in an
account leaves that account out; with no account left the block is None. Currencies are never added together."""
from datetime import datetime, timedelta
from typing import Any, Dict, List

import crm_store as cs
import database as db
from engine import access, alerts
from engine.messaging import IST

STAGES = ("lead", "qualified", "proposal", "negotiation", "won", "lost")
OPEN = STAGES[:4]


def _z(value: str):
    return value + "Z" if value else None


def _ids(accounts: List[Dict[str, Any]], section: str) -> List[str]:
    return [a["id"] for a in accounts if access.allows(a["who"], section + ":view")]


def _query(ids: List[str], sql: str, *args) -> List[Dict[str, Any]]:
    """`sql` has one {ids} where the account list goes, before any other placeholder."""
    with db.get_connection() as conn:
        return [dict(r) for r in conn.execute(sql.format(ids=",".join("?" * len(ids))), (*ids, *args)).fetchall()]


def _count(ids: List[str], sql: str, *args) -> int:
    return _query(ids, sql, *args)[0]["n"]


def _money(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    values: Dict[str, float] = {}
    for r in rows:
        values[r["currency"]] = values.get(r["currency"], 0) + (r["total"] or 0)
    return {"count": sum(r["n"] for r in rows),
            "values": [{"currency": c, "value": v} for c, v in sorted(values.items())]}


def _automations(ids: List[str], week: str) -> Dict[str, Any]:
    totals = _query(ids, "SELECT COUNT(*) AS total, SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active "
                         "FROM automations WHERE account_id IN ({ids})")[0]
    runs = _query(ids, "SELECT COUNT(*) AS runs, SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS failures "
                       "FROM automation_runs WHERE account_id IN ({ids}) AND created_at >= ?", week)[0]
    first = _query(ids, "SELECT MIN(created_at) AS first FROM automation_runs WHERE account_id IN ({ids})")[0]["first"]
    return {"active": totals["active"] or 0, "total": totals["total"], "runs_7d": runs["runs"],
            "failures_7d": runs["failures"] or 0, "counted_since": _z(first or "")}


def _alerts(accounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def add(a, kind, severity, message, link, alert_id=None, count=1):
        out.append({"id": alert_id, "account_id": a["id"] if a else "", "account_name": a["name"] if a else "",
                    "type": kind, "severity": severity, "message": message, "link": link, "count": count})

    for a in accounts:
        if not access.allows(a["who"], "crm:view"):
            continue
        wa = cs.get_whatsapp_public(a["id"])
        if not (wa.get("configured") and wa.get("has_token") and wa.get("phone_number_id")):
            add(a, "wa_not_connected", "warning", "WhatsApp is not connected.", "wa-config")
        if access.allows(a["who"], "templates:view"):
            for t in _query([a["id"]], "SELECT name FROM wa_templates WHERE account_id IN ({ids}) AND status = 'REJECTED' "
                                       "ORDER BY name LIMIT 10"):
                add(a, "template_rejected", "error", f"Template '{t['name']}' was rejected.", "wa-templates")
        for alert in alerts.list_alerts(a["id"]):
            if alert["type"] == "blog_failed" or not access.sees_alert(a["who"], alert):
                continue
            system = alert["id"] is None
            if system and any(x["type"] == alert["type"] for x in out):
                continue
            add(None if system else a, alert["type"], alert["severity"], alert["message"], alert["link"],
                alert["id"], alert["count"])
    return out


def build(accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """`accounts`: [{id, name, who}] the person may see on this dashboard."""
    now = datetime.utcnow()
    week, month_ago = (now - timedelta(days=7)).isoformat(), (now - timedelta(days=30)).isoformat()
    month_start = ((now + timedelta(hours=5, minutes=30)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                   .replace(tzinfo=IST).utctimetuple())
    month = datetime(*month_start[:6]).isoformat()
    names = {a["id"]: a["name"] for a in accounts}
    inbox, contacts, pipeline = (_ids(accounts, s) for s in ("inbox", "contacts", "pipeline"))
    broadcasts, automations, templates, links = (_ids(accounts, s) for s in
                                                 ("broadcasts", "automations", "templates", "entry_links"))
    cards: Dict[str, Any] = {"unread_conversations": None, "new_contacts_7d": None, "new_contacts_30d": None,
                             "open_deals": None, "won_this_month": None}
    out: Dict[str, Any] = {"cards": cards, "pipeline": None, "needs_reply": None, "broadcasts": None,
                           "automations": None, "templates": None, "entry_links": None, "alerts": _alerts(accounts)}
    if inbox:
        cards["unread_conversations"] = _count(
            inbox, "SELECT COUNT(*) AS n FROM conversations WHERE account_id IN ({ids}) AND unread_count > 0")
        rows = _query(inbox, """
            SELECT v.id, v.account_id, v.unread_count, v.needs_human, v.last_message_preview, v.last_inbound_at,
                   v.last_message_at, c.name AS contact_name
            FROM conversations v JOIN contacts c ON c.id = v.contact_id AND c.account_id = v.account_id
            WHERE v.account_id IN ({ids}) AND (v.needs_human = 1 OR (
                SELECT m.direction FROM messages m WHERE m.conversation_id = v.id AND m.account_id = v.account_id
                ORDER BY m.id DESC LIMIT 1) = 'inbound')
            ORDER BY CASE WHEN v.last_inbound_at = '' THEN v.last_message_at ELSE v.last_inbound_at END, v.id
            LIMIT 20""")
        out["needs_reply"] = [{"conversation_id": r["id"], "account_id": r["account_id"],
                               "account_name": names[r["account_id"]], "contact_name": r["contact_name"],
                               "preview": r["last_message_preview"] or "",
                               "waiting_since": _z(r["last_inbound_at"] or r["last_message_at"] or ""),
                               "unread": r["unread_count"], "needs_human": bool(r["needs_human"])} for r in rows]
    if contacts:
        for key, since in (("new_contacts_7d", week), ("new_contacts_30d", month_ago)):
            cards[key] = _count(contacts, "SELECT COUNT(*) AS n FROM contacts WHERE account_id IN ({ids}) "
                                          "AND created_at >= ?", since)
    if pipeline:
        grouped = "SELECT stage, currency, COUNT(*) AS n, SUM(value) AS total FROM deals WHERE account_id IN ({ids})"
        rows = _query(pipeline, grouped + " GROUP BY stage, currency")
        out["pipeline"] = [dict(stage=s, **_money([r for r in rows if r["stage"] == s])) for s in STAGES]
        cards["open_deals"] = _money([r for r in rows if r["stage"] in OPEN])
        cards["won_this_month"] = _money(_query(
            pipeline, grouped + " AND stage = 'won' AND updated_at >= ? GROUP BY stage, currency", month))
    if broadcasts:
        rows = _query(broadcasts, "SELECT * FROM broadcasts WHERE account_id IN ({ids}) ORDER BY created_at DESC, id DESC LIMIT 5")
        out["broadcasts"] = []
        for b in rows:
            c = {r["status"]: r["n"] for r in _query(
                [b["account_id"]], "SELECT status, COUNT(*) AS n FROM messages WHERE account_id IN ({ids}) "
                                   "AND broadcast_id = ? GROUP BY status", b["id"])}
            read = c.get("read", 0) if c else b["read_count"]
            delivered = c.get("delivered", 0) + read if c else b["delivered_count"]
            sent = c.get("sent", 0) + c.get("mock", 0) + delivered if c else b["sent_count"]
            out["broadcasts"].append({
                "id": b["id"], "account_id": b["account_id"], "account_name": names[b["account_id"]], "name": b["name"],
                "status": ("queued" if c.get("queued") else "completed") if c else b["status"],
                "created_at": _z(b["created_at"]), "recipients": b["total_recipients"], "sent": sent,
                "delivered": delivered, "read": read, "failed": c.get("failed", 0)})
    if automations:
        out["automations"] = _automations(automations, week)
    if templates:
        found = {r["status"]: r["n"] for r in _query(
            templates, "SELECT status, COUNT(*) AS n FROM wa_templates WHERE account_id IN ({ids}) GROUP BY status")}
        out["templates"] = dict({"APPROVED": 0, "PENDING": 0, "REJECTED": 0}, **found)
    if links:
        with db.get_connection() as conn:      # the date comes before the account list, so not _query
            rows = [dict(r) for r in conn.execute(f"""
                SELECT l.id, l.account_id, l.label, l.code, COUNT(c.id) AS n FROM entry_links l
                LEFT JOIN contacts c ON c.account_id = l.account_id AND c.entry_code = l.code AND c.created_at >= ?
                WHERE l.account_id IN ({",".join("?" * len(links))})
                GROUP BY l.id, l.account_id, l.label, l.code ORDER BY n DESC, l.id LIMIT 10""",
                (month_ago, *links)).fetchall()]
        out["entry_links"] = [{"id": r["id"], "account_id": r["account_id"], "account_name": names[r["account_id"]],
                               "label": r["label"], "code": r["code"], "leads_30d": r["n"]} for r in rows]
    return out

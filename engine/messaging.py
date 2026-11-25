"""Every outbound WhatsApp message goes through here, so the rules hold everywhere:
no message to an opted-out contact, no free text 24 hours after the customer's last message,
marketing templates only to opted-in contacts, and a per-account daily cap on template recipients."""
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import crm_store as cs
import database as db
from engine import alerts, jobs, media
from engine.whatsapp_client import WhatsAppClient

WINDOW = timedelta(hours=24)
STOP_WORDS = ("stop", "unsubscribe")
IST = timezone(timedelta(hours=5, minutes=30))    # default account time zone (Asia/Kolkata)
DEFAULT_DAILY_CAP = 250


class Blocked(Exception):
    """A rule forbids this send. `code`: opted_out, window_closed, not_opted_in, template_not_approved."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def window_expires_at(conv: Dict[str, Any]) -> Optional[datetime]:
    last = conv.get("last_inbound_at") or ""
    if not last:
        with db.get_connection() as conn:      # conversations from before this column existed
            row = conn.execute("SELECT MAX(created_at) AS t FROM messages WHERE conversation_id = ? AND account_id = ? "
                               "AND direction = 'inbound'", (conv["id"], conv["account_id"])).fetchone()
        last = (row["t"] if row else "") or ""
    return datetime.fromisoformat(last) + WINDOW if last else None


def window_open(conv: Dict[str, Any]) -> bool:
    end = window_expires_at(conv)
    return bool(end and datetime.utcnow() < end)


def get_template(account_id: str, name: str, language: str) -> Optional[Dict[str, Any]]:
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM wa_templates WHERE account_id = ? AND name = ? AND language = ?",
                           (account_id, name, language)).fetchone()
        return dict(row) if row else None


def approved_template(account_id: str, name: str, language: str) -> Dict[str, Any]:
    tpl = get_template(account_id, name, language)
    if not tpl or tpl["status"].upper() != "APPROVED":
        raise Blocked("template_not_approved", "Choose an approved template. Sync templates if it is missing.")
    return tpl


def render(template_body: str, params: List[str]) -> str:
    return re.sub(r"\{\{(\d+)\}\}", lambda m: params[int(m.group(1)) - 1] if 0 < int(m.group(1)) <= len(params) else m.group(0),
                  template_body)


def check(contact: Dict[str, Any], conv: Dict[str, Any], template: Optional[Dict[str, Any]],
          allow_opted_out: bool = False) -> None:
    if contact.get("consent_status") == "opted_out" and not allow_opted_out:
        raise Blocked("opted_out", "This contact has opted out of messages.")
    if template is None:
        if not window_open(conv):
            raise Blocked("window_closed", "The 24-hour reply window is closed. Send an approved template instead.")
    elif template["category"].upper() == "MARKETING" and contact.get("consent_status") != "opted_in":
        raise Blocked("not_opted_in", "Marketing messages go only to contacts who opted in.")


def _next_day_ts() -> float:
    return (_day_start_utc() + timedelta(days=1)).replace(tzinfo=timezone.utc).timestamp()


def _day_start_utc() -> datetime:
    local = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _cap_reached(account_id: str, contact_id: int) -> bool:
    from engine import assistant
    cap = int(assistant.get_knowledge(account_id).get("daily_template_cap") or DEFAULT_DAILY_CAP)
    with db.get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT contact_id FROM messages WHERE account_id = ? AND message_type = 'template' "
                            "AND sent_at >= ?", (account_id, _day_start_utc().isoformat())).fetchall()
    ids = {r["contact_id"] for r in rows}
    return contact_id not in ids and len(ids) >= cap


def _set_message(account_id: str, message_id: int, status: str, wa_id: str = "", error: str = "") -> None:
    sets, args = ["status = ?", "error_message = ?"], [status, (error or "")[:300]]
    if wa_id:
        sets.append("wa_message_id = ?")
        args.append(wa_id)
    if status in ("sent", "mock"):
        sets.append("sent_at = ?")
        args.append(datetime.utcnow().isoformat())
    with db.get_connection() as conn:
        conn.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id = ? AND account_id = ?", (*args, message_id, account_id))
        conn.commit()


def _record(account_id: str, conv: Dict[str, Any], contact: Dict[str, Any], body: str, sent_by: str,
            template: Optional[Dict[str, Any]], broadcast_id: Optional[int], file: Optional[Dict[str, Any]] = None) -> int:
    kind = "template" if template else media.TYPES[file["mime"]][2] if file else "text"
    mid = cs.create_message(account_id, conv["id"], contact["id"], "outbound", body, message_type=kind, status="queued")
    with db.get_connection() as conn:
        conn.execute("UPDATE messages SET sent_by = ?, broadcast_id = ?, media_id = ? WHERE id = ? AND account_id = ?",
                     (sent_by, broadcast_id, file["id"] if file else None, mid, account_id))
        conn.commit()
    return mid


def _transmit(account_id: str, phone: str, body: str, template: Optional[Dict[str, Any]], params: List[str],
              media_id: Optional[int] = None) -> Dict[str, Any]:
    client = WhatsAppClient(account_id)
    file = None
    if media_id:
        try:
            file = media.send_link(account_id, media_id)      # a fresh link for every attempt
        except media.MediaError as e:
            return {"success": False, "status": "failed", "error": e.message, "retryable": e.status >= 500}
    if template:
        return client.send_template_message(phone, template["name"], template["language"], params, file)
    if file:
        return client.send_media_message(phone, file, "" if body == file["filename"] else body)
    return client.send_text_message(phone, body)


def _apply_result(account_id: str, message_id: int, res: Dict[str, Any]) -> str:
    if res.get("success"):
        status = "mock" if res.get("mock") else "sent"
        _set_message(account_id, message_id, status, wa_id=res.get("message_id", ""))
        return status
    if res.get("token_invalid"):
        alerts.raise_alert(account_id, "token_invalid", "WhatsApp rejected the access token. Save a new one.", severity="error")
    return "failed"


def _alert_send_failed(account_id: str, conv_id: int, error: str) -> None:
    alerts.raise_alert(account_id, "send_failed", f"A message could not be sent: {error}", link=f"conversation:{conv_id}",
                       severity="error")


def _queue(account_id: str, message_id: int, params: List[str], template: Optional[Dict[str, Any]],
           run_at: Optional[float] = None, attempts: int = 0, allow_opted_out: bool = False,
           media_id: Optional[int] = None) -> None:
    jobs.enqueue(account_id, "send", {"message_id": message_id, "params": params, "allow_opted_out": allow_opted_out,
                                      "media_id": media_id,
                                      "template": template["name"] if template else "",
                                      "language": template["language"] if template else ""},
                 run_at=run_at, attempts=attempts)


def media_for(account_id: str, template: Optional[Dict[str, Any]], media_id: Any) -> Optional[Dict[str, Any]]:
    """The file to send, checked against the template's header. Raises Blocked."""
    wanted = (template or {}).get("header_format", "") if template else ""
    if not media_id:
        if wanted in ("IMAGE", "VIDEO", "DOCUMENT"):
            raise Blocked("missing_media", f"This template needs a {wanted.lower()} file.")
        return None
    try:
        media.require()
        file = media.get(account_id, media_id)
    except media.MediaError as e:
        raise Blocked(e.code, e.message)
    kind = media.TYPES[file["mime"]][2]
    if not kind:
        raise Blocked("unsupported_on_whatsapp", "WhatsApp does not take WebP. Use JPEG or PNG.")
    if template and wanted != kind.upper():
        raise Blocked("wrong_media_type", f"This template takes {wanted.lower() or 'no'} file in its header.")
    return file


def _prepare(account_id: str, contact: Dict[str, Any], body: str, template_name: str, template_language: str,
             params: List[str], allow_opted_out: bool = False):
    conv = cs.get_or_create_conversation(account_id, contact["id"])
    template = approved_template(account_id, template_name, template_language) if template_name else None
    if template:
        if len(params) < template["variables"] or any(not str(p).strip() for p in params):
            raise Blocked("missing_variables", f"This template needs {template['variables']} values.")
        body = render(template["body"], params) or f"[template {template_name}]"
    check(contact, conv, template, allow_opted_out)
    return conv, template, body


def send(account_id: str, contact: Dict[str, Any], body: str = "", sent_by: str = "staff",
         template_name: str = "", template_language: str = "", params: Optional[List[str]] = None,
         allow_opted_out: bool = False, media_id: Any = None) -> Dict[str, Any]:
    """Send now; queue only if the failure is worth retrying. Raises Blocked, and then stores nothing."""
    params = params or []
    conv, template, body = _prepare(account_id, contact, body, template_name, template_language, params, allow_opted_out)
    file = media_for(account_id, template, media_id)
    file_id = file["id"] if file else None
    body = body or (file["name"] if file else "")
    capped = bool(template) and _cap_reached(account_id, contact["id"])
    mid = _record(account_id, conv, contact, body, sent_by, template, None, file)
    if capped:
        _queue(account_id, mid, params, template, run_at=_next_day_ts(), media_id=file_id)
        return {"success": True, "status": "queued", "message_id": mid, "reason": "daily_cap"}
    res = _transmit(account_id, contact["phone"], body, template, params, file_id)
    status = _apply_result(account_id, mid, res)
    if status != "failed":
        return {"success": True, "status": status, "message_id": mid, "mock": bool(res.get("mock"))}
    if res.get("retryable"):
        _set_message(account_id, mid, "queued", error=res.get("error", ""))
        _queue(account_id, mid, params, template, run_at=time.time() + jobs.RETRY_DELAYS[0], attempts=1,
               allow_opted_out=allow_opted_out, media_id=file_id)
        return {"success": True, "status": "queued", "message_id": mid, "error": res.get("error")}
    _set_message(account_id, mid, "failed", error=res.get("error", ""))
    _alert_send_failed(account_id, conv["id"], res.get("error", "unknown error"))
    return {"success": False, "status": "failed", "message_id": mid, "error": res.get("error")}


def queue_send(account_id: str, contact: Dict[str, Any], body: str = "", sent_by: str = "automation",
               template_name: str = "", template_language: str = "", params: Optional[List[str]] = None,
               broadcast_id: Optional[int] = None, media_id: Any = None) -> int:
    """Bulk and scheduled sends: one job per recipient. Raises Blocked."""
    params = params or []
    conv, template, body = _prepare(account_id, contact, body, template_name, template_language, params)
    file = media_for(account_id, template, media_id)
    mid = _record(account_id, conv, contact, body or (file["name"] if file else ""), sent_by, template, broadcast_id, file)
    _queue(account_id, mid, params, template, media_id=file["id"] if file else None)
    return mid


@jobs.handler("send")
def _send_job(job: Dict[str, Any]) -> None:
    account_id, p = job["account_id"], job["payload"]
    with db.get_connection() as conn:
        msg = conn.execute("SELECT * FROM messages WHERE id = ? AND account_id = ?", (p["message_id"], account_id)).fetchone()
    if not msg or msg["status"] != "queued":
        return
    contact = cs.get_contact(account_id, msg["contact_id"])
    conv = cs.get_conversation(account_id, msg["conversation_id"])
    try:
        template = approved_template(account_id, p["template"], p["language"]) if p.get("template") else None
        check(contact, conv, template, p.get("allow_opted_out", False))   # re-checked at send time
    except Blocked as b:
        _set_message(account_id, msg["id"], "failed", error=b.message)
        _alert_send_failed(account_id, conv["id"], b.message)
        return
    if template and _cap_reached(account_id, contact["id"]):
        raise jobs.Defer(_next_day_ts())
    res = _transmit(account_id, contact["phone"], msg["body"], template, p.get("params") or [], p.get("media_id"))
    if _apply_result(account_id, msg["id"], res) != "failed":
        return
    if res.get("retryable"):
        _set_message(account_id, msg["id"], "queued", error=res.get("error", ""))
        raise jobs.Retry(res.get("error", "send failed"))
    _set_message(account_id, msg["id"], "failed", error=res.get("error", ""))
    _alert_send_failed(account_id, conv["id"], res.get("error", "unknown error"))


def _send_gave_up(job: Dict[str, Any], error: str) -> None:
    account_id, mid = job["account_id"], job["payload"].get("message_id")
    with db.get_connection() as conn:
        msg = conn.execute("SELECT conversation_id FROM messages WHERE id = ? AND account_id = ?", (mid, account_id)).fetchone()
    _set_message(account_id, mid, "failed", error=error)
    _alert_send_failed(account_id, msg["conversation_id"] if msg else 0, error)


jobs.ON_FAIL["send"] = _send_gave_up


# ------------------------------------------------------------------ consent

def set_consent(account_id: str, contact_id: int, status: str, source: str, wording: str = "") -> bool:
    if status not in ("unknown", "opted_in", "opted_out"):
        raise ValueError("invalid_consent")
    with db.get_connection() as conn:
        cur = conn.execute("UPDATE contacts SET consent_status = ?, consent_source = ?, consent_at = ?, consent_wording = ? "
                           "WHERE id = ? AND account_id = ?",
                           (status, source[:100], datetime.utcnow().isoformat(), wording[:500], contact_id, account_id))
        conn.commit()
        ok = cur.rowcount > 0
    if ok and status == "opted_out":
        cancel_queued(account_id, contact_id)
    return ok


def cancel_queued(account_id: str, contact_id: int) -> int:
    """Fail every message still waiting for this contact; its job then does nothing."""
    with db.get_connection() as conn:
        cur = conn.execute("UPDATE messages SET status = 'failed', error_message = 'Cancelled: contact opted out' "
                           "WHERE account_id = ? AND contact_id = ? AND status = 'queued'", (account_id, contact_id))
        conn.commit()
        return cur.rowcount


def is_stop_message(account_id: str, text: str) -> bool:
    """Exact message, any case: "please don't stop" does not opt out."""
    from engine import assistant
    extra = [w.strip().lower() for w in assistant.get_knowledge(account_id).get("stop_words") or []]
    return text.strip().strip(".!").lower() in set(STOP_WORDS) | set(filter(None, extra))

"""
GitPulse CMS - WhatsApp Business Cloud API client and automation engine (per account).

A WhatsAppClient belongs to exactly one account: credentials are read from that
account's encrypted config, and every database read and write carries its
account_id. Access tokens are never logged, never put in return values and never
included in error text. Message bodies are not logged.

Mock mode (simulated sends) is only enabled by the WHATSAPP_MOCK=1 environment
variable for dev and tests. It is never a silent fallback for a missing config.
"""

import json
import os
import re
import uuid
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import crm_store as cs
import database as db


def mock_enabled() -> bool:
    return os.environ.get("WHATSAPP_MOCK") == "1"


class WhatsAppClient:
    META_API_VERSION = "v21.0"
    BASE_URL = "https://graph.facebook.com"

    def __init__(self, account_id: str):
        if not account_id:
            raise ValueError("account_id is required")
        self.account_id = account_id
        self._creds: Optional[Dict[str, str]] = None

    def _credentials(self) -> Dict[str, str]:
        if self._creds is None:
            self._creds = cs.get_whatsapp_credentials(self.account_id)
        return self._creds

    def is_configured(self) -> bool:
        c = self._credentials()
        return bool(c["phone_number_id"] and c["access_token"])

    # ------------------------------------------------------------------ send

    def send_text_message(self, to_phone: str, body: str) -> Dict[str, Any]:
        clean_phone = re.sub(r"[^\d+]", "", to_phone)
        if mock_enabled():
            return {"success": True, "message_id": f"wamid.mock_{uuid.uuid4().hex[:16]}", "status": "sent",
                    "mock": True, "recipient": clean_phone}
        if not self.is_configured():
            return {"success": False, "status": "failed", "error": "WhatsApp is not configured for this account."}

        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": clean_phone,
                   "type": "text", "text": {"preview_url": True, "body": body}}
        return self._post_message(payload)

    def send_template_message(self, to_phone: str, name: str, language: str, params: List[str]) -> Dict[str, Any]:
        clean_phone = re.sub(r"[^\d+]", "", to_phone)
        if mock_enabled():
            return {"success": True, "message_id": f"wamid.mock_{uuid.uuid4().hex[:16]}", "status": "sent",
                    "mock": True, "recipient": clean_phone}
        if not self.is_configured():
            return {"success": False, "status": "failed", "error": "WhatsApp is not configured for this account."}
        template: Dict[str, Any] = {"name": name, "language": {"code": language}}
        if params:
            template["components"] = [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in params]}]
        return self._post_message({"messaging_product": "whatsapp", "to": clean_phone, "type": "template",
                                   "template": template})

    def _post_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """`retryable`: the message certainly did not go out and trying later makes sense."""
        creds = self._credentials()
        url = f"{self.BASE_URL}/{self.META_API_VERSION}/{creds['phone_number_id']}/messages"
        headers = {"Authorization": f"Bearer {creds['access_token']}", "Content-Type": "application/json"}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            msg_id = data.get("messages", [{}])[0].get("id", f"wamid.{uuid.uuid4().hex[:16]}")
            return {"success": True, "message_id": msg_id, "status": "sent"}
        except urllib.error.HTTPError as e:
            error = {}
            try:
                error = json.loads(e.read().decode("utf-8")).get("error", {}) or {}
            except Exception:
                pass
            return {"success": False, "status": "failed",
                    "error": f"Meta WhatsApp API HTTP {e.code}: {str(error.get('message', ''))[:200]}".strip(),
                    "retryable": e.code == 429 or e.code >= 500, "token_invalid": e.code == 401 or error.get("code") == 190}
        except urllib.error.URLError as e:
            return {"success": False, "status": "failed", "error": "Could not reach Meta.", "retryable": True}
        except Exception as e:
            # For example a timeout while waiting for the answer: it may have gone out, so never repeat it.
            return {"success": False, "status": "failed", "error": f"Delivery unknown ({type(e).__name__})."}

    def sync_templates(self) -> Dict[str, Any]:
        """Copy the account's templates from Meta (they are created in WhatsApp Manager)."""
        if mock_enabled():
            items = [{"name": f"mock_{s.lower()}", "language": "en", "status": s, "category": c,
                      "components": [{"type": "BODY", "text": "Hello {{1}}, this is a mock template."}]}
                     for s, c in (("APPROVED", "UTILITY"), ("PENDING", "MARKETING"), ("REJECTED", "MARKETING"))]
        else:
            cfg = cs.get_whatsapp_public(self.account_id)
            if not self.is_configured() or not cfg.get("waba_id"):
                return {"ok": False, "message": "Save the access token and the WhatsApp Business Account id first."}
            url = (f"{self.BASE_URL}/{self.META_API_VERSION}/{urllib.parse.quote(str(cfg['waba_id']), safe='')}"
                   "/message_templates?limit=200&fields=name,language,status,category,components")
            try:
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._credentials()['access_token']}"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    items = json.loads(resp.read().decode("utf-8")).get("data", [])
            except urllib.error.HTTPError as e:
                return {"ok": False, "message": f"Meta refused the template list (HTTP {e.code})."}
            except Exception as e:
                return {"ok": False, "message": f"Could not reach Meta ({type(e).__name__})."}
        now = cs._now()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wa_templates WHERE account_id = ?", (self.account_id,))
            for t in items:
                body = next((c.get("text", "") for c in t.get("components", []) if str(c.get("type", "")).upper() == "BODY"), "")
                variables = len(set(re.findall(r"\{\{(\d+)\}\}", body)))
                conn.execute("INSERT INTO wa_templates (account_id, name, language, category, status, body, variables, synced_at) "
                             "VALUES (?,?,?,?,?,?,?,?)", (self.account_id, t.get("name", ""), t.get("language", ""),
                             str(t.get("category", "MARKETING")).upper(), str(t.get("status", "PENDING")).upper(), body,
                             variables, now))
            conn.commit()
        return {"ok": True, "count": len(items), "mock": mock_enabled()}

    def test_connection(self) -> Dict[str, Any]:
        """Check the saved credentials without sending a message: a read-only lookup of the phone number
        at Meta. In mock mode nothing leaves this server. The result is stored for the setup wizard."""
        if mock_enabled():
            res = {"ok": True, "message": "Mock mode: no request was made to Meta.", "mock": True}
        elif not self.is_configured():
            res = {"ok": False, "message": "Save the phone number id and access token first."}
        else:
            creds = self._credentials()
            url = (f"{self.BASE_URL}/{self.META_API_VERSION}/{creds['phone_number_id']}"
                   "?fields=display_phone_number,verified_name")
            try:
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {creds['access_token']}"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                res = {"ok": True, "message": "Connected to " + str(data.get("verified_name") or data.get("display_phone_number") or "WhatsApp")}
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = (json.loads(e.read().decode("utf-8")).get("error", {}) or {}).get("message", "")[:200]
                except Exception:
                    pass
                res = {"ok": False, "message": f"Meta rejected the credentials (HTTP {e.code}): {detail}".strip()}
            except Exception as e:
                res = {"ok": False, "message": f"Could not reach Meta ({type(e).__name__})."}
        if self.is_configured() or mock_enabled():
            cs.save_whatsapp_test(self.account_id, res["ok"], res["message"])
        return res

    # ------------------------------------------------------------- broadcasts

    @staticmethod
    def _fill(params: List[str], values: Dict[str, str]) -> List[str]:
        out = []
        for param in params:
            for key, value in values.items():
                param = str(param).replace("{{" + key + "}}", value)
            out.append(param)
        return out

    def audience(self, target_tag: str) -> List[Dict[str, Any]]:
        contacts = cs.list_contacts(self.account_id)
        if target_tag == "all":
            return contacts
        return [c for c in contacts if target_tag.lower() in [t.lower() for t in c.get("tags", [])]]

    def preview_broadcast(self, template: Dict[str, Any], target_tag: str) -> Dict[str, Any]:
        """What a send would do now, by the same rules. Nothing is stored or sent."""
        from engine import messaging
        contacts, skipped = self.audience(target_tag), {}
        for contact in contacts:
            try:
                messaging.check(contact, {}, template)
            except messaging.Blocked as b:
                skipped[b.code] = skipped.get(b.code, 0) + 1
        n_skipped = sum(skipped.values())
        return {"audience": len(contacts), "will_send": len(contacts) - n_skipped, "skipped_count": n_skipped,
                "skipped": skipped}

    def execute_broadcast(self, broadcast_id: int) -> Dict[str, Any]:
        """Queue an approved template, one job per recipient. A broadcast runs once."""
        from engine import messaging
        broadcast = cs.get_broadcast(self.account_id, broadcast_id)
        if not broadcast:
            return {"success": False, "error": "Broadcast campaign not found"}
        if not mock_enabled() and not self.is_configured():
            return {"success": False, "error": "WhatsApp is not configured for this account."}
        try:
            messaging.approved_template(self.account_id, broadcast["template_name"], broadcast["template_language"])
        except messaging.Blocked as b:
            return {"success": False, "error": b.message, "code": b.code}
        with db.get_connection() as conn:
            claimed = conn.execute("UPDATE broadcasts SET status = 'queued' WHERE id = ? AND account_id = ? AND status = 'draft'",
                                   (broadcast_id, self.account_id)).rowcount
            conn.commit()
        if not claimed:
            return {"success": False, "error": "This broadcast has already been run.", "code": "already_run"}

        target_tag = broadcast.get("target_tag", "all")
        contacts = self.audience(target_tag)

        queued, skipped = 0, {}
        params = json.loads(broadcast.get("template_params") or "[]")
        for contact in contacts:
            values = {"name": contact.get("name", "there"), "phone": contact.get("phone", "")}
            try:
                messaging.queue_send(self.account_id, contact, sent_by="broadcast", broadcast_id=broadcast_id,
                                     template_name=broadcast["template_name"],
                                     template_language=broadcast["template_language"], params=self._fill(params, values))
                queued += 1
            except messaging.Blocked as b:
                skipped[b.code] = skipped.get(b.code, 0) + 1
        n_skipped = sum(skipped.values())
        with db.get_connection() as conn:
            conn.execute("UPDATE broadcasts SET total_recipients = ?, skipped_count = ? WHERE id = ? AND account_id = ?",
                         (len(contacts), n_skipped, broadcast_id, self.account_id))
            conn.commit()
        return {"success": True, "total_recipients": len(contacts), "queued_count": queued, "skipped_count": n_skipped,
                "skipped": skipped, "mock": mock_enabled()}

    # ------------------------------------------------------- inbound webhooks

    @staticmethod
    def process_incoming_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route each change to the account that owns its phone_number_id and process it there.
        Changes for unknown numbers are skipped. The account is never taken from the payload body
        beyond that lookup key, and never from a request parameter."""
        messages_n = statuses_n = skipped = 0
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                val = change.get("value", {})
                pn_id = (val.get("metadata") or {}).get("phone_number_id", "")
                account_id = cs.find_account_by_phone_number_id(pn_id)
                if not account_id:
                    skipped += 1
                    continue
                cs.touch_whatsapp_webhook(account_id)
                client = WhatsAppClient(account_id)
                m, s = client._process_change(val)
                messages_n += m
                statuses_n += s
        return {"success": True, "processed_messages": messages_n, "processed_statuses": statuses_n,
                "skipped_unknown_number": skipped}

    def _process_change(self, val: Dict[str, Any]):
        from engine import alerts
        processed_messages = processed_statuses = 0
        for st in val.get("statuses", []):
            wa_id, status_name = st.get("id"), st.get("status")
            if wa_id and status_name and cs.update_message_status(self.account_id, wa_id, status_name):
                processed_statuses += 1
                if status_name == "failed":
                    reason = str(((st.get("errors") or [{}])[0]).get("title", "delivery failed"))[:150]
                    alerts.raise_alert(self.account_id, "send_failed", f"WhatsApp did not deliver a message: {reason}",
                                       link="messages", severity="error")

        names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in val.get("contacts", [])}
        for msg in val.get("messages", []):
            if self._process_message(msg, names):
                processed_messages += 1
        return processed_messages, processed_statuses

    def _seen(self, wa_message_id: str) -> bool:
        if not wa_message_id:
            return False
        with db.get_connection() as conn:
            return conn.execute("SELECT 1 FROM messages WHERE account_id = ? AND wa_message_id = ? AND direction = 'inbound'",
                                (self.account_id, wa_message_id)).fetchone() is not None

    def _entry_source(self, msg: Dict[str, Any], body: str):
        """(source, detail): a click-to-WhatsApp ad, a known entry link code, or direct."""
        ref = msg.get("referral") or {}
        if ref:
            return "ad", json.dumps({k: str(ref.get(k, ""))[:300] for k in ("source_id", "headline", "source_url")})
        m = re.search(r"\(ref:\s*([A-Za-z0-9_-]{1,40})\)", body or "")
        if m:
            with db.get_connection() as conn:
                row = conn.execute("SELECT code, label FROM entry_links WHERE account_id = ? AND code = ?",
                                   (self.account_id, m.group(1).upper())).fetchone()
            if row:
                return row["code"], row["label"]
        return "direct", ""

    def _process_message(self, msg: Dict[str, Any], names: Dict[str, str]) -> bool:
        from engine import assistant, jobs, messaging
        sender, wa_id = msg.get("from", ""), msg.get("id", "")
        msg_type = msg.get("type", "text")
        if not sender or msg_type == "reaction" or self._seen(wa_id):
            return False        # Meta redelivers: the same message must not be answered twice
        body = (msg.get("text") or {}).get("body", "") if msg_type == "text" else f"[{msg_type.capitalize()} message received]"

        source, detail = self._entry_source(msg, body)
        contact = cs.get_contact_by_phone(self.account_id, sender)
        is_new = False
        if not contact:
            try:
                cid = cs.create_contact(self.account_id, names.get(sender) or f"Lead {sender[-4:]}",
                                        "+" + sender.lstrip("+"), tags=["Lead"],
                                        notes="Automatically discovered via inbound WhatsApp message")
            except ValueError:
                return False
            with db.get_connection() as conn:
                conn.execute("UPDATE contacts SET source = ?, source_detail = ? WHERE id = ? AND account_id = ?",
                             (source, detail, cid, self.account_id))
                conn.commit()
            contact, is_new = cs.get_contact(self.account_id, cid), True
        elif source != "direct":
            db.log_event(f"Contact #{contact['id']} came back through '{source}'.", "INFO", account_id=self.account_id)
        conv = cs.get_or_create_conversation(self.account_id, contact["id"])
        cs.create_message(self.account_id, conv["id"], contact["id"], "inbound", body, message_type=msg_type,
                          wa_message_id=wa_id, status="delivered")

        if msg_type == "text" and messaging.is_stop_message(self.account_id, body):
            if contact["consent_status"] != "opted_out":
                messaging.set_consent(self.account_id, contact["id"], "opted_out", "whatsapp message", body[:100])
                try:
                    messaging.send(self.account_id, cs.get_contact(self.account_id, contact["id"]),
                                   "You have been unsubscribed. We will not send you further messages.",
                                   sent_by="automation", allow_opted_out=True)
                except messaging.Blocked:
                    pass
            return True
        if contact["consent_status"] == "opted_out":
            return True
        if not self._evaluate_automations(contact, body, is_new):
            job_id = assistant.on_inbound(self.account_id, conv["id"], wa_id or f"{sender}:{cs._now()}", msg_type)
            if job_id:
                jobs.run_job(job_id)        # first try now; the tick picks up whatever is left
        return True

    # ------------------------------------------------------------ automations

    def _evaluate_automations(self, contact: Dict[str, Any], message_body: str, is_new_contact: bool) -> bool:
        """True when a keyword rule answered, so the AI does not answer the same message too."""
        from engine import messaging
        lower_body = message_body.lower()
        answered = False
        for auto in cs.list_automations(self.account_id):
            if not auto.get("is_active"):
                continue
            trigger = auto.get("trigger_type")
            triggered = False
            if trigger == "welcome" and is_new_contact:
                triggered = True
            elif trigger == "keyword":
                kws = [k.strip().lower() for k in (auto.get("trigger_keyword") or "").split(",") if k.strip()]
                triggered = any(k in lower_body for k in kws)
            if not triggered:
                continue
            text = auto.get("message_template", "").replace("{{name}}", contact.get("name", "there"))
            text = text.replace("{{phone}}", contact.get("phone", ""))
            try:
                messaging.send(self.account_id, contact, text, sent_by="automation")
            except messaging.Blocked:
                continue
            answered = answered or trigger == "keyword"
            cs.increment_automation_execution(self.account_id, auto["id"])
            db.log_event(f"Triggered WhatsApp automation '{auto['name']}'", "INFO", account_id=self.account_id)
        return answered

    def trigger_blog_publish_alert(self, post_title: str, post_url: str) -> int:
        """Queue the approved template of each active blog_publish rule for contacts tagged vip,
        customer or all. Opt-out and marketing consent apply."""
        from engine import messaging
        rules = [a for a in cs.list_automations(self.account_id)
                 if a.get("is_active") and a.get("trigger_type") == "blog_publish" and a.get("template_name")]
        if not rules:
            return 0
        targets = [c for c in cs.list_contacts(self.account_id)
                   if any(t.lower() in ("vip", "customer", "all") for t in c.get("tags", []))]
        queued = 0
        for rule in rules:
            for c in targets:
                values = {"title": post_title, "url": post_url, "name": c.get("name", "there"), "phone": c.get("phone", "")}
                try:
                    messaging.queue_send(self.account_id, c, template_name=rule["template_name"],
                                         template_language=rule["template_language"],
                                         params=self._fill(json.loads(rule.get("template_params") or "[]"), values))
                    queued += 1
                except messaging.Blocked:
                    continue
            cs.increment_automation_execution(self.account_id, rule["id"])
            db.log_event(f"Blog publish alert queued for {queued} contacts via rule '{rule['name']}'.", "INFO",
                         account_id=self.account_id)
        return queued

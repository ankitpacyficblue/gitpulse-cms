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

        creds = self._credentials()
        url = f"{self.BASE_URL}/{self.META_API_VERSION}/{creds['phone_number_id']}/messages"
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": clean_phone,
                   "type": "text", "text": {"preview_url": True, "body": body}}
        headers = {"Authorization": f"Bearer {creds['access_token']}", "Content-Type": "application/json"}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            msg_id = data.get("messages", [{}])[0].get("id", f"wamid.{uuid.uuid4().hex[:16]}")
            return {"success": True, "message_id": msg_id, "status": "sent"}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = (json.loads(e.read().decode("utf-8")).get("error", {}) or {}).get("message", "")[:200]
            except Exception:
                pass
            return {"success": False, "status": "failed", "error": f"Meta WhatsApp API HTTP {e.code}: {detail}".strip()}
        except Exception as e:
            return {"success": False, "status": "failed", "error": f"WhatsApp dispatch failed ({type(e).__name__})."}

    def _record_outbound(self, contact: Dict[str, Any], text: str, res: Dict[str, Any]) -> Optional[int]:
        conv = cs.get_or_create_conversation(self.account_id, contact["id"])
        if not conv:
            return None
        if res.get("success"):
            status = "mock" if res.get("mock") else "sent"
        else:
            status = "failed"
        return cs.create_message(self.account_id, conv["id"], contact["id"], "outbound", text,
                                 wa_message_id=res.get("message_id", ""), status=status,
                                 error_message=res.get("error", ""))

    # ------------------------------------------------------------- broadcasts

    def execute_broadcast(self, broadcast_id: int) -> Dict[str, Any]:
        broadcast = cs.get_broadcast(self.account_id, broadcast_id)
        if not broadcast:
            return {"success": False, "error": "Broadcast campaign not found"}
        if not mock_enabled() and not self.is_configured():
            return {"success": False, "error": "WhatsApp is not configured for this account."}

        target_tag = broadcast.get("target_tag", "all")
        contacts = cs.list_contacts(self.account_id)
        if target_tag != "all":
            contacts = [c for c in contacts if target_tag.lower() in [t.lower() for t in c.get("tags", [])]]

        sent = delivered = read = 0
        for contact in contacts:
            text = broadcast["template_body"].replace("{{name}}", contact.get("name", "there"))
            text = text.replace("{{phone}}", contact.get("phone", ""))
            res = self.send_text_message(contact["phone"], text)
            self._record_outbound(contact, text, res)
            if res.get("success"):
                sent += 1   # delivered/read stay 0: nothing in mock mode, and real receipts come from Meta callbacks
        cs.update_broadcast_stats(self.account_id, broadcast_id, total=len(contacts), sent=sent,
                                  delivered=delivered, read=read, status="completed")
        return {"success": True, "total_recipients": len(contacts), "sent_count": sent,
                "delivered_count": delivered, "read_count": read, "mock": mock_enabled()}

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
                client = WhatsAppClient(account_id)
                m, s = client._process_change(val)
                messages_n += m
                statuses_n += s
        return {"success": True, "processed_messages": messages_n, "processed_statuses": statuses_n,
                "skipped_unknown_number": skipped}

    def _process_change(self, val: Dict[str, Any]):
        processed_messages = processed_statuses = 0
        for st in val.get("statuses", []):
            wa_id, status_name = st.get("id"), st.get("status")
            if wa_id and status_name and cs.update_message_status(self.account_id, wa_id, status_name):
                processed_statuses += 1

        names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in val.get("contacts", [])}
        for msg in val.get("messages", []):
            sender = msg.get("from", "")
            if not sender:
                continue
            msg_type = msg.get("type", "text")
            body = (msg.get("text") or {}).get("body", "") if msg_type == "text" else f"[{msg_type.capitalize()} message received]"

            contact = cs.get_contact_by_phone(self.account_id, sender)
            is_new = False
            if not contact:
                try:
                    cid = cs.create_contact(self.account_id, names.get(sender) or f"Lead {sender[-4:]}",
                                            "+" + sender.lstrip("+"), tags=["Lead"],
                                            notes="Automatically discovered via inbound WhatsApp message")
                except ValueError:
                    continue
                contact, is_new = cs.get_contact(self.account_id, cid), True
            conv = cs.get_or_create_conversation(self.account_id, contact["id"])
            cs.create_message(self.account_id, conv["id"], contact["id"], "inbound", body, message_type=msg_type,
                              wa_message_id=msg.get("id", ""), status="delivered")
            processed_messages += 1
            self._evaluate_automations(contact, body, is_new)
        return processed_messages, processed_statuses

    # ------------------------------------------------------------ automations

    def _evaluate_automations(self, contact: Dict[str, Any], message_body: str, is_new_contact: bool) -> None:
        lower_body = message_body.lower()
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
            res = self.send_text_message(contact["phone"], text)
            self._record_outbound(contact, text, res)
            cs.increment_automation_execution(self.account_id, auto["id"])
            db.log_event(f"Triggered WhatsApp automation '{auto['name']}'", "INFO", account_id=self.account_id)

    def trigger_blog_publish_alert(self, post_title: str, post_url: str) -> int:
        """Send a 'new article' message through active blog_publish rules to contacts tagged
        vip, customer or all. Contacts without those tags are never messaged."""
        rules = [a for a in cs.list_automations(self.account_id)
                 if a.get("is_active") and a.get("trigger_type") == "blog_publish"]
        if not rules:
            return 0
        targets = [c for c in cs.list_contacts(self.account_id)
                   if any(t.lower() in ("vip", "customer", "all") for t in c.get("tags", []))]
        dispatched = 0
        for rule in rules:
            template = rule.get("message_template") or "New article: '{{title}}'\n\nRead it live: {{url}}"
            for c in targets:
                msg = template.replace("{{title}}", post_title).replace("{{url}}", post_url)
                msg = msg.replace("{{name}}", c.get("name", "there"))
                res = self.send_text_message(c["phone"], msg)
                self._record_outbound(c, msg, res)
                if res.get("success"):
                    dispatched += 1
            cs.increment_automation_execution(self.account_id, rule["id"])
            db.log_event(f"Blog publish alert sent to {dispatched} contacts via rule '{rule['name']}'.", "INFO",
                         account_id=self.account_id)
        return dispatched

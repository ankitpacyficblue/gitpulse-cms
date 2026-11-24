"""
GitPulse CMS - WhatsApp Business Cloud API & Automation Client
Built on the official Meta WhatsApp Cloud API (v21.0) architecture.
Zero third-party pip dependencies; uses standard library urllib and json.
"""

import os
import json
import uuid
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.error

import database as db

class WhatsAppClient:
    """Official Meta WhatsApp Business Cloud API Client & Auto-Responder Engine."""

    META_API_VERSION = "v21.0"
    BASE_URL = "https://graph.facebook.com"

    def __init__(self, phone_number_id: Optional[str] = None, access_token: Optional[str] = None):
        cfg = db.get_whatsapp_config()
        self.phone_number_id = phone_number_id or cfg.get("phone_number_id") or ""
        self.access_token = access_token or cfg.get("access_token") or ""

    def is_mock_mode(self) -> bool:
        """Determines if the client should run in mock simulation mode."""
        return not self.access_token or self.access_token.startswith("mock") or self.access_token == "test"

    def send_text_message(self, to_phone: str, body: str,
                          phone_number_id: Optional[str] = None,
                          access_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Dispatches an individual outbound text message via Meta Graph API.
        Simulates delivery in mock mode if live Meta credentials are not configured.
        """
        p_id = phone_number_id or self.phone_number_id
        token = access_token or self.access_token
        clean_phone = re.sub(r"[^\d+]", "", to_phone)

        if not p_id or not token or self.is_mock_mode():
            sim_id = f"wamid.mock_{uuid.uuid4().hex[:16]}"
            return {
                "success": True,
                "message_id": sim_id,
                "status": "sent",
                "mock": True,
                "recipient": clean_phone,
                "body": body
            }

        url = f"{self.BASE_URL}/{self.META_API_VERSION}/{p_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "text",
            "text": {
                "preview_url": True,
                "body": body
            }
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                msg_id = resp_data.get("messages", [{}])[0].get("id", f"wamid.{uuid.uuid4().hex[:16]}")
                return {
                    "success": True,
                    "message_id": msg_id,
                    "status": "sent",
                    "raw": resp_data
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            return {
                "success": False,
                "error": f"Meta WhatsApp API HTTP {e.code}: {err_msg}",
                "status": "failed"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"WhatsApp dispatch failed: {str(e)}",
                "status": "failed"
            }

    def execute_broadcast(self, broadcast_id: int, client_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes a targeted broadcast campaign to contacts filtered by audience tags.
        """
        broadcast = db.get_broadcast(broadcast_id)
        if not broadcast:
            return {"success": False, "error": "Broadcast campaign not found"}

        target_tag = broadcast.get("target_tag", "all")
        template_body = broadcast.get("template_body", "")

        contacts = db.list_contacts(client_id=client_id)
        if target_tag != "all":
            contacts = [c for c in contacts if target_tag.lower() in [t.lower() for t in c.get("tags", [])]]

        total = len(contacts)
        sent = 0
        delivered = 0
        read = 0

        for contact in contacts:
            # Personalize template
            msg_text = template_body.replace("{{name}}", contact.get("name", "there"))
            msg_text = msg_text.replace("{{phone}}", contact.get("phone", ""))

            res = self.send_text_message(contact["phone"], msg_text)
            if res.get("success"):
                sent += 1
                delivered += 1
                if res.get("mock"):
                    read += 1

                # Record in conversation thread
                conv = db.get_or_create_conversation(contact["id"], client_id=client_id)
                db.create_message(
                    conversation_id=conv["id"],
                    contact_id=contact["id"],
                    direction="outbound",
                    body=msg_text,
                    wa_message_id=res.get("message_id", ""),
                    status="read" if res.get("mock") else "sent",
                    client_id=client_id
                )

        db.update_broadcast_stats(broadcast_id, total=total, sent=sent, delivered=delivered, read=read, status="completed")
        return {
            "success": True,
            "total_recipients": total,
            "sent_count": sent,
            "delivered_count": delivered,
            "read_count": read
        }

    def process_incoming_webhook(self, payload: Dict[str, Any], client_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Ingests and processes incoming WhatsApp Meta Webhook payloads.
        Handles message receipt, status transitions, contact discovery, and auto-responder rules.
        """
        processed_messages = []
        processed_statuses = []

        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                val = change.get("value", {})
                
                # 1. Process Message Status Updates (sent, delivered, read)
                statuses = val.get("statuses", [])
                for st in statuses:
                    wa_id = st.get("id")
                    status_name = st.get("status")
                    if wa_id and status_name:
                        db.update_message_status(wa_id, status_name)
                        processed_statuses.append({"id": wa_id, "status": status_name})

                # 2. Process Inbound Messages
                messages = val.get("messages", [])
                contacts_meta = {c.get("wa_id"): c.get("profile", {}).get("name") for c in val.get("contacts", [])}

                for msg in messages:
                    sender_phone = msg.get("from", "")
                    sender_name = contacts_meta.get(sender_phone) or f"Lead {sender_phone[-4:]}"
                    msg_id = msg.get("id", "")
                    msg_type = msg.get("type", "text")
                    
                    if msg_type == "text":
                        body = msg.get("text", {}).get("body", "")
                    else:
                        body = f"[{msg_type.capitalize()} message received]"

                    # Check or create contact
                    contact = db.get_contact_by_phone(sender_phone, client_id=client_id)
                    is_new_contact = False
                    if not contact:
                        c_id = db.create_contact(
                            name=sender_name,
                            phone="+" + sender_phone.lstrip("+"),
                            tags=["Lead"],
                            notes="Automatically discovered via inbound WhatsApp message",
                            client_id=client_id
                        )
                        contact = db.get_contact(c_id)
                        is_new_contact = True

                    # Get or create conversation thread
                    conv = db.get_or_create_conversation(contact["id"], client_id=client_id)

                    # Insert inbound message
                    db_msg_id = db.create_message(
                        conversation_id=conv["id"],
                        contact_id=contact["id"],
                        direction="inbound",
                        body=body,
                        message_type=msg_type,
                        wa_message_id=msg_id,
                        status="delivered",
                        client_id=client_id
                    )

                    processed_messages.append({
                        "message_id": db_msg_id,
                        "contact": contact["name"],
                        "body": body
                    })

                    # Run No-Code Automation Rules
                    self._evaluate_automations(contact, conv, body, is_new_contact, client_id=client_id)

        return {
            "success": True,
            "processed_messages": len(processed_messages),
            "processed_statuses": len(processed_statuses)
        }

    def _evaluate_automations(self, contact: Dict[str, Any], conv: Dict[str, Any],
                              message_body: str, is_new_contact: bool, client_id: Optional[int] = None):
        """Evaluates active automation rules and triggers automated replies."""
        automations = db.list_automations(client_id=client_id)
        lower_body = message_body.lower()

        for auto in automations:
            if not auto.get("is_active"):
                continue

            trigger = auto.get("trigger_type")
            triggered = False

            # Welcome Trigger
            if trigger == "welcome" and is_new_contact:
                triggered = True

            # Keyword Trigger
            elif trigger == "keyword":
                keywords = [k.strip().lower() for k in (auto.get("trigger_keyword") or "").split(",") if k.strip()]
                for kw in keywords:
                    if kw in lower_body:
                        triggered = True
                        break

            if triggered:
                reply_template = auto.get("message_template", "")
                reply_text = reply_template.replace("{{name}}", contact.get("name", "there"))
                reply_text = reply_text.replace("{{phone}}", contact.get("phone", ""))

                # Send outbound reply
                res = self.send_text_message(contact["phone"], reply_text)
                db.create_message(
                    conversation_id=conv["id"],
                    contact_id=contact["id"],
                    direction="outbound",
                    body=reply_text,
                    wa_message_id=res.get("message_id", ""),
                    status="delivered" if res.get("mock") else "sent",
                    client_id=client_id
                )
                db.increment_automation_execution(auto["id"])
                db.log_event(f"Triggered WhatsApp Automation '{auto['name']}' for {contact['name']}", "INFO")

    def trigger_blog_publish_alert(self, post_title: str, post_url: str, client_id: Optional[int] = None) -> int:
        """
        Cross-engine synergy: Automatically broadcasts newly published blog articles
        to opted-in contacts when an automation rule with trigger_type='blog_publish' is active.
        """
        automations = db.list_automations(client_id=client_id)
        pub_rules = [a for a in automations if a.get("is_active") and a.get("trigger_type") == "blog_publish"]
        if not pub_rules:
            return 0

        dispatched = 0
        contacts = db.list_contacts(client_id=client_id)
        # Target VIP or Customer leads
        target_contacts = [
            c for c in contacts 
            if any(t.lower() in ["vip", "customer", "all"] for t in c.get("tags", []))
        ] or contacts[:5]  # Fallback to top 5 contacts

        for rule in pub_rules:
            template = rule.get("message_template") or "📰 New Article Published: '{{title}}'\\n\\nRead it live: {{url}}"
            for c in target_contacts:
                msg = template.replace("{{title}}", post_title).replace("{{url}}", post_url)
                msg = msg.replace("{{name}}", c.get("name", "there"))
                res = self.send_text_message(c["phone"], msg)
                if res.get("success"):
                    conv = db.get_or_create_conversation(c["id"], client_id=client_id)
                    db.create_message(
                        conversation_id=conv["id"],
                        contact_id=c["id"],
                        direction="outbound",
                        body=msg,
                        wa_message_id=res.get("message_id", ""),
                        status="delivered" if res.get("mock") else "sent",
                        client_id=client_id
                    )
                    dispatched += 1

            db.increment_automation_execution(rule["id"])
            db.log_event(f"Broadcasted published blog '{post_title}' to {dispatched} WhatsApp contacts via automation rule '{rule['name']}'.", "INFO")

        return dispatched

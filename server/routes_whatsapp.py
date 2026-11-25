"""
GitPulse CMS - WhatsApp Meta Cloud API webhook handlers.

One public URL serves every account. Inbound events are authenticated with
Meta's X-Hub-Signature-256 (HMAC-SHA256 of the raw body with the app secret),
then routed to the owning account by the phone_number_id inside the event.
Fails closed: no secret configured, or a bad signature, means 403.
"""

import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional, Tuple

import crm_store as cs
import dbcompat
import database as db
from engine.whatsapp_client import WhatsAppClient


def handle_whatsapp_webhook_get(query: Dict[str, str]) -> Tuple[int, str, str]:
    """Meta handshake: GET ?hub.mode=subscribe&hub.challenge=...&hub.verify_token=..."""
    mode = query.get("hub.mode", "")
    token = query.get("hub.verify_token", "")
    challenge = query.get("hub.challenge", "")
    if mode == "subscribe" and cs.verify_token_matches_any(token):
        db.log_event("WhatsApp webhook verification handshake succeeded.", "INFO")
        return 200, "text/plain", challenge
    db.log_event("WhatsApp webhook handshake rejected.", "WARNING")
    return 403, "text/plain", "Forbidden"


def _signature_ok(raw_body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature[len("sha256="):])


def _secrets_for_payload(body: Dict[str, Any]):
    """App secrets of the accounts addressed by the payload, plus the optional platform-wide secret."""
    found = set()
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            pn_id = ((change.get("value") or {}).get("metadata") or {}).get("phone_number_id", "")
            account_id = cs.find_account_by_phone_number_id(pn_id)
            if account_id:
                try:
                    s = cs.get_whatsapp_credentials(account_id).get("app_secret", "")
                except Exception as e:
                    if dbcompat.is_transient(e):
                        raise
                    s = ""
                if s:
                    found.add(s)
    global_secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    if global_secret:
        found.add(global_secret)
    return found


def handle_whatsapp_webhook_post(raw_body: bytes, signature: str = "",
                                 body: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
    if body is None:
        try:
            body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            return 400, {"error": "Invalid JSON"}
    if not body:
        return 400, {"error": "Missing webhook payload"}

    if not (signature or "").startswith("sha256="):
        return 403, {"error": "Invalid signature"}      # unsigned: refuse without touching the database
    try:
        secrets_list = _secrets_for_payload(body)
    except Exception:  # noqa: BLE001  database trouble: Meta retries a 503
        return 503, {"error": "Temporarily unavailable"}
    if not any(_signature_ok(raw_body, signature or "", s) for s in secrets_list):
        db.log_event("WhatsApp webhook rejected: bad or missing signature.", "WARNING")
        return 403, {"error": "Invalid signature"}

    try:
        return 200, WhatsAppClient.process_incoming_webhook(body)
    except Exception as e:
        db.log_event(f"Error processing WhatsApp webhook ({type(e).__name__}).", "ERROR")
        return 500, {"error": "Webhook processing error"}

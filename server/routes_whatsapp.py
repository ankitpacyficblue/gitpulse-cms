"""
GitPulse CMS - WhatsApp Business Meta Cloud API Webhook Handlers
Handles Meta webhook verification challenges (GET) and incoming messages/status events (POST).
"""

from typing import Dict, Any, Tuple
import database as db
from engine.whatsapp_client import WhatsAppClient

def handle_whatsapp_webhook_get(query: Dict[str, str]) -> Tuple[int, str, str]:
    """
    Handles Meta WhatsApp Webhook handshake verification.
    Meta requests: GET /api/webhook/whatsapp?hub.mode=subscribe&hub.challenge=1158201444&hub.verify_token=...
    """
    mode = query.get("hub.mode", "")
    token = query.get("hub.verify_token", "")
    challenge = query.get("hub.challenge", "")

    cfg = db.get_whatsapp_config()
    expected_token = cfg.get("verify_token") or "gitpulse_webhook_verify"

    if mode == "subscribe" and token == expected_token:
        db.log_event("WhatsApp webhook verification handshake succeeded.", "INFO")
        return 200, "text/plain", challenge

    db.log_event(f"WhatsApp webhook handshake rejected: mode={mode}, token_match={token == expected_token}", "WARNING")
    return 403, "text/plain", "Forbidden: Invalid verify token"

def handle_whatsapp_webhook_post(body: Dict[str, Any], client_id=None) -> Tuple[int, Dict[str, Any]]:
    """
    Processes incoming WhatsApp messages and status notifications from Meta Graph API.
    """
    if not body:
        return 400, {"error": "Missing webhook payload"}

    try:
        wa_client = WhatsAppClient()
        result = wa_client.process_incoming_webhook(body, client_id=client_id)
        return 200, result
    except Exception as e:
        db.log_event(f"Error processing WhatsApp webhook: {str(e)}", "ERROR")
        return 500, {"error": f"Webhook processing error: {str(e)}"}

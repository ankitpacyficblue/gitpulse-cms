"""
GitPulse CMS - WhatsApp Automation & CRM (WACRM) Test Suite
Tests official Meta Cloud API client, webhook handshake, auto-responders,
conversations, contacts CDP, deals Kanban, and blog publishing alerts.
"""

import unittest
import json
import time
from datetime import datetime

import database as db
from engine.whatsapp_client import WhatsAppClient
from server.routes_whatsapp import handle_whatsapp_webhook_get, handle_whatsapp_webhook_post
from server.routes_api import handle_api_request

class TestWhatsAppCRM(unittest.TestCase):

    def setUp(self):
        db.init_db()
        db.seed_whatsapp_demo_data()
        db.save_whatsapp_config(
            phone_number_id="109876543210123",
            access_token="mock_meta_wa_token",
            verify_token="gitpulse_webhook_verify",
            business_name="GitPulse Official WhatsApp"
        )
        self.wa_client = WhatsAppClient()
        self.mock_user = {"id": 1, "username": "admin", "role": "admin"}

    def test_whatsapp_config_storage(self):
        cfg = db.get_whatsapp_config()
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["verify_token"], "gitpulse_webhook_verify")

        new_id = db.save_whatsapp_config(
            phone_number_id="999888777666",
            access_token="mock_custom_token",
            waba_id="111222333",
            verify_token="custom_verify_secret",
            business_name="Custom Business"
        )
        self.assertGreater(new_id, 0)
        updated_cfg = db.get_whatsapp_config()
        self.assertEqual(updated_cfg["phone_number_id"], "999888777666")
        self.assertEqual(updated_cfg["verify_token"], "custom_verify_secret")

    def test_contacts_crud_and_lookup(self):
        c_id = db.create_contact(
            name="David Miller",
            phone="+15551234999",
            email="david@example.com",
            tags=["VIP", "Customer"],
            notes="Interested in enterprise SLA"
        )
        self.assertGreater(c_id, 0)

        contact = db.get_contact(c_id)
        self.assertEqual(contact["name"], "David Miller")
        self.assertIn("VIP", contact["tags"])

        by_phone = db.get_contact_by_phone("+15551234999")
        self.assertIsNotNone(by_phone)
        self.assertEqual(by_phone["id"], c_id)

        # Update
        ok = db.update_contact(c_id, name="David M. Miller", tags=["VIP", "Enterprise"])
        self.assertTrue(ok)
        updated = db.get_contact(c_id)
        self.assertEqual(updated["name"], "David M. Miller")
        self.assertIn("Enterprise", updated["tags"])

        # Delete
        del_ok = db.delete_contact(c_id)
        self.assertTrue(del_ok)
        self.assertIsNone(db.get_contact(c_id))

    def test_conversation_and_messages_lifecycle(self):
        c_id = db.create_contact(name="Grace Hopper", phone="+15559876543")
        conv = db.get_or_create_conversation(c_id)
        self.assertIsNotNone(conv)
        self.assertEqual(conv["contact_id"], c_id)

        # Inbound message
        m1 = db.create_message(
            conversation_id=conv["id"],
            contact_id=c_id,
            direction="inbound",
            body="Can you tell me more about your CMS?",
            wa_message_id="wamid.test_inbound_1"
        )
        self.assertGreater(m1, 0)

        # Outbound reply
        m2 = db.create_message(
            conversation_id=conv["id"],
            contact_id=c_id,
            direction="outbound",
            body="GitPulse is an autonomous blog publishing CMS for GitHub!",
            wa_message_id="wamid.test_outbound_1",
            status="sent"
        )
        self.assertGreater(m2, 0)

        # Update status
        db.update_message_status("wamid.test_outbound_1", "read")
        messages = db.list_messages(conv["id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]["status"], "read")

        # Mark read
        db.mark_conversation_read(conv["id"])
        c_refreshed = db.get_conversation(conv["id"])
        self.assertEqual(c_refreshed["unread_count"], 0)

    def test_sales_pipeline_kanban(self):
        deal_id = db.create_deal(
            title="Next.js Blog Implementation",
            value=8500.0,
            stage="lead",
            notes="Discussing scope"
        )
        self.assertGreater(deal_id, 0)

        deals = db.list_deals()
        self.assertTrue(any(d["id"] == deal_id for d in deals))

        # Advance through Kanban stages
        for stage in ["qualified", "proposal", "negotiation", "won"]:
            ok = db.update_deal_stage(deal_id, stage)
            self.assertTrue(ok)

        won_deals = [d for d in db.list_deals() if d["id"] == deal_id]
        self.assertEqual(won_deals[0]["stage"], "won")

        # Delete deal
        del_ok = db.delete_deal(deal_id)
        self.assertTrue(del_ok)

    def test_broadcast_campaign_dispatch(self):
        c_id = db.create_contact(
            name="Broadcast Tester",
            phone="+15557778888",
            tags=["VIP"]
        )

        b_id = db.create_broadcast(
            name="Test Campaign",
            template_body="Hi {{name}}! Check out our new update.",
            target_tag="VIP"
        )
        self.assertGreater(b_id, 0)

        res = self.wa_client.execute_broadcast(b_id)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["sent_count"], 1)

        b = db.get_broadcast(b_id)
        self.assertEqual(b["status"], "completed")

    def test_whatsapp_webhook_handshake_verification(self):
        cfg = db.get_whatsapp_config()
        token = cfg["verify_token"]

        # Valid challenge
        code, ctype, resp = handle_whatsapp_webhook_get({
            "hub.mode": "subscribe",
            "hub.verify_token": token,
            "hub.challenge": "challenge_123456"
        })
        self.assertEqual(code, 200)
        self.assertEqual(resp, "challenge_123456")

        # Invalid token rejection
        bad_code, _, _ = handle_whatsapp_webhook_get({
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "challenge_123456"
        })
        self.assertEqual(bad_code, 403)

    def test_whatsapp_webhook_inbound_and_auto_responder(self):
        inbound_phone = "15554443333"
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "waba_id_test",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "15550001111", "phone_number_id": "109876543210123"},
                        "contacts": [{"profile": {"name": "New Inbound Lead"}, "wa_id": inbound_phone}],
                        "messages": [{
                            "from": inbound_phone,
                            "id": "wamid.inbound_webhook_test_1",
                            "timestamp": str(int(time.time())),
                            "text": {"body": "Hello, what is your pricing and cost?"},
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }

        code, resp = handle_whatsapp_webhook_post(payload)
        self.assertEqual(code, 200)
        self.assertTrue(resp["success"])
        self.assertGreaterEqual(resp["processed_messages"], 1)

        # Contact should be automatically discovered
        contact = db.get_contact_by_phone("+" + inbound_phone)
        self.assertIsNotNone(contact)
        self.assertEqual(contact["name"], "New Inbound Lead")

        # Check that auto-responder triggered
        conv = db.get_or_create_conversation(contact["id"])
        messages = db.list_messages(conv["id"])
        # At least 1 inbound + 1 outbound auto-response
        self.assertGreaterEqual(len(messages), 2)
        outbound = [m for m in messages if m["direction"] == "outbound"]
        self.assertTrue(len(outbound) >= 1)
        self.assertTrue(any("pricing" in m["body"].lower() or "welcome" in m["body"].lower() for m in outbound))

    def test_blog_publish_cross_engine_whatsapp_alert(self):
        alerts_sent = self.wa_client.trigger_blog_publish_alert(
            post_title="Accelerating Microservices with Kubernetes",
            post_url="https://github.com/my-org/my-blog/pull/42"
        )
        self.assertGreaterEqual(alerts_sent, 1)

    def test_rest_api_endpoints_whatsapp(self):
        # 1. GET & POST config
        code, cfg = handle_api_request("GET", "/api/whatsapp/config", {}, None, self.mock_user)
        self.assertEqual(code, 200)

        # 2. GET contacts
        code, cnt_data = handle_api_request("GET", "/api/whatsapp/contacts", {}, None, self.mock_user)
        self.assertEqual(code, 200)
        self.assertIn("contacts", cnt_data)

        # 3. GET conversations
        code, conv_data = handle_api_request("GET", "/api/whatsapp/conversations", {}, None, self.mock_user)
        self.assertEqual(code, 200)
        self.assertIn("conversations", conv_data)

        # 4. GET deals
        code, deal_data = handle_api_request("GET", "/api/whatsapp/deals", {}, None, self.mock_user)
        self.assertEqual(code, 200)
        self.assertIn("deals", deal_data)

        # 5. Simulate inbound message
        sim_code, sim_res = handle_api_request("POST", "/api/whatsapp/simulate-incoming", {}, {
            "name": "API Test Lead",
            "phone": "+19998887777",
            "message": "Hi GitPulse! I want pricing."
        }, self.mock_user)
        self.assertEqual(sim_code, 200)
        self.assertTrue(sim_res["success"])

if __name__ == "__main__":
    unittest.main()

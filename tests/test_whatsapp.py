"""Per-account WhatsApp: encrypted config, webhook signature + routing, sends, automations, broadcasts."""
import hashlib
import hmac
import json
import os
import unittest
import tests._env  # noqa: F401
from tests.apihelpers import Caller, new_user, new_account, join, setup_db
import crm_store as cs
from database import get_connection
from engine.whatsapp_client import WhatsAppClient
from server.routes_whatsapp import handle_whatsapp_webhook_get, handle_whatsapp_webhook_post


def sign(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def payload(phone_number_id, sender="15550001111", text="hello", name="Pat"):
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": phone_number_id},
        "contacts": [{"wa_id": sender, "profile": {"name": name}}],
        "messages": [{"from": sender, "id": f"wamid.{os.urandom(4).hex()}", "type": "text", "text": {"body": text}}]}}]}]}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup_db()

    def setUp(self):
        os.environ.pop("WHATSAPP_MOCK", None)
        os.environ.pop("WHATSAPP_APP_SECRET", None)
        self.a, self.b = new_account(), new_account()
        self.owner_a, self.owner_b = new_user("oa"), new_user("ob")
        join(self.a, self.owner_a, "owner")
        join(self.b, self.owner_b, "owner")
        self.api_a, self.api_b = Caller(self.owner_a, self.a), Caller(self.owner_b, self.b)
        tag = os.urandom(3).hex()
        self.pn_a, self.pn_b = f"PNA-{tag}", f"PNB-{tag}"
        self.secret_a, self.secret_b = f"appsecret-a-{tag}", f"appsecret-b-{tag}"
        self.verify_a = cs.save_whatsapp_account(self.a, phone_number_id=self.pn_a, access_token="TOKEN-A-9999",
                                                 app_secret=self.secret_a, business_name="A Co")
        self.verify_b = cs.save_whatsapp_account(self.b, phone_number_id=self.pn_b, access_token="TOKEN-B-8888",
                                                 app_secret=self.secret_b, business_name="B Co")

    def post(self, body, secret, sig=None):
        raw = json.dumps(body).encode()
        return handle_whatsapp_webhook_post(raw, sig if sig is not None else sign(raw, secret))


class TestConfigApi(Base):
    def test_config_never_returns_token(self):
        code, cfg = self.api_a("GET", "/api/whatsapp/config")
        self.assertEqual(code, 200)
        self.assertTrue(cfg["has_token"])
        self.assertEqual(cfg["token_masked"], "…9999")
        self.assertNotIn("TOKEN-A", json.dumps(cfg))
        self.assertNotIn("access_token", cfg)

    def test_save_keeps_token_when_empty_and_returns_verify_once(self):
        acct = new_account()
        u = new_user("cfg")
        join(acct, u, "admin")
        api = Caller(u, acct)
        code, out = api("POST", "/api/whatsapp/config", {"phone_number_id": f"PN-{os.urandom(3).hex()}", "access_token": "NEWTOKEN-1234"})
        self.assertEqual(code, 200)
        self.assertTrue(out["verify_token"])
        self.assertNotIn("NEWTOKEN", json.dumps(out))
        code, out2 = api("POST", "/api/whatsapp/config", {"business_name": "Renamed", "access_token": ""})
        self.assertNotIn("verify_token", out2)
        self.assertEqual(cs.get_whatsapp_credentials(acct)["access_token"], "NEWTOKEN-1234")

    def test_other_account_cannot_claim_a_connected_number(self):
        code, out = self.api_b("POST", "/api/whatsapp/config", {"phone_number_id": self.pn_a})
        self.assertEqual((code, out["error"]), (409, "phone_number_in_use"))
        self.assertEqual(cs.find_account_by_phone_number_id(self.pn_a), self.a)

    def test_agents_cannot_read_or_change_credentials(self):
        agent = new_user("ag")
        join(self.a, agent, "agent")
        api = Caller(agent, self.a)
        self.assertEqual(api("POST", "/api/whatsapp/config", {"access_token": "x"})[0], 403)
        self.assertEqual(api("POST", "/api/whatsapp/config/verify-token")[0], 403)

    def test_rotate_verify_token(self):
        code, out = self.api_a("POST", "/api/whatsapp/config/verify-token")
        self.assertEqual(code, 200)
        self.assertEqual(handle_whatsapp_webhook_get({"hub.mode": "subscribe", "hub.verify_token": self.verify_a, "hub.challenge": "c"})[0], 403)
        self.assertEqual(handle_whatsapp_webhook_get({"hub.mode": "subscribe", "hub.verify_token": out["verify_token"], "hub.challenge": "c"})[0], 200)

    def test_stored_values_are_ciphertext(self):
        with get_connection() as conn:
            row = dict(conn.execute("SELECT * FROM whatsapp_accounts WHERE account_id = ?", (self.a,)).fetchone())
        blob = json.dumps(row)
        self.assertNotIn("TOKEN-A-9999", blob)
        self.assertNotIn(self.secret_a, blob)
        self.assertNotIn(self.verify_a, blob)


class TestWebhookHandshake(Base):
    def test_handshake_with_account_verify_token(self):
        code, ctype, body = handle_whatsapp_webhook_get({"hub.mode": "subscribe", "hub.verify_token": self.verify_a, "hub.challenge": "12345"})
        self.assertEqual((code, body), (200, "12345"))

    def test_old_default_token_and_garbage_rejected(self):
        for tok in ("gitpulse_webhook_verify", "", "nope"):
            self.assertEqual(handle_whatsapp_webhook_get({"hub.mode": "subscribe", "hub.verify_token": tok, "hub.challenge": "c"})[0], 403)
        self.assertEqual(handle_whatsapp_webhook_get({"hub.mode": "other", "hub.verify_token": self.verify_a, "hub.challenge": "c"})[0], 403)


class TestWebhookPost(Base):
    def test_signed_event_lands_only_in_owning_account(self):
        code, res = self.post(payload(self.pn_a, sender="15551230001", text="hi from A's customer"), self.secret_a)
        self.assertEqual(code, 200)
        self.assertEqual(res["processed_messages"], 1)
        self.assertEqual(len(cs.list_contacts(self.a)), 1)
        self.assertEqual(cs.list_contacts(self.b), [])
        conv = cs.list_conversations(self.a)[0]
        self.assertEqual(cs.list_messages(self.a, conv["id"])[0]["body"], "hi from A's customer")

    def test_same_customer_number_in_two_accounts_stays_separate(self):
        self.post(payload(self.pn_a, sender="15559998888"), self.secret_a)
        self.post(payload(self.pn_b, sender="15559998888"), self.secret_b)
        self.assertEqual(len(cs.list_contacts(self.a)), 1)
        self.assertEqual(len(cs.list_contacts(self.b)), 1)
        self.assertNotEqual(cs.list_contacts(self.a)[0]["id"], cs.list_contacts(self.b)[0]["id"])

    def test_wrong_signature_missing_signature_and_wrong_account_secret_rejected(self):
        body = payload(self.pn_a)
        self.assertEqual(self.post(body, self.secret_a, sig="sha256=" + "0" * 64)[0], 403)
        self.assertEqual(self.post(body, self.secret_a, sig="")[0], 403)
        self.assertEqual(self.post(body, self.secret_b)[0], 403)       # B's secret cannot inject into A
        self.assertEqual(cs.list_contacts(self.a), [])

    def test_no_secret_configured_fails_closed(self):
        acct = new_account()
        cs.save_whatsapp_account(acct, phone_number_id="PN-nosecret-" + os.urandom(3).hex(), access_token="t")
        pn = cs.get_whatsapp_public(acct)["phone_number_id"]
        raw = json.dumps(payload(pn)).encode()
        self.assertEqual(handle_whatsapp_webhook_post(raw, sign(raw, ""))[0], 403)
        self.assertEqual(handle_whatsapp_webhook_post(raw, "")[0], 403)

    def test_unknown_phone_number_id_is_dropped(self):
        os.environ["WHATSAPP_APP_SECRET"] = "platform-secret"
        raw = json.dumps(payload("PN-unknown")).encode()
        code, res = handle_whatsapp_webhook_post(raw, sign(raw, "platform-secret"))
        self.assertEqual(code, 200)
        self.assertEqual((res["processed_messages"], res["skipped_unknown_number"]), (0, 1))

    def test_payload_cannot_choose_account(self):
        body = payload(self.pn_a)
        body["client_id"] = self.b
        body["account_id"] = self.b
        self.post(body, self.secret_a)
        self.assertEqual(cs.list_contacts(self.b), [])
        self.assertEqual(len(cs.list_contacts(self.a)), 1)

    def test_status_updates_scoped(self):
        self.post(payload(self.pn_a, sender="15553334444"), self.secret_a)
        conv = cs.list_conversations(self.a)[0]
        wa_id = cs.list_messages(self.a, conv["id"])[0]["wa_message_id"]
        status_b = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": self.pn_b},
                                                     "statuses": [{"id": wa_id, "status": "read"}]}}]}]}
        self.post(status_b, self.secret_b)
        self.assertEqual(cs.list_messages(self.a, conv["id"])[0]["status"], "delivered")   # unchanged by B
        status_a = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": self.pn_a},
                                                     "statuses": [{"id": wa_id, "status": "read"}]}}]}]}
        self.post(status_a, self.secret_a)
        self.assertEqual(cs.list_messages(self.a, conv["id"])[0]["status"], "read")

    def test_invalid_json_and_empty_body(self):
        self.assertEqual(handle_whatsapp_webhook_post(b"not json", "x")[0], 400)
        self.assertEqual(handle_whatsapp_webhook_post(b"", "x")[0], 400)


class TestSendingAndAutomations(Base):
    def test_unconfigured_account_cannot_send_and_no_mock_fallback(self):
        acct = new_account()
        res = WhatsAppClient(acct).send_text_message("+15550001111", "hi")
        self.assertFalse(res["success"])
        self.assertNotIn("mock", res)

    def test_mock_mode_only_with_env_flag(self):
        os.environ["WHATSAPP_MOCK"] = "1"
        res = WhatsAppClient(new_account()).send_text_message("+15550001111", "hi")
        self.assertTrue(res["success"] and res["mock"])

    def test_client_requires_account(self):
        with self.assertRaises(ValueError):
            WhatsAppClient("")

    def test_welcome_and_keyword_automations_only_fire_in_their_account(self):
        os.environ["WHATSAPP_MOCK"] = "1"
        cs.create_automation(self.a, "Welcome", "welcome", "Welcome {{name}}!")
        cs.create_automation(self.a, "Price", "keyword", "Prices at example.com", trigger_keyword="price, cost")
        cs.create_automation(self.b, "B welcome", "welcome", "B says hi")
        self.post(payload(self.pn_a, sender="15554445555", text="what is the price?", name="Dana"), self.secret_a)
        conv = cs.list_conversations(self.a)[0]
        msgs = cs.list_messages(self.a, conv["id"])
        bodies = [m["body"] for m in msgs if m["direction"] == "outbound"]
        self.assertIn("Welcome Dana!", bodies)
        self.assertIn("Prices at example.com", bodies)
        self.assertNotIn("B says hi", bodies)
        self.assertEqual([x["executions_count"] for x in cs.list_automations(self.b)], [0])

    def test_broadcast_reaches_only_own_contacts(self):
        os.environ["WHATSAPP_MOCK"] = "1"
        cs.create_contact(self.a, "A1", "+15550100001", tags=["VIP"])
        cs.create_contact(self.a, "A2", "+15550100002", tags=["Lead"])
        cs.create_contact(self.b, "B1", "+15550100003", tags=["VIP"])
        bid = cs.create_broadcast(self.a, "Promo", "Hi {{name}}", target_tag="VIP")
        code, out = self.api_a("POST", f"/api/whatsapp/broadcasts/{bid}/run")
        self.assertEqual(code, 200)
        self.assertEqual((out["stats"]["total_recipients"], out["stats"]["sent_count"]), (1, 1))
        self.assertEqual((out["stats"]["delivered_count"], out["stats"]["read_count"]), (0, 0))
        self.assertTrue(out["stats"]["mock"])
        conv = cs.list_conversations(self.a)[0]
        self.assertEqual([m["status"] for m in cs.list_messages(self.a, conv["id"])], ["mock"])
        self.assertTrue(self.api_a("GET", "/api/whatsapp/config")[1]["mock_mode"])
        self.assertEqual(cs.list_conversations(self.b), [])

    def test_broadcast_without_config_fails_cleanly(self):
        acct = new_account()
        u = new_user("bc")
        join(acct, u, "admin")
        bid = cs.create_broadcast(acct, "P", "x")
        code, out = Caller(u, acct)("POST", f"/api/whatsapp/broadcasts/{bid}/run")
        self.assertEqual(code, 400)

    def test_blog_alert_only_to_opted_in_tags(self):
        os.environ["WHATSAPP_MOCK"] = "1"
        cs.create_contact(self.a, "Vip", "+15550200001", tags=["VIP"])
        cs.create_contact(self.a, "Cold", "+15550200002", tags=["Lead"])
        cs.create_automation(self.a, "Alert", "blog_publish", "New: {{title}} {{url}}")
        self.assertEqual(WhatsAppClient(self.a).trigger_blog_publish_alert("T", "https://x/y"), 1)

    def test_send_message_endpoint_records_failure_when_unconfigured(self):
        acct = new_account()
        u = new_user("snd")
        join(acct, u, "agent")
        cid = cs.create_contact(acct, "C", "+15550300001")
        conv = cs.get_or_create_conversation(acct, cid)
        code, out = Caller(u, acct)("POST", f"/api/whatsapp/conversations/{conv['id']}/messages", {"body": "hello"})
        self.assertEqual(code, 502)
        self.assertEqual(cs.list_messages(acct, conv["id"])[0]["status"], "failed")

    def test_simulate_incoming_off_unless_mock_and_scoped(self):
        self.assertEqual(self.api_a("POST", "/api/whatsapp/simulate-incoming", {"phone": "+15550400001"})[0], 404)
        os.environ["WHATSAPP_MOCK"] = "1"
        code, out = self.api_a("POST", "/api/whatsapp/simulate-incoming", {"phone": "+15550400001", "message": "hi"})
        self.assertEqual((code, out["processed_messages"]), (200, 1))
        self.assertEqual(len(cs.list_contacts(self.a)), 1)
        self.assertEqual(cs.list_contacts(self.b), [])
        viewer = new_user("vw")
        join(self.a, viewer, "viewer")
        self.assertEqual(Caller(viewer, self.a)("POST", "/api/whatsapp/simulate-incoming", {"phone": "+1"})[0], 403)


class TestNoSecretsInLogs(Base):
    def test_logs_contain_no_tokens_or_message_text(self):
        from database import list_logs
        self.post(payload(self.pn_a, text="very private message body"), self.secret_a)
        self.post(payload(self.pn_a), self.secret_b)       # rejected
        self.api_a("POST", "/api/whatsapp/config", {"access_token": "TOKEN-LEAK-CHECK-7777"})
        everything = json.dumps(list_logs(self.a, 500)) + json.dumps(list_logs(self.b, 500))
        with get_connection() as conn:
            everything += json.dumps([dict(r) for r in conn.execute("SELECT message, metadata FROM system_logs").fetchall()])
        for needle in ("TOKEN-LEAK-CHECK", "TOKEN-A-9999", "very private message body", self.secret_a, self.verify_a):
            self.assertNotIn(needle, everything)


if __name__ == "__main__":
    unittest.main()

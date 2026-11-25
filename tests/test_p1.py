"""Role changes by an account admin, user purge, WhatsApp connection status, input validation."""
import os
import unittest
from unittest import mock

import tests._env  # noqa: F401
from tests.apihelpers import Caller, new_user, new_account, join, setup_db
import crm_store as cs
from engine import auth


class P1Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup_db()
        cls.acct = new_account()
        cls.ids, cls.c = {}, {}
        for role in ("owner", "admin", "agent", "viewer"):
            u = new_user(role)
            join(cls.acct, u, role)
            cls.ids[role] = u["id"] if isinstance(u, dict) else u
            cls.c[role] = Caller(u, cls.acct)


class RoleChangeTests(P1Base):
    def url(self, uid):
        return f"/api/accounts/{self.acct}/users/{uid}"

    def test_admin_changes_viewer_and_back(self):
        a = self.c["admin"]
        self.assertEqual(a("PUT", self.url(self.ids["viewer"]), {"role": "agent"})[0], 200)
        self.assertEqual(a("PUT", self.url(self.ids["viewer"]), {"role": "viewer"})[0], 200)

    def test_admin_cannot_touch_owner_or_grant_owner(self):
        a = self.c["admin"]
        self.assertEqual(a("PUT", self.url(self.ids["owner"]), {"role": "agent"})[0], 403)
        self.assertEqual(a("PUT", self.url(self.ids["agent"]), {"role": "owner"})[0], 403)

    def test_last_owner_cannot_be_demoted(self):
        code, body = self.c["owner"]("PUT", self.url(self.ids["owner"]), {"role": "admin"})
        self.assertEqual((code, body["error"]), (409, "last_owner"))

    def test_bad_input_is_4xx_not_500(self):
        a = self.c["admin"]
        self.assertEqual(a("PUT", self.url(self.ids["agent"]), {"role": "bogus"})[0], 400)
        self.assertEqual(a("PUT", self.url(self.ids["agent"]), {})[0], 400)
        self.assertEqual(a("PUT", self.url(self.ids["agent"]), None)[0], 400)
        self.assertEqual(a("PUT", self.url(999999), {"role": "agent"})[0], 404)

    def test_agent_and_viewer_cannot_change_roles(self):
        for r in ("agent", "viewer"):
            self.assertEqual(self.c[r]("PUT", self.url(self.ids["viewer"]), {"role": "agent"})[0], 403)


class PurgeTests(P1Base):
    def test_remove_with_purge_deletes_orphan_login_only(self):
        o = self.c["owner"]
        solo = new_user("solo")
        join(self.acct, solo, "agent")
        uid = solo["id"] if isinstance(solo, dict) else solo
        code, body = o("DELETE", f"/api/accounts/{self.acct}/users/{uid}", query={"purge": "1"})
        self.assertEqual((code, body["login_deleted"]), (200, True))
        self.assertIsNone(auth.get_user_by_id(uid))

    def test_shared_login_is_not_deleted(self):
        other = new_account()
        shared = new_user("shared")
        join(self.acct, shared, "agent")
        join(other, shared, "agent")
        uid = shared["id"] if isinstance(shared, dict) else shared
        code, body = self.c["owner"]("DELETE", f"/api/accounts/{self.acct}/users/{uid}", query={"purge": "1"})
        self.assertEqual((code, body["login_deleted"]), (200, False))
        self.assertIsNotNone(auth.get_user_by_id(uid))

    def test_plain_remove_keeps_login(self):
        u = new_user("keep")
        join(self.acct, u, "viewer")
        uid = u["id"] if isinstance(u, dict) else u
        code, body = self.c["admin"]("DELETE", f"/api/accounts/{self.acct}/users/{uid}")
        self.assertEqual((code, body["login_deleted"]), (200, False))
        self.assertIsNotNone(auth.get_user_by_id(uid))


class ConnectionStatusTests(P1Base):
    def test_status_flow(self):
        o = self.c["owner"]
        code, st = o("GET", "/api/whatsapp/connection-status")
        self.assertEqual(code, 200)
        self.assertFalse(st["credentials"]["access_token"])
        self.assertFalse(st["ready"])
        o("POST", "/api/whatsapp/config", {"phone_number_id": "pn-status-1", "access_token": "tok-secret-1", "app_secret": "app-secret-1"})
        code, st = o("GET", "/api/whatsapp/connection-status")
        self.assertTrue(st["credentials"]["access_token"] and st["credentials"]["app_secret"])
        self.assertNotIn("tok-secret-1", str(st))
        self.assertIsNone(st["last_webhook_at"])
        # a webhook for this number stamps last_webhook_at
        from engine.whatsapp_client import WhatsAppClient
        WhatsAppClient.process_incoming_webhook({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "pn-status-1"}}}]}]})
        st = o("GET", "/api/whatsapp/connection-status")[1]
        self.assertTrue(st["last_webhook_at"])
        self.assertTrue(st["ready"])

    def test_test_connection_no_network_when_unconfigured_and_stored_when_failing(self):
        acct = new_account()
        u = new_user("t")
        join(acct, u, "owner")
        o = Caller(u, acct)
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("no network expected")):
            code, res = o("POST", "/api/whatsapp/config/test", {})
        self.assertEqual((code, res["ok"]), (200, False))
        o("POST", "/api/whatsapp/config", {"phone_number_id": "pn-status-2", "access_token": "tok-2"})
        import urllib.error, io
        err = urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b'{"error":{"message":"bad token"}}'))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            res = o("POST", "/api/whatsapp/config/test", {})[1]
        self.assertFalse(res["ok"])
        st = o("GET", "/api/whatsapp/connection-status")[1]
        self.assertFalse(st["last_test"]["ok"])
        self.assertIn("bad token", st["last_test"]["message"])

    def test_viewer_can_read_status_but_not_test(self):
        self.assertEqual(self.c["viewer"]("GET", "/api/whatsapp/connection-status")[0], 200)
        self.assertEqual(self.c["viewer"]("POST", "/api/whatsapp/config/test", {})[0], 403)


class ValidationTests(P1Base):
    def test_phone(self):
        o = self.c["owner"]
        for bad in ("abc", "123", "+1 (555) 12", "5" * 20):
            self.assertEqual(o("POST", "/api/whatsapp/contacts", {"name": "n", "phone": bad})[0], 400, bad)
        code, _ = o("POST", "/api/whatsapp/contacts", {"name": "n", "phone": "+91 98765 43210"})
        self.assertEqual(code, 201)

    def test_deal_value_and_currency(self):
        o = self.c["owner"]
        self.assertEqual(o("POST", "/api/whatsapp/deals", {"title": "d", "value": -5})[0], 400)
        self.assertEqual(o("POST", "/api/whatsapp/deals", {"title": "d", "value": "nan"})[0], 400)
        self.assertEqual(o("POST", "/api/whatsapp/deals", {"title": "d", "value": 5, "currency": "RUPEES"})[0], 400)
        code, body = o("POST", "/api/whatsapp/deals", {"title": "d", "value": 5, "currency": "usd"})
        self.assertEqual((code, body["currency"]), (201, "USD"))
        code, body = o("POST", "/api/whatsapp/deals", {"title": "d2", "value": 0})
        self.assertEqual((code, body["currency"]), (201, "INR"))


class AutomationReplyTests(P1Base):
    def test_automation_reply_is_stored_as_outbound_message(self):
        acct = new_account()
        u = new_user("auto")
        join(acct, u, "owner")
        o = Caller(u, acct)
        o("POST", "/api/whatsapp/config", {"phone_number_id": "pn-auto-1", "access_token": "t", "app_secret": "s"})
        o("POST", "/api/whatsapp/automations", {"name": "A", "trigger_type": "keyword", "trigger_keyword": "price", "message_template": "Hello {{name}}"})
        payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "pn-auto-1"},
                   "contacts": [{"wa_id": "919876500001", "profile": {"name": "Ria"}}],
                   "messages": [{"from": "919876500001", "id": "wamid.a1", "type": "text", "text": {"body": "price?"}}]}}]}]}
        from engine.whatsapp_client import WhatsAppClient
        with mock.patch.dict(os.environ, {"WHATSAPP_MOCK": "1"}):
            WhatsAppClient.process_incoming_webhook(payload)
        conv = cs.list_conversations(acct)[0]
        msgs = cs.list_messages(acct, conv["id"])
        out = [m for m in msgs if m["direction"] == "outbound"]
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["body"], "Hello Ria")


class PlatformAdminTests(P1Base):
    def test_platform_admin_lists_and_manages_any_account(self):
        pa = new_user("pa", platform_admin=True)
        c = Caller(pa, None)
        code, body = c("GET", "/api/accounts")
        ids = {a["id"] for a in body["accounts"]}
        self.assertIn(self.acct, ids)
        self.assertTrue(all("member_count" in a for a in body["accounts"]))
        self.assertEqual(Caller(pa, self.acct)("GET", "/api/whatsapp/contacts")[0], 200)
        self.assertEqual(Caller(pa, self.acct)("GET", f"/api/accounts/{self.acct}/users")[0], 200)

    def test_normal_user_still_sees_only_own_and_is_denied_elsewhere(self):
        other = new_account()
        self.assertEqual(self.c["owner"]("GET", "/api/whatsapp/contacts", account_id=other)[0], 403)
        ids = {a["id"] for a in self.c["owner"]("GET", "/api/accounts")[1]["accounts"]}
        self.assertNotIn(other, ids)

    def test_missing_account_header_has_select_account_code(self):
        pa = new_user("pa2", platform_admin=True)
        code, body = Caller(pa, None)("GET", "/api/projects")
        self.assertEqual((code, body["code"]), (400, "select_account"))

    def test_delete_account_removes_orphan_logins_only(self):
        pa = new_user("pa3", platform_admin=True)
        acct = new_account()
        solo, shared = new_user("solo2"), new_user("shared2")
        join(acct, solo, "owner")
        join(acct, shared, "agent")
        join(new_account(), shared, "agent")
        name = cs.get_account(acct)["name"]
        code, _ = Caller(pa, acct)("DELETE", f"/api/accounts/{acct}", {"confirm_name": name})
        self.assertEqual(code, 200)
        uid = lambda u: u["id"] if isinstance(u, dict) else u
        self.assertIsNone(auth.get_user_by_id(uid(solo)))
        self.assertIsNotNone(auth.get_user_by_id(uid(shared)))
        self.assertIsNotNone(auth.get_user_by_id(uid(pa)))


if __name__ == "__main__":
    unittest.main()

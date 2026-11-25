"""API access control: default deny, role matrix, cross-account isolation, account/user endpoints."""
import unittest
import tests._env  # noqa: F401
from tests.apihelpers import Caller, new_user, new_account, join, setup_db
import crm_store as cs


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup_db()
        cls.acct = new_account()
        cls.other = new_account()
        cls.users = {}
        for role in ("owner", "admin", "agent", "viewer"):
            u = new_user(role)
            join(cls.acct, u, role)
            cls.users[role] = Caller(u, cls.acct)
        cls.outsider_user = new_user("out")
        join(cls.other, cls.outsider_user, "owner")
        cls.outsider = Caller(cls.outsider_user, cls.other)
        cls.platform = new_user("pa", platform_admin=True)


class TestAuthAndDefaultDeny(Base):
    def test_unauthenticated_gets_401_everywhere_but_public(self):
        c = Caller(None, self.acct)
        for method, path in (("GET", "/api/whatsapp/contacts"), ("GET", "/api/projects"), ("GET", "/api/auth/me"),
                             ("GET", "/api/accounts"), ("GET", "/api/settings"), ("POST", "/api/whatsapp/config")):
            self.assertEqual(c(method, path)[0], 401, path)
        self.assertEqual(c("GET", "/api/presets")[0], 200)

    def test_unknown_route_404_even_for_owner(self):
        self.assertEqual(self.users["owner"]("GET", "/api/whatsapp/everything")[0], 404)
        self.assertEqual(self.users["owner"]("POST", "/api/clients", {"name": "x"})[0], 404)

    def test_account_header_required_and_membership_checked(self):
        v = self.users["viewer"]
        code, body = v("GET", "/api/whatsapp/contacts", account_id=None)
        self.assertEqual((code, body["error"]), (400, "account_required"))
        self.assertEqual(v("GET", "/api/whatsapp/contacts", account_id=self.other)[0], 403)
        self.assertEqual(v("GET", "/api/whatsapp/contacts", account_id="doesnotexist")[0], 403)

    def test_client_id_param_and_body_are_ignored(self):
        o = self.users["owner"]
        o("POST", "/api/whatsapp/contacts", {"name": "Mine", "phone": "+15557770001", "client_id": self.other,
                                              "account_id": self.other})
        self.assertEqual(len(cs.list_contacts(self.acct, search="Mine")), 1)
        self.assertEqual(cs.list_contacts(self.other, search="Mine"), [])
        code, body = o("GET", "/api/whatsapp/contacts", query={"client_id": self.other})
        self.assertTrue(all(c["name"] != "x" for c in body["contacts"]))


class TestRoleMatrix(Base):
    # (method, path, body, minimum role that may call it)
    CASES = [
        ("GET", "/api/whatsapp/contacts", None, "viewer"),
        ("GET", "/api/whatsapp/conversations", None, "viewer"),
        ("GET", "/api/whatsapp/deals", None, "viewer"),
        ("GET", "/api/whatsapp/broadcasts", None, "viewer"),
        ("GET", "/api/whatsapp/automations", None, "viewer"),
        ("GET", "/api/whatsapp/config", None, "viewer"),
        ("GET", "/api/projects", None, "viewer"),
        ("GET", "/api/posts", None, "viewer"),
        ("POST", "/api/whatsapp/contacts", {"name": "Rm", "phone": "+1555{n}"}, "agent"),
        ("POST", "/api/whatsapp/deals", {"title": "D"}, "agent"),
        ("POST", "/api/whatsapp/config", {"phone_number_id": "pn-matrix-{n}"}, "admin"),
        ("POST", "/api/whatsapp/automations", {"name": "A", "trigger_type": "welcome", "message_template": "hi"}, "admin"),
        ("POST", "/api/whatsapp/broadcasts", {"name": "B", "template_body": "hi"}, "admin"),
        ("POST", "/api/projects", {"name": "P", "github_repo": "o/r{n}", "topic": "t"}, "admin"),
        ("GET", "/api/logs", None, "admin"),
    ]
    ORDER = ["viewer", "agent", "admin", "owner"]

    def test_matrix(self):
        n = 0
        for method, path, body, minimum in self.CASES:
            for role in self.ORDER:
                n += 1
                b = None
                if body:
                    b = {k: (v.format(n=f"{n:06d}") if isinstance(v, str) else v) for k, v in body.items()}
                # role-specific unique values for creates
                code, resp = self.users[role](method, path, b)
                allowed = self.ORDER.index(role) >= self.ORDER.index(minimum)
                if allowed:
                    self.assertNotIn(code, (401, 403), f"{role} should reach {method} {path}: {code} {resp}")
                else:
                    self.assertEqual(code, 403, f"{role} must be denied {method} {path}")
                    self.assertIn("required", resp)

    def test_delete_requires_admin(self):
        cid = cs.create_contact(self.acct, "Del", "+15558880001")
        did = cs.create_deal(self.acct, "Del deal", 1)
        for role in ("viewer", "agent"):
            self.assertEqual(self.users[role]("DELETE", f"/api/whatsapp/contacts/{cid}")[0], 403)
            self.assertEqual(self.users[role]("DELETE", f"/api/whatsapp/deals/{did}")[0], 403)
        self.assertEqual(self.users["admin"]("DELETE", f"/api/whatsapp/contacts/{cid}")[0], 200)
        self.assertEqual(self.users["admin"]("DELETE", f"/api/whatsapp/deals/{did}")[0], 200)

    def test_viewer_cannot_send_messages_or_mark_read(self):
        cid = cs.create_contact(self.acct, "Chat", "+15558880002")
        conv = cs.get_or_create_conversation(self.acct, cid)
        base = f"/api/whatsapp/conversations/{conv['id']}"
        self.assertEqual(self.users["viewer"]("POST", base + "/messages", {"body": "hi"})[0], 403)
        self.assertEqual(self.users["viewer"]("POST", base + "/read")[0], 403)
        self.assertEqual(self.users["viewer"]("GET", base + "/messages")[0], 200)

    def test_global_settings_and_supabase_are_platform_only(self):
        for path, method in (("/api/settings", "GET"), ("/api/settings", "POST"), ("/api/supabase/sync", "POST"),
                             ("/api/supabase/status", "GET")):
            self.assertEqual(self.users["owner"](method, path)[0], 403, path)
        self.assertEqual(Caller(self.platform)("GET", "/api/settings")[0], 200)


class TestCrossAccountIsolationViaApi(Base):
    def test_cannot_touch_other_accounts_rows_by_id(self):
        cid = cs.create_contact(self.other, "Secret", "+15559990001")
        did = cs.create_deal(self.other, "Secret deal", 5, contact_id=cid)
        conv = cs.get_or_create_conversation(self.other, cid)
        bid = cs.create_broadcast(self.other, "Secret bc", "x")
        aid = cs.create_automation(self.other, "Secret auto", "welcome", "x")
        o = self.users["owner"]
        for method, path, body in (
            ("DELETE", f"/api/whatsapp/contacts/{cid}", None),
            ("PUT", f"/api/whatsapp/contacts/{cid}", {"name": "Hacked"}),
            ("DELETE", f"/api/whatsapp/deals/{did}", None),
            ("PUT", f"/api/whatsapp/deals/{did}/stage", {"stage": "won"}),
            ("GET", f"/api/whatsapp/conversations/{conv['id']}", None),
            ("GET", f"/api/whatsapp/conversations/{conv['id']}/messages", None),
            ("POST", f"/api/whatsapp/conversations/{conv['id']}/messages", {"body": "hi"}),
            ("POST", f"/api/whatsapp/conversations/{conv['id']}/read", None),
            ("POST", f"/api/whatsapp/broadcasts/{bid}/run", None),
            ("PUT", f"/api/whatsapp/automations/{aid}/toggle", {"is_active": False}),
            ("DELETE", f"/api/whatsapp/automations/{aid}", None),
        ):
            code, _ = o(method, path, body)
            self.assertIn(code, (400, 404), f"{method} {path} -> {code}")
        self.assertEqual(cs.get_contact(self.other, cid)["name"], "Secret")
        self.assertEqual(len(cs.list_deals(self.other)), 1)
        self.assertTrue(cs.list_automations(self.other)[0]["is_active"])
        self.assertEqual(cs.list_messages(self.other, conv["id"]), [])

    def test_delete_contact_keeps_deal_unlinked_and_drops_conversation(self):
        cid = cs.create_contact(self.acct, "Gone", "+15559990009")
        did = cs.create_deal(self.acct, "Keep me", 5, contact_id=cid)
        cs.get_or_create_conversation(self.acct, cid)
        code, _ = self.users["admin"]("DELETE", f"/api/whatsapp/contacts/{cid}")
        self.assertEqual(code, 200)
        deals = [d for d in cs.list_deals(self.acct) if d["id"] == did]
        self.assertEqual(len(deals), 1)
        self.assertIsNone(deals[0]["contact_id"])
        self.assertNotIn(cid, [c["contact_id"] for c in cs.list_conversations(self.acct)])

    def test_handler_exception_returns_json_500(self):
        from unittest import mock
        with mock.patch.object(cs, "delete_deal", side_effect=RuntimeError("boom")):
            code, body = self.users["admin"]("DELETE", "/api/whatsapp/deals/1")
        self.assertEqual(code, 500)
        self.assertEqual(body["code"], "INTERNAL")

    def test_validation_and_partial_config_save(self):
        o = self.users["owner"]
        code, b = o("POST", "/api/whatsapp/automations", {"name": "x", "trigger_type": "new_contact", "message_template": "hi"})
        self.assertEqual((code, b["error"]), (400, "invalid_trigger"))
        code, b = o("POST", "/api/whatsapp/automations", {"name": "x", "trigger_type": "keyword", "message_template": "hi"})
        self.assertEqual((code, b["error"]), (400, "keyword_required"))
        code, b = o("POST", "/api/whatsapp/deals", {"title": "d", "stage": "bogus"})
        self.assertEqual((code, b["error"]), (400, "invalid_stage"))
        did = cs.create_deal(self.acct, "S", 1)
        self.assertEqual(o("PUT", f"/api/whatsapp/deals/{did}/stage", {"stage": "bogus"})[0], 400)
        self.assertEqual(o("PUT", f"/api/whatsapp/deals/{did}/stage", {"stage": "won"})[0], 200)
        self.assertEqual(o("POST", "/api/whatsapp/config", {"phone_number_id": "pn-b10", "waba_id": "W1", "business_name": "A"})[0], 200)
        self.assertEqual(o("POST", "/api/whatsapp/config", {"business_name": "B"})[0], 200)
        from unittest import mock
        with mock.patch.dict("os.environ", {"PUBLIC_BASE_URL": "https://preview.example.com/"}):
            cfg = o("GET", "/api/whatsapp/config")[1]
        self.assertEqual(cfg["webhook_url"], "https://preview.example.com/api/webhook/whatsapp")
        self.assertEqual((cfg["waba_id"], cfg["phone_number_id"], cfg["business_name"]), ("W1", "pn-b10", "B"))

    def test_conversation_assignment(self):
        cid = cs.create_contact(self.acct, "Assignee", "+15559990077")
        conv = cs.get_or_create_conversation(self.acct, cid)
        base = f"/api/whatsapp/conversations/{conv['id']}/assign"
        agent_id = self.users["agent"].user["id"]
        self.assertEqual(self.users["admin"]("PUT", base, {"user_id": agent_id})[0], 200)
        mine = self.users["agent"]("GET", "/api/whatsapp/conversations", query={"assigned": "me", "include_empty": "1"})[1]["conversations"]
        self.assertEqual([c["id"] for c in mine], [conv["id"]])
        self.assertEqual(self.users["admin"]("GET", "/api/whatsapp/conversations", query={"assigned": "me", "include_empty": "1"})[1]["conversations"], [])
        self.assertEqual(self.users["admin"]("PUT", base, {"user_id": self.outsider_user["id"]})[0], 400)
        self.assertEqual(self.users["admin"]("PUT", base, {"user_id": "abc"})[0], 400)
        self.assertEqual(self.users["viewer"]("PUT", base, {"user_id": agent_id})[0], 403)
        self.assertEqual(self.outsider("PUT", base, {"user_id": self.outsider_user["id"]})[0], 404)
        self.assertEqual(self.users["admin"]("PUT", base, {"user_id": None})[0], 200)
        self.assertEqual(cs.get_conversation(self.acct, conv["id"])["assigned_to"], "Team")

    def test_default_currency_is_inr_and_editable(self):
        acct = new_account()
        from tests.apihelpers import new_user as nu, join as jn
        u = nu("cur"); jn(acct, u, "owner")
        c = Caller(u, acct)
        did = cs.create_deal(acct, "D1", 10)
        self.assertEqual([d["currency"] for d in cs.list_deals(acct) if d["id"] == did], ["INR"])
        self.assertEqual(c("PATCH", f"/api/accounts/{acct}", {"default_currency": "usd"})[0], 200)
        self.assertEqual(c("GET", f"/api/accounts/{acct}")[1]["default_currency"], "USD")
        self.assertEqual(c("PATCH", f"/api/accounts/{acct}", {"default_currency": "rupees"})[0], 400)
        did2 = c("POST", "/api/whatsapp/deals", {"title": "D2"})[1]["id"]
        self.assertEqual([d["currency"] for d in cs.list_deals(acct) if d["id"] == did2], ["USD"])
        self.assertEqual(self.users["admin"]("PATCH", f"/api/accounts/{self.acct}", {"default_currency": "EUR"})[0], 403)

    def test_account_settings_are_owner_only_write_only_and_encrypted(self):
        o = self.users["owner"]
        self.assertEqual(self.users["admin"]("GET", "/api/account/settings")[0], 403)
        self.assertEqual(o("POST", "/api/account/settings", {"ai_provider": "claude"})[0], 400)
        code, out = o("POST", "/api/account/settings", {"ai_provider": "gemini", "ai_api_key": "AIza-secret-9999",
                                                       "github_token": "ghp_acct_token_1234"})
        self.assertEqual(code, 200)
        body = o("GET", "/api/account/settings")[1]
        self.assertTrue(body["has_ai_api_key"] and body["has_github_token"])
        self.assertNotIn("secret", str(body))
        self.assertEqual(body["ai_key_source"], "account")
        self.assertEqual(cs.get_account_ai(self.acct), ("gemini", "AIza-secret-9999"))
        self.assertEqual(cs.get_account_ai(self.other), ("", ""))          # other account untouched
        with cs.get_connection() as conn:
            raw = conn.execute("SELECT ai_api_key_enc, github_token_enc FROM account_settings WHERE account_id = ?",
                               (self.acct,)).fetchone()
        self.assertTrue(raw[0].startswith("v1:") and raw[1].startswith("v1:"))
        o("POST", "/api/account/settings", {"ai_provider": "openai"})        # absent key keeps stored one
        self.assertEqual(cs.get_account_ai(self.acct)[1], "AIza-secret-9999")
        o("POST", "/api/account/settings", {"clear_ai_key": True})
        self.assertFalse(o("GET", "/api/account/settings")[1]["has_ai_api_key"])

    def test_project_github_token_is_encrypted_at_rest(self):
        o = self.users["owner"]
        pid = o("POST", "/api/projects", {"name": "Enc", "github_repo": "o/r", "topic": "t",
                                          "github_token": "ghp_plain_9876"})[1]["id"]
        with cs.get_connection() as conn:
            raw = conn.execute("SELECT github_token FROM projects WHERE id = ?", (pid,)).fetchone()[0]
        self.assertTrue(raw.startswith("v1:"))
        from database import get_project
        self.assertEqual(get_project(pid)["github_token"], "ghp_plain_9876")

    def test_deal_cannot_link_foreign_contact(self):
        cid = cs.create_contact(self.other, "Foreign", "+15559990002")
        code, _ = self.users["owner"]("POST", "/api/whatsapp/deals", {"title": "Steal", "contact_id": cid})
        self.assertEqual(code, 404)

    def test_logs_scoped_to_account(self):
        from database import log_event
        log_event("marker-for-other-account", "INFO", account_id=self.other)
        code, body = self.users["admin"]("GET", "/api/logs")
        self.assertEqual(code, 200)
        self.assertFalse(any("marker-for-other-account" in l["message"] for l in body["logs"]))


class TestAccountEndpoints(Base):
    def test_me_returns_memberships_and_permissions_for_active_account(self):
        code, body = self.users["agent"]("GET", "/api/auth/me")
        self.assertEqual(code, 200)
        self.assertEqual(body["memberships"][0]["role"], "agent")
        self.assertIn("crm.write", body["permissions"])
        self.assertNotIn("wa.config", body["permissions"])
        code, body = self.users["agent"]("GET", "/api/auth/me", account_id=None)
        self.assertEqual(body["permissions"], [])
        self.assertEqual(self.users["agent"]("GET", "/api/auth/me", account_id=self.other)[0], 403)

    def test_accounts_list_only_mine(self):
        code, body = self.users["viewer"]("GET", "/api/accounts")
        self.assertEqual([a["id"] for a in body["accounts"]], [self.acct])

    def test_only_platform_admin_creates_accounts(self):
        self.assertEqual(self.users["owner"]("POST", "/api/accounts", {"name": "Nope"})[0], 403)
        code, body = Caller(self.platform)("POST", "/api/accounts", {"name": "Fresh", "owner_username": "fresh_owner_x1"})
        self.assertEqual(code, 201)
        self.assertIn("owner_temporary_password", body)
        self.assertEqual(cs.list_contacts(body["id"]), [])

    def test_user_management_over_api(self):
        a = self.users["admin"]
        code, body = a("POST", f"/api/accounts/{self.acct}/users", {"username": "invitee_api1", "role": "agent"})
        self.assertEqual(code, 201)
        uid = body["user_id"]
        self.assertIn("temporary_password", body)
        self.assertEqual(a("POST", f"/api/accounts/{self.acct}/users", {"username": "invitee_api2", "role": "owner"})[0], 403)
        self.assertEqual(a("PUT", f"/api/accounts/{self.acct}/users/{uid}", {"role": "viewer"})[0], 200)
        self.assertEqual(cs.get_membership_role(self.acct, uid), "viewer")
        code, body = a("GET", f"/api/accounts/{self.acct}/users")
        self.assertIn("invitee_api1", [u["username"] for u in body["users"]])
        self.assertEqual(a("DELETE", f"/api/accounts/{self.acct}/users/{uid}")[0], 200)
        self.assertIsNone(cs.get_membership_role(self.acct, uid))

    def test_agent_cannot_manage_users_and_outsider_cannot_see_users(self):
        self.assertEqual(self.users["agent"]("GET", f"/api/accounts/{self.acct}/users")[0], 403)
        self.assertEqual(self.outsider("GET", f"/api/accounts/{self.acct}/users")[0], 403)
        self.assertEqual(self.outsider("GET", f"/api/accounts/{self.acct}")[0], 403)

    def test_header_account_cannot_override_path_account(self):
        # outsider pins header to their own account but asks for another account's user list
        self.assertEqual(self.outsider("GET", f"/api/accounts/{self.acct}/users", account_id=self.other)[0], 403)

    def test_last_owner_via_api(self):
        solo = new_account()
        u = new_user("solo")
        join(solo, u, "owner")
        c = Caller(u, solo)
        self.assertEqual(c("PUT", f"/api/accounts/{solo}/users/{u['id']}", {"role": "admin"})[1]["error"], "last_owner")
        self.assertEqual(c("DELETE", f"/api/accounts/{solo}/users/{u['id']}")[1]["error"], "last_owner")

    def test_delete_account_flow(self):
        acct = new_account("Doomed Inc")
        u = new_user("doom")
        join(acct, u, "owner")
        c = Caller(u, acct)
        cs.create_contact(acct, "Keep", "+15550123456")
        self.assertEqual(c("DELETE", f"/api/accounts/{acct}", {"confirm_name": "wrong"})[0], 400)
        self.assertEqual(c("DELETE", f"/api/accounts/{acct}", {"confirm_name": "Doomed Inc"})[0], 200)
        self.assertEqual(c("GET", "/api/whatsapp/contacts")[0], 403)   # membership gone
        self.assertEqual(len(cs.list_contacts(acct)), 1)               # data retained, still account-scoped

    def test_admin_cannot_delete_or_rename_account(self):
        self.assertEqual(self.users["admin"]("DELETE", f"/api/accounts/{self.acct}", {"confirm_name": "x"})[0], 403)
        self.assertEqual(self.users["admin"]("PATCH", f"/api/accounts/{self.acct}", {"name": "x"})[0], 403)
        self.assertEqual(self.users["owner"]("PATCH", f"/api/accounts/{self.acct}", {"name": "Renamed OK"})[0], 200)


class TestSecretsNeverReturned(Base):
    def test_project_token_masked(self):
        o = self.users["owner"]
        code, body = o("POST", "/api/projects", {"name": "Tok", "github_repo": "o/tok-secret", "topic": "t",
                                                  "github_token": "ghp_supersecret1234", "webhook_secret": "whsec"})
        pid = body["id"]
        for path in ("/api/projects", f"/api/projects/{pid}"):
            text = str(o("GET", path)[1])
            self.assertNotIn("ghp_supersecret", text)
            self.assertNotIn("whsec", text)
        self.assertTrue(o("GET", f"/api/projects/{pid}")[1]["has_github_token"])
        o("PUT", f"/api/projects/{pid}", {"name": "Tok2", "github_token": ""})
        from database import get_project
        self.assertEqual(get_project(pid)["github_token"], "ghp_supersecret1234")   # empty keeps old

    def test_settings_masks_sensitive_values(self):
        from database import set_setting
        set_setting("openai_api_key", "sk-1234567890abcdef")
        code, body = Caller(self.platform)("GET", "/api/settings")
        self.assertNotIn("sk-1234567890", str(body))
        self.assertNotIn("session_secret", str(body) if "session_secret" not in body else "")


if __name__ == "__main__":
    unittest.main()

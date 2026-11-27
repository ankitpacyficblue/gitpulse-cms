"""Section permissions and the CRM dashboard (docs/CRM-DASHBOARD-PERMISSIONS.md)."""
import unittest

import tests._env  # noqa: F401
from tests.apihelpers import Caller, new_user, new_account, join
from tests.test_phase1 import Base, website
import crm_store as cs
import database as db
from engine import access, alerts, permissions
from server.routes_api import ROUTES, handle_api_request


class RoleTests(Base):
    def person(self, role, account=None):
        user = new_user("p")
        code, out = self.api("POST", f"/api/accounts/{self.a}/users", {"username": user["username"], "role": role})
        self.assertEqual(code, 201, out)
        return user, Caller(user, self.a)

    def row(self, user):
        with db.get_connection() as c:
            return dict(c.execute("SELECT * FROM memberships WHERE account_id = ? AND user_id = ?",
                                  (self.a, user["id"])).fetchone())

    def me(self, api):
        return api("GET", "/api/auth/me")[1]

    def test_existing_roles_keep_exactly_what_they_had(self):
        for old, user in (("owner", self.owner), ("agent", self.agent), ("viewer", self.viewer)):
            self.assertEqual(access.names(access.membership(self.a, user["id"])), permissions.permissions_for(old), old)
        admin = new_user("ad")
        join(self.a, admin, "admin")
        self.assertEqual(access.names(access.membership(self.a, admin["id"])), permissions.permissions_for("admin"))
        self.assertEqual(self.me(self.agent_api)["role_key"], "crm_agent")
        self.assertIsNone(self.row(self.agent)["role_key"])      # nothing was rewritten

    def test_every_route_enforces_its_section(self):
        users = {role: self.person(role)[0] for role in ("admin", "content_editor", "crm_agent", "viewer")}
        checked = 0
        for method, rx, need, _ in ROUTES:
            if not need.startswith(("acct:", "path:")):
                continue
            path = (rx.pattern.strip("^$").replace("(?P<aid>[0-9a-f]{32})", self.a)
                    .replace("(?P<key>[a-z_]+)", "viewer"))
            for name in ("pid", "id", "uid"):
                path = path.replace(f"(?P<{name}>\\d+)", "999999999")
            for role, user in users.items():
                who = access.membership(self.a, user["id"])
                if access.allows(who, need[5:]):
                    continue
                code, out = handle_api_request(method, path, {}, {}, current_user=user, headers={"X-Account-Id": self.a})
                self.assertEqual((code, out.get("required")), (403, need[5:]), (role, method, path, out))
                checked += 1
        self.assertGreater(checked, 100)

    def test_content_editor_and_crm_agent(self):
        _, editor = self.person("content_editor")
        _, agent = self.person("crm_agent")
        self.assertEqual(editor("GET", "/api/blog/plan")[0], 200)
        for path in ("/api/whatsapp/contacts", "/api/whatsapp/conversations", "/api/whatsapp/deals"):
            self.assertEqual((editor("GET", path)[0], agent("GET", path)[0]), (403, 200), path)
        self.assertEqual(agent("GET", "/api/blog/plan")[0], 403)
        self.assertEqual(agent("GET", "/api/whatsapp/broadcasts")[1]["required"], "broadcasts:view")
        for api, ok, denied in ((editor, "/api/dashboard", "/api/crm/dashboard"),
                                (agent, "/api/crm/dashboard", "/api/dashboard")):
            self.assertEqual(api("GET", ok, account_id=None)[0], 200)
            self.assertEqual(api("GET", denied, query={"account": self.a}, account_id=None)[0], 403)
        alerts.raise_alert(self.a, "blog_failed", "blog")
        alerts.raise_alert(self.a, "send_failed", "crm")
        seen = lambda api: {a["type"] for a in api("GET", "/api/alerts")[1]["alerts"] if a["id"] is not None}
        self.assertEqual((seen(editor), seen(agent)), ({"blog_failed"}, {"send_failed"}))

    def test_overrides_grant_and_revoke_without_escalation(self):
        agent_user, agent = self.person("crm_agent")
        admin_user, admin = self.person("admin")
        path = f"/api/accounts/{self.a}/users/{agent_user['id']}/overrides"
        self.assertEqual(admin("PUT", path, {"overrides": {"posts": "view", "inbox": "none"}})[0], 200)
        self.assertEqual((agent("GET", "/api/blog/plan")[0], agent("GET", "/api/whatsapp/conversations")[0]), (200, 403))
        self.assertEqual(admin("PUT", path, {"overrides": {"settings": "manage"}})[1]["error"], "above_your_access")
        self.assertEqual(admin("PUT", path, {"overrides": {"database": "view"}})[1]["error"], "invalid_section")
        self.assertEqual(admin("PUT", path, {"overrides": {"inbox": "full"}})[1]["error"], "invalid_level")
        own = f"/api/accounts/{self.a}/users/{admin_user['id']}/overrides"
        self.assertEqual(admin("PUT", own, {"overrides": {}})[1]["error"], "own_access")
        users = f"/api/accounts/{self.a}/users"
        self.assertEqual(admin("PUT", f"{users}/{agent_user['id']}", {"role": "owner"})[0], 403)
        self.assertEqual(admin("PUT", f"{users}/{self.owner['id']}", {"role": "viewer"})[1]["error"], "owner_only")
        self.assertEqual(self.api("PUT", f"{users}/{agent_user['id']}", {"role": "viewer"})[0], 200)
        listed = {u["user_id"]: u for u in self.api("GET", users)[1]["users"]}
        self.assertEqual((listed[agent_user["id"]]["role_key"], listed[agent_user["id"]]["overrides"]), ("viewer", {}))

    def test_a_user_manager_cannot_take_over_someone_with_more_access(self):
        manager_user, manager = self.person("viewer")
        admin_user, _ = self.person("admin")
        self.api("PUT", f"/api/accounts/{self.a}/users/{manager_user['id']}/overrides", {"overrides": {"users": "manage"}})
        users = f"/api/accounts/{self.a}/users"
        for method, path in (("POST", f"{users}/{admin_user['id']}/reset-password"), ("DELETE", f"{users}/{admin_user['id']}")):
            self.assertEqual(manager(method, path)[1]["error"], "above_your_access", path)
        self.assertEqual(manager("POST", users, {"username": "new_one", "role": "admin"})[0], 403)

    def test_role_grid_is_owner_only_and_resettable(self):
        _, admin = self.person("admin")
        _, agent = self.person("crm_agent")
        roles = f"/api/accounts/{self.a}/roles"
        self.assertEqual(admin("GET", roles)[0], 200)
        self.assertEqual(admin("PUT", roles + "/crm_agent", {"access": {"posts": "view"}})[1]["error"], "owner_only")
        self.assertEqual(self.api("PUT", roles + "/owner", {"access": {"posts": "none"}})[0], 400)
        self.assertEqual(self.api("PUT", roles + "/crm_agent", {"access": {"posts": "view", "inbox": "none"}})[0], 200)
        self.assertEqual(self.me(agent)["access"]["posts"], "view")
        self.assertEqual(self.me(agent)["access"]["inbox"], "none")
        self.assertEqual(self.me(agent)["access"]["contacts"], "manage")
        self.assertEqual(self.api_b("GET", roles)[0], 403)
        self.assertEqual(self.api("DELETE", roles + "/crm_agent")[0], 200)
        self.assertEqual(self.me(agent)["access"]["inbox"], "manage")

    def test_the_deployed_code_keeps_working_and_its_changes_win(self):
        user, api = self.person("content_editor")
        self.assertEqual(self.row(user)["role"], "viewer")      # old code sees an allowed, low role
        with db.get_connection() as c:      # exactly the statements the deployed code runs
            self.assertEqual(c.execute("SELECT m.role FROM memberships m WHERE m.account_id = ? AND m.user_id = ?",
                                       (self.a, user["id"])).fetchone()["role"], "viewer")
            c.execute("UPDATE memberships SET role = ? WHERE account_id = ? AND user_id = ?", ("admin", self.a, user["id"]))
            c.commit()
        self.assertEqual(self.me(api)["role_key"], "admin")
        with db.get_connection() as c:
            c.execute("DELETE FROM memberships WHERE account_id = ? AND user_id = ?", (self.a, user["id"]))
            c.execute("INSERT INTO memberships (account_id, user_id, role, created_at) VALUES (?,?,?,?)",
                      (self.a, user["id"], "viewer", "2026-01-01"))
            c.commit()
        self.assertEqual((self.me(api)["role_key"], self.me(api)["access"]["posts"]), ("viewer", "view"))


class CrmDashboardTests(Base):
    def get(self, user=None, **query):
        return Caller(user or self.owner)("GET", "/api/crm/dashboard", query=query, account_id=None)

    def test_numbers(self):
        self.api("POST", "/api/whatsapp/automations", {"name": "Hi", "trigger_type": "keyword", "trigger_keyword": "plots",
                                                       "message_template": "Hello {{name}}"})
        self.assertEqual(self.api("POST", "/api/whatsapp/config", {"phone_number": "919999999999"})[0], 200)
        self.assertEqual(self.api("POST", "/api/entry-links", {"label": "Site", "code": "WEB"})[0], 201)
        self.inbound("plots please")
        self.inbound("anyone there?")
        for title, stage, value in (("A", "lead", 100), ("B", "won", 50), ("C", "lost", 7)):
            self.assertEqual(self.api("POST", "/api/whatsapp/deals", {"title": title, "stage": stage, "value": value,
                                                                      "currency": "INR"})[0], 201)
        code, body = self.get(account=self.a)
        self.assertEqual(code, 200, body)
        cards = body["cards"]
        self.assertEqual((cards["unread_conversations"], cards["new_contacts_7d"], cards["new_contacts_30d"]), (1, 1, 1))
        self.assertEqual(cards["open_deals"], {"count": 1, "values": [{"currency": "INR", "value": 100}]})
        self.assertEqual(cards["won_this_month"]["values"], [{"currency": "INR", "value": 50}])
        self.assertEqual([p["stage"] for p in body["pipeline"]], ["lead", "qualified", "proposal", "negotiation", "won", "lost"])
        self.assertEqual((body["automations"]["active"], body["automations"]["runs_7d"] >= 1), (1, True))
        self.assertEqual(body["templates"], {"APPROVED": 0, "PENDING": 0, "REJECTED": 0})
        self.assertEqual((body["entry_links"][0]["code"], body["entry_links"][0]["leads_30d"]), ("WEB", 0))
        self.inbound("hi (ref: WEB)", phone="919" + self.phone[3:][::-1] + "7")
        self.assertEqual(self.get(account=self.a)[1]["entry_links"][0]["leads_30d"], 1)
        self.assertIn("wa_not_connected", [a["type"] for a in body["alerts"]])
        self.assertEqual(len(body["needs_reply"]), 1)      # the last message came from the contact

    def test_needs_reply_and_hidden_blocks(self):
        self.inbound("hello")
        body = self.get(account=self.a)[1]
        self.assertEqual(len(body["needs_reply"]), 1)
        self.api("PUT", f"/api/accounts/{self.a}/users/{self.viewer['id']}/overrides",
                 {"overrides": {"crm_dashboard": "view", "inbox": "view"}})
        with db.get_connection() as c:
            for section in ("contacts", "pipeline", "broadcasts"):
                c.execute("INSERT INTO permission_overrides (account_id, user_id, section, level) VALUES (?,?,?,'none')",
                          (self.a, self.viewer["id"], section))
            c.commit()
        body = self.get(self.viewer, account=self.a)[1]
        self.assertEqual((body["pipeline"], body["broadcasts"], body["cards"]["open_deals"]), (None, None, None))
        self.assertEqual(len(body["needs_reply"]), 1)

    def test_other_accounts_stay_out(self):
        self.assertEqual(self.get(new_user("x"), account=self.a)[0], 403)
        self.assertEqual(self.get(new_user("y"))[1]["needs_reply"], None)


if __name__ == "__main__":
    unittest.main()

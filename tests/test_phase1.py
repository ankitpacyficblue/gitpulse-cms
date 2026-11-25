"""Phase 1: knowledge and AI replies, hand-off, 24-hour window, templates, consent, queue, alerts,
entry sources, daily blog. WhatsApp runs in mock mode and the AI call is faked: nothing leaves this machine."""
import json
import os
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

import tests._env  # noqa: F401
from tests.apihelpers import Caller, new_user, new_account, join, setup_db
import crm_store as cs
import database as db
from engine import assistant, jobs, llm, messaging
from engine.whatsapp_client import WhatsAppClient
from server.routes_api import handle_api_request

KNOWLEDGE = {"ai_enabled": True, "business_facts": "We sell farm plots near Mysuru. Visits are on weekends.",
             "faqs": [{"question": "Where are the plots?", "answer": "Near Mysuru, 25 km from the city."}],
             "price_items": [{"text": "Plot price is 45 lakh", "ai_may_quote": False}],
             "banned_claims": ["RERA approved", "guaranteed returns"]}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup_db()

    def setUp(self):
        patch = mock.patch.dict(os.environ, {"WHATSAPP_MOCK": "1"})
        patch.start()
        self.addCleanup(patch.stop)
        self.a, self.b = new_account(), new_account()
        self.owner, self.agent, self.viewer = new_user("o"), new_user("ag"), new_user("v")
        for user, role in ((self.owner, "owner"), (self.agent, "agent"), (self.viewer, "viewer")):
            join(self.a, user, role)
        other = new_user("ob")
        join(self.b, other, "owner")
        self.api, self.api_b = Caller(self.owner, self.a), Caller(other, self.b)
        self.agent_api, self.viewer_api = Caller(self.agent, self.a), Caller(self.viewer, self.a)
        self.phone = "9198" + os.urandom(4).hex().translate(str.maketrans("abcdef", "012345"))
        self.llm_reply = {"reply": "The plots are near Mysuru, 25 km from the city.", "confident": True, "reason": ""}
        self.llm_calls = []

        def fake(account_id, system, turns, timeout=10):
            self.llm_calls.append((account_id, system, turns))
            if isinstance(self.llm_reply, Exception):
                raise self.llm_reply
            return self.llm_reply

        p = mock.patch.object(llm, "generate_json", fake)
        p.start()
        self.addCleanup(p.stop)

    def inbound(self, text="Where are the plots?", wa_id=None, phone=None, account=None, **extra):
        phone = phone or self.phone
        msg = dict({"from": phone, "id": wa_id or "wamid." + os.urandom(6).hex(), "type": "text", "text": {"body": text}}, **extra)
        WhatsAppClient(account or self.a)._process_change({"messages": [msg], "contacts": []})
        return self.contact(phone, account)

    def contact(self, phone=None, account=None):
        return cs.get_contact_by_phone(account or self.a, phone or self.phone)

    def conv(self):
        return cs.get_or_create_conversation(self.a, self.contact()["id"])

    def out(self):
        return [m for m in cs.list_messages(self.a, self.conv()["id"]) if m["direction"] == "outbound"]

    def alerts(self, kind=None):
        _, body = self.api("GET", "/api/alerts")
        return [a for a in body["alerts"] if a["id"] is not None and (kind is None or a["type"] == kind)]

    def close_window(self):
        old = (datetime.utcnow() - timedelta(hours=25)).isoformat()
        with db.get_connection() as c:
            c.execute("UPDATE conversations SET last_inbound_at = ? WHERE id = ?", (old, self.conv()["id"]))
            c.commit()

    def sync_templates(self):
        self.assertEqual(self.api("POST", "/api/whatsapp/templates/sync")[0], 200)


class KnowledgeTests(Base):
    def test_roles_and_isolation(self):
        self.assertEqual(self.api("PUT", "/api/ai/knowledge", KNOWLEDGE)[0], 200)
        self.assertEqual(self.agent_api("PUT", "/api/ai/knowledge", {"tone": "x"})[0], 403)
        self.assertEqual(self.viewer_api("GET", "/api/ai/knowledge")[0], 200)
        _, other = self.api_b("GET", "/api/ai/knowledge")
        self.assertEqual(other["knowledge"]["business_facts"], "")
        self.assertFalse(other["knowledge"]["ai_enabled"])

    def test_bad_shape_is_400(self):
        self.assertEqual(self.api("PUT", "/api/ai/knowledge", {"faqs": "nope"})[0], 400)

    def test_test_box_sends_nothing_and_hidden_price_never_reaches_model(self):
        self.api("PUT", "/api/ai/knowledge", KNOWLEDGE)
        _, out = self.api("POST", "/api/ai/test", {"question": "Where are the plots?"})
        self.assertFalse(out["handoff"])
        self.assertNotIn("45 lakh", self.llm_calls[-1][1])
        self.assertEqual(cs.list_contacts(self.a), [])

    def test_guard(self):
        self.api("PUT", "/api/ai/knowledge", KNOWLEDGE)
        for bad in ("It is RERA approved.", "Guaranteed returns!", "It costs 45 lakh", "Only 12 plots left",
                    "Pay at http://evil.example", "about fifty lakh"):
            self.llm_reply = {"reply": bad, "confident": True}
            self.assertTrue(assistant.answer(self.a, [("customer", "tell me more")])["handoff"], bad)

    def test_price_question_hands_off_unless_quotable(self):
        self.api("PUT", "/api/ai/knowledge", KNOWLEDGE)
        self.assertTrue(assistant.answer(self.a, [("customer", "What is the price?")])["handoff"])
        self.api("PUT", "/api/ai/knowledge", {"price_items": [{"text": "Plot price is 45 lakh", "ai_may_quote": True}]})
        self.llm_reply = {"reply": "The plot price is 45 lakh.", "confident": True}
        self.assertFalse(assistant.answer(self.a, [("customer", "What is the price?")])["handoff"])


class ReplyTests(Base):
    def setUp(self):
        super().setUp()
        self.api("PUT", "/api/ai/knowledge", KNOWLEDGE)

    def test_one_reply_with_disclosure_and_duplicate_delivery_ignored(self):
        self.inbound(wa_id="wamid.same-" + self.a)
        self.inbound(wa_id="wamid.same-" + self.a)
        out = self.out()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["sent_by"], "ai")
        self.assertTrue(out[0]["body"].startswith(assistant.DISCLOSURE))
        self.inbound("And the visit days?")
        self.assertFalse(self.out()[-1]["body"].startswith(assistant.DISCLOSURE))

    def test_ai_off_by_default(self):
        self.inbound(account=self.b)
        conv = cs.list_conversations(self.b)[0]
        self.assertEqual([m["direction"] for m in cs.list_messages(self.b, conv["id"])], ["inbound"])

    def test_handoff_once_then_silent_until_resume(self):
        self.llm_reply = {"reply": "", "confident": False, "reason": "unknown"}
        self.inbound("Do you have a swimming pool?")
        self.inbound("Hello??")
        self.assertEqual(len(self.out()), 1)
        self.assertEqual(self.conv()["needs_human"], 1)
        self.assertEqual(len(self.alerts("handoff")), 1)
        self.llm_reply = {"reply": "Near Mysuru.", "confident": True}
        self.assertEqual(self.viewer_api("POST", f"/api/whatsapp/conversations/{self.conv()['id']}/ai", {"mode": "on"})[0], 403)
        self.assertEqual(self.agent_api("POST", f"/api/whatsapp/conversations/{self.conv()['id']}/ai", {"mode": "on"})[0], 200)
        self.inbound("Where?")
        self.assertEqual(len(self.out()), 2)

    def test_staff_reply_pauses_ai_for_a_day(self):
        self.inbound()
        self.agent_api("POST", f"/api/whatsapp/conversations/{self.conv()['id']}/messages", {"body": "Hi, I am here"})
        before = len(self.out())
        self.inbound("thanks")
        self.assertEqual(len(self.out()), before)
        with db.get_connection() as c:
            c.execute("UPDATE conversations SET ai_paused_at = ? WHERE id = ?", (time.time() - 90000, self.conv()["id"]))
            c.commit()
        self.inbound("Where?")
        self.assertEqual(len(self.out()), before + 1)

    def test_provider_error_hands_off_with_alert_and_no_filler(self):
        self.llm_reply = llm.LLMError("AI provider returned HTTP 500")
        self.inbound()
        self.assertEqual([m["body"] for m in self.out()], [assistant.DEFAULT_HANDOFF])
        self.assertEqual(len(self.alerts("ai_failed")), 1)

    def test_media_hands_off_and_reaction_is_ignored(self):
        self.inbound(type="image")
        self.assertEqual(self.conv()["needs_human"], 1)
        before = len(cs.list_messages(self.a, self.conv()["id"]))
        self.inbound(type="reaction")
        self.assertEqual(len(cs.list_messages(self.a, self.conv()["id"])), before)

    def test_only_this_accounts_knowledge(self):
        self.api_b("PUT", "/api/ai/knowledge", {"ai_enabled": True, "business_facts": "SECRET-OF-B"})
        self.inbound()
        self.assertNotIn("SECRET-OF-B", self.llm_calls[-1][1])


class WindowConsentTests(Base):
    def test_free_text_refused_after_24h_and_nothing_stored(self):
        self.inbound()
        self.close_window()
        cid = self.conv()["id"]
        code, out = self.api("POST", f"/api/whatsapp/conversations/{cid}/messages", {"body": "hello"})
        self.assertEqual((code, out["error"]), (409, "window_closed"))
        self.assertEqual(self.out(), [])
        _, conv = self.api("GET", f"/api/whatsapp/conversations/{cid}")
        self.assertFalse(conv["window_open"])

    def test_template_outside_window_and_marketing_needs_opt_in(self):
        self.inbound()
        self.close_window()
        self.sync_templates()
        url = f"/api/whatsapp/conversations/{self.conv()['id']}/template"
        self.assertEqual(self.api("POST", url, {"name": "mock_approved", "language": "en", "params": ["Pat"]})[0], 200)
        self.assertEqual(self.out()[-1]["body"], "Hello Pat, this is a mock template.")
        self.assertEqual(self.api("POST", url, {"name": "mock_pending", "language": "en", "params": ["P"]})[1]["error"],
                         "template_not_approved")
        self.assertEqual(self.api("POST", url, {"name": "mock_approved", "language": "en", "params": []})[1]["error"],
                         "missing_variables")
        with db.get_connection() as c:
            c.execute("UPDATE wa_templates SET category = 'MARKETING' WHERE account_id = ?", (self.a,))
            c.commit()
        self.assertEqual(self.api("POST", url, {"name": "mock_approved", "language": "en", "params": ["P"]})[1]["error"],
                         "not_opted_in")

    def test_stop_is_exact_confirms_once_and_blocks(self):
        self.api("PUT", "/api/ai/knowledge", dict(KNOWLEDGE, stop_words=["band karo"]))
        self.inbound("please don't stop")
        self.assertEqual(self.contact()["consent_status"], "unknown")
        self.inbound("Stop")
        self.inbound("STOP")
        self.assertEqual(self.contact()["consent_status"], "opted_out")
        self.assertEqual(sum("unsubscribed" in m["body"] for m in self.out()), 1)
        n = len(self.out())
        self.inbound("Where are the plots?")
        self.assertEqual(len(self.out()), n)
        code, out = self.api("POST", f"/api/whatsapp/conversations/{self.conv()['id']}/messages", {"body": "x"})
        self.assertEqual((code, out["error"]), (409, "opted_out"))
        self.assertTrue(messaging.is_stop_message(self.a, "BAND KARO"))

    def test_consent_edit_needs_admin_and_source(self):
        cid = self.inbound()["id"]
        url = f"/api/whatsapp/contacts/{cid}/consent"
        self.assertEqual(self.agent_api("PUT", url, {"status": "opted_in", "source": "form"})[0], 403)
        self.assertEqual(self.api("PUT", url, {"status": "opted_in"})[0], 400)
        self.assertEqual(self.api("PUT", url, {"status": "opted_in", "source": "form"})[0], 200)
        self.assertEqual(self.api_b("PUT", url, {"status": "opted_out"})[0], 404)


class QueueTests(Base):
    def setUp(self):
        super().setUp()
        self.sync_templates()      # mock_approved is a UTILITY template
        self.ids = [cs.create_contact(self.a, f"C{i}", f"+9190000{i}{os.urandom(2).hex()}") for i in range(3)]

    def broadcast(self):
        code, out = self.api("POST", "/api/whatsapp/broadcasts", {"name": "B", "template_name": "mock_approved",
                             "template_language": "en", "template_params": ["{{name}}"], "auto_send": True})
        self.assertEqual(code, 201)
        return out

    def statuses(self):
        with db.get_connection() as c:
            return sorted(r["status"] for r in c.execute("SELECT status FROM messages WHERE account_id = ?", (self.a,)).fetchall())

    def test_broadcast_needs_template(self):
        self.assertEqual(self.api("POST", "/api/whatsapp/broadcasts", {"name": "B", "template_body": "free text"})[0], 400)

    def test_queued_then_sent_once_and_cannot_run_twice(self):
        messaging.set_consent(self.a, self.ids[0], "opted_out", "test")
        out = self.broadcast()
        self.assertEqual((out["stats"]["queued_count"], out["stats"]["skipped"]), (2, {"opted_out": 1}))
        self.assertEqual(self.statuses(), ["queued", "queued"])
        self.assertEqual(self.api("POST", f"/api/whatsapp/broadcasts/{out['id']}/run")[0], 409)
        jobs.tick()
        jobs.tick()
        self.assertEqual(self.statuses(), ["mock", "mock"])
        _, rec = self.api("GET", f"/api/whatsapp/broadcasts/{out['id']}/recipients")
        self.assertEqual(len(rec["recipients"]), 2)
        _, lst = self.api("GET", "/api/whatsapp/broadcasts")
        self.assertEqual((lst["broadcasts"][0]["sent_count"], lst["broadcasts"][0]["status"]), (2, "completed"))

    def test_daily_cap_defers(self):
        self.api("PUT", "/api/ai/knowledge", {"daily_template_cap": 1})
        self.broadcast()
        jobs.tick()
        self.assertEqual(self.statuses(), ["mock", "queued", "queued"])

    def test_retry_three_times_then_failed_with_alert(self):
        fail = {"success": False, "retryable": True, "error": "Meta WhatsApp API HTTP 500"}
        with mock.patch.object(messaging, "_transmit", return_value=fail):
            self.broadcast()
            for _ in range(5):
                with db.get_connection() as c:
                    c.execute("UPDATE jobs SET run_at = 0 WHERE status = 'pending' AND account_id = ?", (self.a,))
                    c.commit()
                jobs.tick()
        self.assertEqual(self.statuses(), ["failed", "failed", "failed"])
        with db.get_connection() as c:
            attempts = {r["attempts"] for r in c.execute("SELECT attempts FROM jobs WHERE account_id = ?", (self.a,)).fetchall()}
        self.assertEqual(attempts, {4})         # first try and three retries
        self.assertTrue(self.alerts("send_failed"))

    def test_consent_rechecked_at_send_time(self):
        self.broadcast()
        messaging.set_consent(self.a, self.ids[0], "opted_out", "test")
        jobs.tick()
        self.assertEqual(self.statuses(), ["failed", "mock", "mock"])

    def test_claimed_job_is_not_run_twice(self):
        job = jobs.enqueue(self.a, "send", {"message_id": 0}, dedupe_key="once-" + self.a)
        self.assertIsNone(jobs.enqueue(self.a, "send", {"message_id": 0}, dedupe_key="once-" + self.a))
        self.assertEqual(jobs.run_job(job), "done")
        self.assertEqual(jobs.run_job(job), "skipped")


class TickAndAlertTests(Base):
    def call(self, headers):
        return handle_api_request("POST", "/api/internal/tick", {}, None, headers=headers)[0]

    def test_tick_needs_secret(self):
        with mock.patch.dict(os.environ, {"CRON_SECRET": ""}):
            self.assertEqual(self.call({"X-Cron-Secret": ""}), 401)
        with mock.patch.dict(os.environ, {"CRON_SECRET": "s3cret-value"}):
            self.assertEqual(self.call({}), 401)
            self.assertEqual(self.call({"X-Cron-Secret": "wrong"}), 401)
            self.assertEqual(self.call({"X-Cron-Secret": "s3cret-value"}), 200)
            self.assertEqual(self.call({"Authorization": "Bearer s3cret-value"}), 200)

    def test_repeats_count_and_resolve_is_scoped(self):
        from engine import alerts
        for _ in range(3):
            alerts.raise_alert(self.a, "send_failed", "boom", link="x")
        rows = self.alerts()
        self.assertEqual((len(rows), rows[0]["count"]), (1, 3))
        self.assertEqual(self.api_b("POST", f"/api/alerts/{rows[0]['id']}/resolve")[0], 404)
        self.assertEqual(self.agent_api("POST", f"/api/alerts/{rows[0]['id']}/resolve")[0], 200)
        self.assertEqual(self.alerts(), [])

    def test_worker_stalled_is_reported_and_setup_note_before_the_secret(self):
        db.set_setting("worker_last_tick", str(time.time() - 400))
        with mock.patch.dict(os.environ, {"CRON_SECRET": "x"}):
            self.assertEqual(self.api("GET", "/api/alerts")[1]["alerts"][0]["type"], "worker_stalled")
        with mock.patch.dict(os.environ, {"CRON_SECRET": ""}):
            body = self.api("GET", "/api/alerts")[1]
        self.assertEqual((body["alerts"][0]["type"], body["alerts"][0]["severity"], body["open"]), ("worker_setup", "info", 0))
        with mock.patch.dict(os.environ, {"CRON_SECRET": "x"}):
            self.assertEqual(handle_api_request("GET", "/api/internal/tick", {}, None,
                                                headers={"Authorization": "Bearer x"})[0], 200)

    def test_normal_requests_drain_the_queue_at_most_once_a_minute(self):
        db.set_setting("worker_last_tick", str(time.time() - 400))
        with mock.patch.dict(os.environ, {"OPPORTUNISTIC_TICK": "1"}), mock.patch.object(jobs, "tick") as tick:
            jobs._checked_at = 0
            self.api("GET", "/api/alerts")
            jobs._checked_at = 0
            db.set_setting("worker_last_tick", str(time.time()))
            self.api("GET", "/api/alerts")
        self.assertEqual(tick.call_count, 1)


class EntryTests(Base):
    def test_ad_code_and_direct_sources(self):
        code, link = self.api("POST", "/api/entry-links", {"label": "Website", "code": "web1"})
        self.assertEqual(code, 201)
        self.assertTrue(link["prefill"].endswith("(ref: WEB1)"))
        a = self.inbound("hi", phone=self.phone + "1", referral={"source_id": "ad9", "headline": "Plots"})
        b = self.inbound("hi (ref: web1)", phone=self.phone + "2")
        c = self.inbound("hi (ref: NOPE)", phone=self.phone + "3")
        self.assertEqual((a["source"], b["source"], c["source"]), ("ad", "WEB1", "direct"))
        self.assertEqual(json.loads(a["source_detail"])["source_id"], "ad9")
        self.assertEqual(self.inbound("again", phone=self.phone + "2", referral={"source_id": "z"})["source"], "WEB1")
        self.assertEqual(self.api_b("DELETE", f"/api/entry-links/{link['id']}")[0], 404)


class BlogPlanTests(Base):
    def setUp(self):
        super().setUp()
        self.writer = self.agent_api
        self.pid = db.create_project({"name": "Site", "github_repo": "x/y", "topic": "farm plots",
                                      "target_framework": "generic"}, self.a)

    def new(self, minutes=-1, api=None, **extra):
        when = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat() + "Z"
        code, out = (api or self.writer)("POST", "/api/blog/plan", dict(
            {"title": "Visiting the plots", "body": "Visits are on weekends.", "publish_at": when, "project_id": self.pid}, **extra))
        self.assertEqual(code, 201, out)
        return out["item"]["id"]

    def step(self, item, action, api=None):
        return (api or self.api)("POST", f"/api/blog/plan/{item}/{action}")

    def item(self, item):
        return next(i for i in self.api("GET", "/api/blog/plan")[1]["items"] if i["id"] == item)

    def publisher(self, success=True):
        res = {"success": success, "pr_url": "https://github.com/x/y/pull/1", "error": "boom"}
        return mock.patch("engine.github_client.GitHubClient.publish_post", return_value=res)

    def test_roles_and_illegal_jumps(self):
        self.assertEqual(self.viewer_api("POST", "/api/blog/plan", {"title": "x"})[0], 403)
        item = self.new()
        self.assertEqual(self.step(item, "approve")[0], 409)                      # draft cannot jump to approved
        self.assertEqual(self.step(item, "submit", self.writer)[0], 200)
        self.assertEqual(self.step(item, "approve", self.writer)[0], 403)         # writers cannot approve
        self.assertEqual(self.step(item, "approve")[0], 200)
        self.assertEqual(self.step(item, "submit")[0], 409)

    def test_scoping(self):
        item = self.new()
        self.assertEqual(self.api_b("PATCH", f"/api/blog/plan/{item}", {"title": "mine"})[0], 404)
        self.assertEqual(self.api_b("GET", "/api/blog/plan")[1]["items"], [])
        self.assertEqual(self.api("POST", "/api/blog/plan", {"title": "t", "assignee_id": 10 ** 9})[0], 404)
        self.assertEqual(self.api_b("POST", "/api/blog/plan", {"title": "t", "project_id": self.pid})[0], 404)

    def test_editing_approved_post_needs_approval_again(self):
        item = self.new(minutes=60)
        self.step(item, "submit"), self.step(item, "approve")
        self.writer("PATCH", f"/api/blog/plan/{item}", {"assignee_id": self.agent["id"]})
        self.assertEqual(self.item(item)["status"], "approved")
        self.writer("PATCH", f"/api/blog/plan/{item}", {"body": "New text"})
        self.assertEqual(self.item(item)["status"], "needs_approval")

    def test_only_due_approved_posts_publish_once(self):
        cs.save_account_settings(self.a, github_token="gh-test-token")
        due, later, unapproved = self.new(), self.new(minutes=600), self.new()
        for item in (due, later):
            self.step(item, "submit"), self.step(item, "approve")
        self.step(unapproved, "submit")
        with self.publisher() as pub:
            jobs.tick(limit=1000)
            jobs.tick(limit=1000)
        self.assertEqual(pub.call_count, 1)
        self.assertIn("Visits are on weekends.", pub.call_args.kwargs["file_content"])
        self.assertEqual([self.item(i)["status"] for i in (due, later, unapproved)], ["published", "approved", "needs_approval"])
        self.assertTrue(self.item(due)["post_url"])
        self.assertEqual(self.writer("PATCH", f"/api/blog/plan/{due}", {"title": "z"})[0], 409)

    def test_failure_and_missing_token_raise_alert_and_do_not_repeat(self):
        item = self.new()
        self.step(item, "submit"), self.step(item, "approve")
        with self.publisher() as pub:
            jobs.tick(limit=1000)
            jobs.tick(limit=1000)
        self.assertEqual(pub.call_count, 0)
        self.assertEqual(self.item(item)["status"], "failed")
        self.assertIn("GitHub token", self.alerts("blog_failed")[0]["message"])

    def test_banned_claim_cannot_be_approved(self):
        self.api("PUT", "/api/ai/knowledge", {"banned_claims": ["guaranteed returns"]})
        item = self.new(body="Guaranteed returns for all.")
        self.step(item, "submit")
        self.assertEqual(self.step(item, "approve")[1]["error"], "blocked")

    def test_empty_item_is_drafted_then_waits_for_approval(self):
        item = self.new(body="")
        article = {"content_markdown": "## Visits\nCome on a weekend."}
        with mock.patch("engine.ai_generator.AIGenerator.generate_article", return_value=article), self.publisher() as pub:
            jobs.tick(limit=1000)
        self.assertEqual(self.item(item)["status"], "needs_approval")
        self.assertEqual(pub.call_count, 0)

    def test_ai_failure_leaves_the_draft_empty_with_alert(self):
        item = self.new(body="")
        db.set_setting("ai_provider", "gemini")
        with mock.patch("config.DEFAULT_GEMINI_API_KEY", ""):
            self.assertEqual(self.step(item, "draft")[0], 502)
            jobs.tick(limit=1000)
        self.assertEqual((self.item(item)["status"], self.item(item)["body"]), ("draft", ""))
        self.assertEqual(len(self.alerts("blog_failed")), 1)

    def test_nothing_planned_means_nothing_published(self):
        with self.publisher() as pub:
            jobs.tick(limit=1000)
        self.assertEqual((pub.call_count, db.list_posts_for_account(self.a, limit=5)), (0, []))


if __name__ == "__main__":
    unittest.main()

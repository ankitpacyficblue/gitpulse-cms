"""Phase 1: knowledge and AI replies, hand-off, 24-hour window, templates, consent, queue, alerts,
entry sources, daily blog. WhatsApp runs in mock mode and the AI call is faked: nothing leaves this machine."""
import json
import os
import time
import unittest
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

import tests._env  # noqa: F401
from tests.apihelpers import Caller, new_user, new_account, join, setup_db
import crm_store as cs
import database as db
from engine import assistant, blog_plan, jobs, llm, media, messaging, writer_tokens
from engine.whatsapp_client import WhatsAppClient
from database import normalize_repo
from engine.github_client import GitHubClient
from server.routes_api import handle_api_request
from server.routes_public import handle_public_request

KNOWLEDGE = {"ai_enabled": True, "business_facts": "We sell farm plots near Mysuru. Visits are on weekends.",
             "faqs": [{"question": "Where are the plots?", "answer": "Near Mysuru, 25 km from the city."}],
             "price_items": [{"text": "Plot price is 45 lakh", "ai_may_quote": False}],
             "banned_claims": ["RERA approved", "guaranteed returns"]}


def without_cover_rule(test):
    """For tests about something else; CoverRequiredTests covers the rule itself."""
    patch = mock.patch.object(blog_plan, "require_cover", lambda row: None)
    patch.start()
    test.addCleanup(patch.stop)


def git_publishing(test):
    """The older path: publishing commits to the website repository."""
    patch = mock.patch.dict(os.environ, {"PUBLISH_VIA_GIT": "1"})
    patch.start()
    test.addCleanup(patch.stop)


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
        self.assertEqual([m["body"] for m in self.out()], [f"{assistant.DISCLOSURE}\n\n{assistant.DEFAULT_HANDOFF}"])
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
        db.set_setting("worker_last_tick", str(time.time() - 7 * 3600))
        with mock.patch.dict(os.environ, {"CRON_SECRET": "x"}):
            self.assertEqual(self.api("GET", "/api/alerts")[1]["alerts"][0]["type"], "worker_stalled")
        with mock.patch.dict(os.environ, {"CRON_SECRET": ""}):
            body = self.api("GET", "/api/alerts")[1]
        self.assertEqual((body["alerts"][0]["type"], body["alerts"][0]["severity"], body["open"]), ("worker_setup", "info", 0))
        with mock.patch.dict(os.environ, {"CRON_SECRET": "x"}):
            self.assertEqual(handle_api_request("GET", "/api/internal/tick", {}, None,
                                                headers={"Authorization": "Bearer x"})[0], 200)

    def test_normal_requests_drain_the_queue_at_most_once_a_minute(self):
        db.set_setting("worker_last_tick", str(time.time() - 7 * 3600))
        with mock.patch.dict(os.environ, {"OPPORTUNISTIC_TICK": "1"}), mock.patch.object(jobs, "tick") as tick:
            jobs._checked_at = 0
            self.api("GET", "/api/alerts")
            jobs._checked_at = 0
            db.set_setting("worker_last_tick", str(time.time()))
            self.api("GET", "/api/alerts")
        self.assertEqual(tick.call_count, 1)


class UatTests(Base):
    def test_a_first_message_that_hands_off_still_says_it_is_automated(self):
        self.api("PUT", "/api/ai/knowledge", {"ai_enabled": True, "business_name": "Villa"})
        self.llm_reply = {"reply": "", "confident": False, "reason": "unsure"}
        self.inbound("Can I speak to someone?")
        self.assertIn(assistant.DISCLOSURE, self.out()[-1]["body"])

    def test_broadcast_preview_counts_who_is_skipped_and_sends_nothing(self):
        self.sync_templates()
        cs.create_contact(self.a, "A", "+" + self.phone + "1")
        out = cs.create_contact(self.a, "B", "+" + self.phone + "2")
        messaging.set_consent(self.a, out, "opted_out", "test")
        code, res = self.api("POST", "/api/whatsapp/broadcasts/preview",
                             {"template_name": "mock_approved", "template_language": "en"})
        self.assertEqual((code, res["audience"], res["will_send"], res["skipped"]), (200, 2, 1, {"opted_out": 1}))
        self.assertEqual(cs.list_messages(self.a, cs.get_or_create_conversation(self.a, out)["id"]), [])


class RepoNameTests(Base):
    def test_a_pasted_address_is_saved_and_used_as_owner_repo(self):
        for given in ("https://github.com/o/site.git/", "github.com/o/site", "git@github.com:o/site.git", " o/site/ ",
                      "https://github.com/o/site/tree/main"):
            self.assertEqual(normalize_repo(given), "o/site", given)
        pid = db.create_project({"name": "S", "github_repo": "https://github.com/o/site", "topic": "t",
                                 "target_framework": "generic"}, self.a)
        self.assertEqual(db.get_project(pid)["github_repo"], "o/site")
        db.update_project(pid, {"github_repo": "https://github.com/o/other.git"}, self.a)
        self.assertEqual(db.get_project(pid)["github_repo"], "o/other")
        missing = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=missing):
            ok, message = GitHubClient("t").test_connection("o/other")
        self.assertEqual((ok, "repo not found or token has no access" in message), (False, True))


class EntryTests(Base):
    def link(self, **extra):
        return self.api("POST", "/api/entry-links", dict({"label": "Website", "code": "web1"}, **extra))

    def test_no_number_no_link(self):
        code, out = self.link()
        self.assertEqual((code, out["error"]), (409, "no_number"))

    def test_first_touch_source_and_campaign_are_kept(self):
        cs.save_whatsapp_account(self.a, phone_number="+91 98000 00000")
        code, link = self.link(source="social", campaign="diwali")
        self.assertEqual(code, 201, link)
        self.assertTrue(link["url"].startswith("https://wa.me/919800000000?text="))
        self.assertTrue(link["prefill"].endswith("(ref: WEB1)"))
        ad = self.inbound("hi", phone=self.phone + "1", referral={"source_id": "ad9", "headline": "Plots"})
        social = self.inbound("hi (ref: web1)", phone=self.phone + "2")
        direct = self.inbound("hi (ref: NOPE)", phone=self.phone + "3")
        self.assertEqual((ad["source"], social["source"], social["campaign"], direct["source"]),
                         ("ad", "social", "diwali", "direct"))
        self.assertEqual(json.loads(ad["source_detail"])["source_id"], "ad9")
        again = self.inbound("again", phone=self.phone + "2", referral={"source_id": "z"})
        self.assertEqual((again["source"], again["campaign"]), ("social", "diwali"))
        manual = self.phone + "4"
        cs.create_contact(self.a, "Typed in", "+" + manual)
        self.assertEqual(self.inbound("hi (ref: WEB1)", phone=manual)["source"], "social")
        self.assertEqual(self.api("GET", "/api/entry-links")[1]["links"][0]["enquiries"], 2)
        self.assertEqual(self.api_b("DELETE", f"/api/entry-links/{link['id']}")[0], 404)


class CustomFieldTests(Base):
    def field(self, name, kind, **extra):
        code, out = self.api("POST", "/api/contact-fields", dict({"name": name, "type": kind}, **extra))
        self.assertEqual(code, 201, out)
        return str(out["field"]["id"])

    def contacts(self, **query):
        return self.api("GET", "/api/whatsapp/contacts", query=query)

    def add(self, custom):
        return self.agent_api("POST", "/api/whatsapp/contacts",
                              {"name": "C", "phone": "+9198" + str(int.from_bytes(os.urandom(4), "big"))[:8], "custom": custom})

    def test_define_validate_filter_and_archive(self):
        self.assertEqual(self.agent_api("POST", "/api/contact-fields", {"name": "x", "type": "text"})[0], 403)
        city, budget = self.field("City", "text"), self.field("Budget", "number")
        when, phase = self.field("Visit", "date"), self.field("Phase", "select", options=["1", "2"])
        self.assertEqual(self.api("POST", "/api/contact-fields", {"name": "city", "type": "text"})[0], 409)
        for bad in ({budget: "lots"}, {when: "tomorrow"}, {phase: "3"}):
            self.assertEqual(self.add(bad)[0], 400, bad)
        self.assertEqual(self.contacts()[1]["contacts"], [])                      # nothing saved by a bad request
        self.assertEqual(self.add({city: "Mysuru", budget: "50", phase: "1", when: "2026-12-05"})[0], 201)
        self.assertEqual(self.add({city: "Pune", budget: 20})[0], 201)
        names = lambda **q: len(self.contacts(**q)[1]["contacts"])
        self.assertEqual(names(**{"cf_" + budget + "_min": "30"}), 1)
        self.assertEqual(names(**{"cf_" + city: "mys", "cf_" + phase: "1"}), 1)
        self.assertEqual(names(**{"cf_" + when + "_max": "2026-12-01"}), 0)
        self.assertEqual(self.api("PATCH", f"/api/contact-fields/{budget}", {"type": "text"})[0], 409)
        cid = self.contacts(**{"cf_" + city: "pune"})[1]["contacts"][0]["id"]
        self.assertEqual(self.agent_api("PUT", f"/api/whatsapp/contacts/{cid}", {"custom": {city: ""}})[0], 200)
        self.assertEqual(names(**{"cf_" + city: "pune"}), 0)
        self.assertEqual(self.api("DELETE", f"/api/contact-fields/{city}")[0], 200)
        self.assertTrue(all(city not in c["custom"] for c in self.contacts()[1]["contacts"]))
        self.assertEqual(self.add({city: "x"})[0], 404)

    def test_other_account_cannot_use_a_field(self):
        mine = self.field("City", "text")
        self.assertEqual(self.api_b("GET", "/api/contact-fields")[1]["fields"], [])
        self.assertEqual(self.api_b("GET", "/api/whatsapp/contacts", query={"cf_" + mine: "x"})[0], 404)
        self.assertEqual(self.api_b("DELETE", f"/api/contact-fields/{mine}")[0], 404)


class BlogPlanTests(Base):
    def setUp(self):
        super().setUp()
        without_cover_rule(self)
        git_publishing(self)
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


class PublishNowTests(Base):
    def setUp(self):
        super().setUp()
        without_cover_rule(self)
        git_publishing(self)

    def post_waiting(self, status="approved"):
        pid = db.create_project({"name": "S", "github_repo": "x/y", "topic": "t", "target_framework": "generic", "github_token": "tok"}, self.a)
        later = (datetime.utcnow() + timedelta(5)).isoformat() + "Z"
        item = self.api("POST", "/api/blog/plan", {"title": "T", "body": "B", "project_id": pid, "publish_at": later})[1]["item"]
        self.api("POST", f"/api/blog/plan/{item['id']}/submit")
        if status == "approved":
            self.assertEqual(self.api("POST", f"/api/blog/plan/{item['id']}/approve")[0], 200)
        return item["id"]

    def publisher(self, **res):
        return mock.patch("engine.github_client.GitHubClient.publish_post", return_value=res)

    def test_publishes_once_and_only_for_a_publisher(self):
        item = self.post_waiting()
        url = f"/api/blog/plan/{item}/publish-now"
        with self.publisher(success=True, pr_url="u") as publish:
            self.assertEqual(self.agent_api("POST", url)[0], 403)
            code, out = self.api("POST", url)
            self.assertEqual((code, out["item"]["status"], out["item"]["post_url"]), (200, "published", "u"), out)
            self.assertEqual(self.api("POST", url)[1]["error"], "wrong_status")
            blog_plan.schedule_due()
            jobs.tick()
        self.assertEqual(publish.call_count, 1)

    def test_refuses_unapproved_and_reports_a_failure(self):
        waiting = self.post_waiting(status="needs_approval")
        self.assertEqual(self.api("POST", f"/api/blog/plan/{waiting}/publish-now")[1]["error"], "wrong_status")
        item = self.post_waiting()
        with self.publisher(success=False, error="no access"):
            code, out = self.api("POST", f"/api/blog/plan/{item}/publish-now")
        self.assertEqual((code, out["error"]), (502, "publish_failed"), out)
        self.assertIn("no access", out["message"])


class CoverRequiredTests(Base):
    COVER = '[{"media_id": 1, "alt": "", "cover": true}]'

    def setUp(self):
        super().setUp()
        patch = mock.patch.object(blog_plan, "_post_files", lambda account_id, row: [])      # no file storage here
        patch.start()
        self.addCleanup(patch.stop)
        self.pid = db.create_project({"name": "S", "github_repo": "x/y", "topic": "t", "target_framework": "generic",
                                      "github_token": "tok"}, self.a)

    def put(self, item, **values):
        with db.get_connection() as c:
            for key, value in values.items():
                c.execute(f"UPDATE blog_plan SET {key} = ? WHERE id = ?", (value, item))
            c.commit()

    def test_submit_approve_and_publish_need_a_cover(self):
        when = (datetime.utcnow() - timedelta(minutes=1)).isoformat() + "Z"
        item = self.api("POST", "/api/blog/plan", {"title": "T", "body": "B", "project_id": self.pid,
                                                  "publish_at": when})[1]["item"]["id"]
        step = lambda action: self.api("POST", f"/api/blog/plan/{item}/{action}")
        self.assertEqual(step("submit")[1]["error"], "cover_required")
        self.put(item, status="needs_approval")
        self.assertEqual(step("approve")[1]["error"], "cover_required")
        self.put(item, status="approved")                                   # approved before the rule
        self.assertEqual(step("publish-now")[1]["error"], "cover_required")
        with mock.patch("engine.github_client.GitHubClient.publish_post") as publish:
            blog_plan.schedule_due()
            jobs.tick()
        publish.assert_not_called()
        stored = self.api("GET", "/api/blog/plan")[1]["items"][0]
        self.assertEqual(stored["status"], "failed")
        self.assertIn("cover image", stored["error"])
        self.put(item, images=self.COVER)
        self.assertEqual([step("submit")[0], step("approve")[0]], [200, 200])

    def test_writer_cannot_hand_in_without_a_cover(self):
        code, out = self.api("POST", "/api/writer-tokens", {"name": "Toby"})
        header = {"Authorization": "Bearer " + out["token"]}
        for images in ([], None):
            code, body = handle_api_request("POST", "/api/writer/posts", {}, {"title": "T", "body": "B", "images": images},
                                            headers=header)
            self.assertEqual((code, body["error"]), (409, "cover_required"), body)
            self.assertIn("cover", body["message"])
        self.assertEqual(self.api("GET", "/api/blog/plan")[1]["items"], [])


class LivePublishTests(Base):
    """The default: GitPulse is the source of posts and nothing is committed."""
    COVER = {"url": "https://cms.example.com/api/public/media/abc", "alt": "Title card"}

    def setUp(self):
        super().setUp()
        without_cover_rule(self)
        for target, name, fake in (
            (blog_plan, "_post_files", lambda account_id, row: []),
            (blog_plan, "_cover", lambda account_id, row: self.COVER),
        ):
            patch = mock.patch.object(target, name, fake)
            patch.start()
            self.addCleanup(patch.stop)
        self.pid = db.create_project({"name": "S", "github_repo": "x/y", "topic": "t", "target_framework": "generic"}, self.a)
        git = mock.patch("engine.github_client.GitHubClient.publish_post", side_effect=AssertionError("committed"))
        self.git = git.start()
        self.addCleanup(git.stop)

    def publish(self):
        later = (datetime.utcnow() + timedelta(5)).isoformat() + "Z"
        item = self.api("POST", "/api/blog/plan", {"title": "Hill plots", "body": "Visits are on weekends.",
                        "meta_description": "What to check.", "project_id": self.pid, "publish_at": later})[1]["item"]["id"]
        self.api("POST", f"/api/blog/plan/{item}/submit")
        self.api("POST", f"/api/blog/plan/{item}/approve")
        return self.api("POST", f"/api/blog/plan/{item}/publish-now")

    def public(self, tail=""):
        code, _, body = handle_public_request(f"/api/public/projects/{self.pid}/posts{tail}", {})
        return code, json.loads(body)

    def test_publishes_without_a_commit_or_any_setup(self):
        self.assertEqual(self.public()[1]["posts"], [])
        with mock.patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://cms.example.com"}), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("called out")):
            code, out = self.publish()                     # no GitHub token, no website settings
        view = f"https://cms.example.com/api/public/projects/{self.pid}/posts/hill-plots/view"
        self.assertEqual((code, out["item"]["status"], out["item"]["post_url"]), (200, "published", view), out)
        self.git.assert_not_called()
        listed = self.public()[1]["posts"][0]
        self.assertEqual((listed["slug"], listed["cover_image"], listed["seo"]),
                         ("hill-plots", self.COVER, {"title": "Hill plots", "description": "What to check."}))
        code, post = self.public("/hill-plots")
        self.assertEqual((code, post["content_markdown"], post["body_format"]), (200, "Visits are on weekends.", "markdown"))
        self.assertEqual(self.public("/missing")[0], 404)

    def test_embed_script_and_readable_page(self):
        self.publish()
        code, ctype, script = handle_public_request(f"/api/public/projects/{self.pid}/embed.js", {})
        self.assertEqual((code, ctype.split(";")[0]), (200, "application/javascript"))
        self.assertNotIn("innerHTML", script)
        code, ctype, page = handle_public_request(f"/api/public/projects/{self.pid}/posts/hill-plots/view", {})
        self.assertEqual((code, ctype.split(";")[0]), (200, "text/html"))
        self.assertIn("<title>Hill plots</title>", page)
        self.assertIn('data-post="hill-plots"', page)
        self.assertEqual(handle_public_request(f"/api/public/projects/{self.pid}/posts/missing/view", {})[0], 404)


class MediaTests(Base):
    PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 8
    PDF = b"%PDF-1.7 " + b"0" * 7

    def setUp(self):
        super().setUp()
        without_cover_rule(self)
        git_publishing(self)
        env = mock.patch.dict(os.environ, {"MEDIA_SUPABASE_URL": "https://store.test", "MEDIA_SUPABASE_KEY": "k",
                                           "MEDIA_BUCKET": "b"})
        env.start()
        self.addCleanup(env.stop)
        self.stored, self.next_upload = {}, None
        for name, fake in (
            ("storage_sign_upload", lambda path: self._arrive(path)),
            ("storage_sign", lambda paths, seconds: {p: "https://store.test/s/" + p for p in paths}),
            ("storage_head", lambda path: (len(self.stored[path]), self.stored[path][:16]) if path in self.stored else None),
            ("storage_remove", lambda paths: [self.stored.pop(p, None) for p in paths]),
            ("storage_put", lambda path, content, mime: self.stored.__setitem__(path, content)),
        ):
            p = mock.patch.object(media, name, fake)
            p.start()
            self.addCleanup(p.stop)

    def _arrive(self, path):
        if self.next_upload is not None:
            self.stored[path] = self.next_upload
        return "https://store.test/up/" + path

    def upload(self, content=PNG, mime="image/png", name="plot.png", size=None):
        self.next_upload = content
        code, out = self.agent_api("POST", "/api/media/upload-url", {"name": name, "mime": mime, "size": size or 16})
        if code != 201:
            return code, out
        return self.agent_api("POST", "/api/media", {"media_id": out["media_id"]})

    def test_checks_isolation_and_delete(self):
        self.assertEqual(self.upload(mime="image/gif")[1]["error"], "type_not_allowed")
        self.assertEqual(self.upload(size=6 * 1024 * 1024)[1]["error"], "too_large")
        code, out = self.upload(content=self.PDF)                       # claims PNG, is a PDF
        self.assertEqual((code, out["error"], self.stored), (400, "file_rejected", {}))
        self.assertEqual(self.upload(content=None)[1]["error"], "not_uploaded")
        code, out = self.upload()
        self.assertEqual(code, 201, out)
        item = out["item"]["id"]
        self.assertEqual([i["id"] for i in self.viewer_api("GET", "/api/media")[1]["items"]], [item])
        self.assertEqual(self.viewer_api("POST", "/api/media/upload-url", {})[0], 403)
        self.assertEqual(self.api_b("GET", "/api/media")[1]["items"], [])
        self.assertEqual(self.api_b("DELETE", f"/api/media/{item}")[0], 404)
        self.assertEqual(self.agent_api("DELETE", f"/api/media/{item}")[0], 403)
        self.assertEqual(self.api("DELETE", f"/api/media/{item}")[0], 200)
        self.assertEqual(self.stored, {})

    def test_off_without_settings(self):
        with mock.patch.dict(os.environ, {"MEDIA_BUCKET": ""}):
            self.assertEqual(self.api("GET", "/api/media")[1], {"configured": False, "items": []})
            self.assertEqual(self.api("POST", "/api/media/upload-url", {})[0], 503)

    def test_chat_send_window_and_in_use(self):
        pdf = self.upload(content=self.PDF, mime="application/pdf", name="brochure.pdf")[1]["item"]["id"]
        webp = self.upload(content=b"RIFF0000WEBP0000", mime="image/webp", name="a.webp")[1]["item"]["id"]
        self.inbound("Send the brochure")
        url = f"/api/whatsapp/conversations/{self.conv()['id']}/messages"
        self.assertEqual(self.api("POST", url, {"media_id": webp})[1]["error"], "unsupported_on_whatsapp")
        code, out = self.api("POST", url, {"media_id": pdf})
        self.assertEqual(code, 200, out)
        sent = [m for m in self.api("GET", url)[1]["messages"] if m.get("media")]
        self.assertEqual((sent[0]["message_type"], sent[0]["media"]["name"]), ("document", "brochure.pdf"))
        self.assertEqual(self.api("DELETE", f"/api/media/{pdf}")[1]["error"], "in_use")
        self.assertEqual(self.api("DELETE", f"/api/media/{pdf}", query={"force": "1"})[0], 200)
        self.close_window()
        self.assertEqual(self.api("POST", url, {"media_id": webp, "body": "x"})[0], 409)

    def test_link_is_public_only_after_the_post_is_published(self):
        out = self.upload()[1]["item"]
        token = out["blog_url"].rsplit("/", 1)[1]
        self.assertEqual(handle_public_request(f"/api/public/media/{token}", {})[0], 404)
        pid = db.create_project({"name": "S", "github_repo": "x/y", "topic": "t", "target_framework": "generic"}, self.a)
        cs.save_account_settings(self.a, github_token="t")
        when = (datetime.utcnow() - timedelta(1)).isoformat() + "Z"
        item = self.api("POST", "/api/blog/plan", {"title": "T", "body": f"![plot]({out['blog_url']})",
                                                   "publish_at": when, "project_id": pid})[1]["item"]["id"]
        self.api("POST", f"/api/blog/plan/{item}/submit")
        self.api("POST", f"/api/blog/plan/{item}/approve")
        self.assertEqual(handle_public_request(f"/api/public/media/{token}", {})[0], 404)
        with mock.patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://cms.test"}), \
                mock.patch("engine.github_client.GitHubClient.publish_post", return_value={"success": True, "pr_url": "u"}):
            jobs.tick(limit=1000)
        code, _, link = handle_public_request(f"/api/public/media/{token}", {})
        self.assertEqual(code, 302)
        self.assertTrue(link.startswith("https://store.test/s/"))
        self.assertEqual(self.api("GET", "/api/media")[1]["items"][0]["used_by"], ["blog"])

    def post(self, **extra):
        pid = db.create_project({"name": "S", "github_repo": "x/y", "topic": "t", "target_framework": "generic"}, self.a)
        cs.save_account_settings(self.a, github_token="t")
        when = (datetime.utcnow() - timedelta(1)).isoformat() + "Z"
        return self.agent_api("POST", "/api/blog/plan", dict({"title": "Plots", "body": "Visit on weekends.",
                                                            "publish_at": when, "project_id": pid}, **extra))

    def publisher(self):
        return mock.patch("engine.github_client.GitHubClient.publish_post", return_value={"success": True, "pr_url": "u"})

    def test_agent_writes_with_images_admin_rejects_then_approves(self):
        cover, inline = (self.upload(name=n)[1]["item"]["id"] for n in ("cover.png", "inline.png"))
        pdf = self.upload(content=self.PDF, mime="application/pdf", name="a.pdf")[1]["item"]["id"]
        self.assertEqual(self.post(images=[{"media_id": pdf}])[1]["error"], "not_an_image")
        self.assertEqual(self.api_b("POST", "/api/blog/plan", {"title": "x", "images": [{"media_id": cover}]})[0], 404)
        code, out = self.post(images=[{"media_id": cover, "cover": True, "alt": "Gate"}, {"media_id": inline, "alt": "Road"}])
        self.assertEqual(code, 201, out)
        item = out["item"]["id"]
        saved = self.agent_api("GET", "/api/blog/plan")[1]["items"][0]["images"]
        self.assertEqual([(i["media_id"], i["cover"], bool(i["url"])) for i in saved], [(cover, True, True), (inline, False, True)])
        url = f"/api/blog/plan/{item}"
        with self.publisher() as pub:
            jobs.tick(limit=1000)                                             # draft: never
            self.assertEqual(self.agent_api("POST", url + "/submit")[0], 200)
            jobs.tick(limit=1000)                                             # waiting for approval: never
            self.assertEqual(self.api("DELETE", f"/api/media/{inline}", query={"force": "1"})[1]["error"], "in_use_by_post")
            self.assertEqual(self.agent_api("POST", url + "/reject", {"note": "n"})[0], 403)
            self.assertEqual(self.api("POST", url + "/reject", {"note": " "})[1]["error"], "note_required")
            rejected = self.api("POST", url + "/reject", {"note": "Use a better photo"})[1]["item"]
            self.assertEqual((rejected["status"], rejected["rejected_note"]), ("draft", "Use a better photo"))
            jobs.tick(limit=1000)                                             # rejected: never
            self.assertEqual(pub.call_count, 0)
        self.assertIsNone(self.agent_api("POST", url + "/submit")[1]["item"]["rejected_note"])
        self.assertEqual(self.api("POST", url + "/approve")[0], 200)
        changed = self.agent_api("PATCH", url, {"images": [{"media_id": cover, "cover": True, "alt": "Main gate"},
                                                          {"media_id": inline}]})[1]["item"]
        self.assertEqual(changed["status"], "needs_approval")
        self.api("POST", url + "/approve")
        with mock.patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://cms.test"}), self.publisher() as pub:
            jobs.tick(limit=1000)
        sent = pub.call_args.kwargs["file_content"]
        self.assertLess(sent.index("![Main gate](https://cms.test/api/public/media/"), sent.rindex("Visit on weekends."))
        self.assertEqual(sent.count("/api/public/media/"), 2)
        token = sent.split("/api/public/media/")[2].split(")")[0]
        self.assertEqual(handle_public_request(f"/api/public/media/{token}", {})[0], 302)

    def test_relative_media_links_are_published_with_the_full_address(self):
        out = self.upload()[1]["item"]
        path = "/api/public/media/" + out["blog_url"].rsplit("/", 1)[1]
        item = self.post(body=f"![x]({path}) and ![y](https://cms.test{path})")[1]["item"]["id"]
        self.agent_api("POST", f"/api/blog/plan/{item}/submit")
        self.api("POST", f"/api/blog/plan/{item}/approve")
        with mock.patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://cms.test"}), self.publisher() as pub:
            jobs.tick(limit=1000)
        self.assertIn(f"![x](https://cms.test{path}) and ![y](https://cms.test{path})", pub.call_args.kwargs["file_content"])

    def test_a_missing_image_stops_the_whole_post(self):
        image = self.upload()[1]["item"]["id"]
        item = self.post(images=[{"media_id": image}])[1]["item"]["id"]
        self.agent_api("POST", f"/api/blog/plan/{item}/submit")
        with mock.patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://cms.test"}):
            self.assertEqual(self.api("POST", f"/api/blog/plan/{item}/approve")[0], 200)
            self.stored.clear()
            with self.publisher() as pub:
                jobs.tick(limit=1000)
        self.assertEqual(pub.call_count, 0)
        self.assertEqual(len(self.alerts("blog_failed")), 1)

    def writer(self, name="Toby", account_api=None):
        code, out = (account_api or self.api)("POST", "/api/writer-tokens", {"name": name})
        self.assertEqual(code, 201, out)
        header = {"Authorization": "Bearer " + out["token"]}
        return out, lambda method, path, body=None: handle_api_request(method, path, {}, body or {}, headers=header)

    @mock.patch.object(blog_plan, "has_cover", lambda images: True)
    def test_writer_meta_description_and_project(self):
        pid = db.create_project({"name": "Villa", "github_repo": "x/y", "topic": "t", "target_framework": "generic"}, self.a)
        _, writer = self.writer()
        code, out = writer("POST", "/api/writer/posts", {"title": "T", "body": "B", "meta_description": "  A short\n\\summary  "})
        self.assertEqual((code, out["item"]["meta_description"], out["item"]["project"]),
                         (201, "A short summary", {"id": pid, "name": "Villa"}), out)
        item = writer("GET", f"/api/writer/posts/{out['item']['id']}")[1]["item"]
        self.assertEqual((item["meta_description"], item["project"]["id"]), ("A short summary", pid))
        bad = writer("POST", "/api/writer/posts", {"title": "T", "body": "B", "meta_description": "<b>x</b>"})
        self.assertEqual(bad[1]["error"], "html_not_allowed")

    def test_writer_token_submits_for_review_and_can_do_nothing_else(self):
        pid = db.create_project({"name": "S", "github_repo": "x/y", "topic": "t", "target_framework": "generic"}, self.a)
        self.assertEqual(self.agent_api("POST", "/api/writer-tokens", {"name": "x"})[0], 403)
        token, writer = self.writer()
        self.assertTrue(token["token"].startswith("gpw_"))
        listed = self.api("GET", "/api/writer-tokens")[1]["tokens"]
        self.assertNotIn(token["token"], json.dumps(listed))
        self.assertEqual(self.api("GET", "/api/writer/posts")[0], 401)          # a session is not a writer token
        pdf = writer("POST", "/api/writer/media/upload-url", {"name": "a.pdf", "mime": "application/pdf", "size": 9})
        self.assertEqual(pdf[1]["error"], "type_not_allowed")
        self.next_upload = self.PNG
        up = writer("POST", "/api/writer/media/upload-url", {"name": "a.png", "mime": "image/png", "size": 16})[1]
        got = writer("POST", "/api/writer/media", {"media_id": up["media_id"]})[1]
        draft = {"title": "Plots", "body": f"Hi ![a]({got['markdown_url']})", "images": [{"media_id": up["media_id"], "cover": True}],
                 "publish_at": (datetime.utcnow() - timedelta(1)).isoformat() + "Z", "status": "approved", "external_id": "e1"}
        staff_image = self.upload()[1]["item"]["id"]
        self.assertEqual(writer("POST", "/api/writer/posts", dict(draft, images=[{"media_id": staff_image}], external_id="e2"))[0], 404)
        self.assertEqual(writer("POST", "/api/writer/posts", dict(draft, body="<img src=x onerror=a>", external_id="e3"))[1]["error"],
                         "html_not_allowed")
        code, out = writer("POST", "/api/writer/posts", draft)
        self.assertEqual((code, out["item"]["state"]), (201, "draft"), out)
        item = out["item"]["id"]
        again = writer("POST", "/api/writer/posts", draft)
        self.assertEqual((again[0], again[1]["item"]["id"], again[1]["created"]), (200, item, False))
        self.assertEqual(writer("POST", f"/api/writer/posts/{item}/submit")[1]["item"]["state"], "in_review")
        for path in (f"/api/blog/plan/{item}/approve", "/api/blog/plan", "/api/media", "/api/whatsapp/contacts",
                     "/api/internal/tick"):
            self.assertEqual(writer("POST", path)[0], 401, path)
        other = self.writer("Other", self.api_b)[1]
        self.assertEqual((other("GET", "/api/writer/posts")[1]["items"], other("GET", f"/api/writer/posts/{item}")[0]), ([], 404))
        self.api("POST", f"/api/blog/plan/{item}/reject", {"note": "Shorter"})
        self.assertEqual(writer("GET", f"/api/writer/posts/{item}")[1]["item"]["rejected_note"], "Shorter")
        self.assertEqual(writer("PATCH", f"/api/writer/posts/{item}", {"body": "Short."})[1]["item"]["state"], "rejected")
        self.assertEqual(writer("POST", f"/api/writer/posts/{item}/submit")[1]["item"]["state"], "in_review")
        row = self.api("GET", "/api/blog/plan")[1]
        self.assertEqual((row["items"][0]["writer"], row["items"][0]["project_id"], row["tick_hours"]), ("Toby", pid, 3))
        cs.save_account_settings(self.a, github_token="t")
        with mock.patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://cms.test"}):
            self.assertEqual(self.api("POST", f"/api/blog/plan/{item}/approve")[0], 200)
            self.assertEqual(writer("PATCH", f"/api/writer/posts/{item}", {"body": "Changed."})[1]["error"], "wrong_status")
            with self.publisher() as pub:
                jobs.tick(limit=1000)
        self.assertEqual(pub.call_args.kwargs["mode"], "direct")
        done = self.api("GET", "/api/blog/plan")[1]["items"][0]
        self.assertEqual((done["state"], bool(done["published_at"])), ("published", True))
        self.assertEqual(self.api("DELETE", f"/api/writer-tokens/{token['item']['id']}")[0], 200)
        self.assertEqual(writer("GET", "/api/writer/posts")[0], 401)

    def test_a_planned_slot_can_be_given_to_a_writer_and_requests_are_limited(self):
        token, writer = self.writer()
        slot = self.agent_api("POST", "/api/blog/plan", {"title": "Slot"})[1]["item"]["id"]
        tid = token["item"]["id"]
        self.assertEqual(self.agent_api("PATCH", f"/api/blog/plan/{slot}", {"writer_token_id": tid})[0], 403)
        self.assertEqual(self.api("PATCH", f"/api/blog/plan/{slot}", {"writer_token_id": tid})[0], 200)
        self.assertEqual(writer("PATCH", f"/api/writer/posts/{slot}", {"body": "Text."})[0], 200)
        with mock.patch.object(writer_tokens, "MAX_PER_HOUR", 2):
            self.assertEqual([writer("GET", "/api/writer/posts")[0] for _ in range(2)], [200, 429])

    def test_template_header_and_incoming_file(self):
        image = self.upload()[1]["item"]["id"]
        self.inbound("hello")
        self.sync_templates()
        with db.get_connection() as c:
            c.execute("UPDATE wa_templates SET header_format = 'IMAGE' WHERE account_id = ?", (self.a,))
            c.commit()
        tpl = {"name": "mock_approved", "language": "en", "params": ["A"]}
        url = f"/api/whatsapp/conversations/{self.conv()['id']}/template"
        self.assertEqual(self.api("POST", url, tpl)[1]["error"], "missing_media")
        self.assertEqual(self.api("POST", url, dict(tpl, media_id=image))[0], 200)
        sent = []
        with mock.patch.dict(os.environ, {"WHATSAPP_MOCK": ""}), \
                mock.patch.object(WhatsAppClient, "is_configured", lambda self: True), \
                mock.patch.object(WhatsAppClient, "_post_message",
                                  lambda self, payload: sent.append(payload) or {"success": True, "message_id": "w"}):
            self.assertEqual(self.api("POST", url, dict(tpl, media_id=image))[0], 200)
        header = sent[0]["template"]["components"][0]
        self.assertEqual((header["type"], header["parameters"][0]["type"]), ("header", "image"))

        with mock.patch.object(media, "download_from_meta", lambda account, wa_id: self.PDF):
            message = cs.list_messages(self.a, self.conv()["id"])[0]
            jobs.run_job(jobs.enqueue(self.a, "media_fetch", {"message_id": message["id"], "wa_media_id": "1"}))
        got = self.api("GET", f"/api/whatsapp/conversations/{self.conv()['id']}/messages")[1]["messages"]
        self.assertEqual(next(m for m in got if m["id"] == message["id"])["media"]["mime"], "application/pdf")
        self.assertEqual(len(self.api("GET", "/api/media")[1]["items"]), 1)      # received files stay out of the library


if __name__ == "__main__":
    unittest.main()

"""UI redesign backend: one set of posts, lifecycle actions, dashboard and posts list."""
import contextlib
import io
import unittest
from datetime import datetime, timedelta

import tests._env  # noqa: F401
from tests.test_phase1 import Base, without_cover_rule, website
from tests.apihelpers import Caller, new_user
import database as db
from engine import blog_plan
from server.routes_public import handle_public_request
from scripts import merge_posts


class Posts(Base):
    def setUp(self):
        super().setUp()
        self.pid = db.create_project({"name": "Site", "github_repo": "x/y", "topic": "t",
                                      "target_framework": "generic"}, self.a)
        website(self, self.a)

    def old_post(self, status="published", title="Old post", slug="old-post", **extra):
        post_id = db.create_post(dict({"project_id": self.pid, "title": title, "slug": slug, "excerpt": "Short",
                                       "content_markdown": "Body", "target_path": "p.md", "tags": ["a", "b"],
                                       "status": "draft"}, **extra))
        db.update_post_status(post_id, status)
        return post_id

    def new_item(self, title="New post", publish_at="2030-01-01T00:00:00Z", **extra):
        return blog_plan.create(self.a, dict({"title": title, "body": "Text", "project_id": self.pid,
                                              "publish_at": publish_at}, **extra))["id"]

    def publish(self, **extra):
        without_cover_rule(self)
        item_id = self.new_item(**extra)
        self.assertEqual(self.api("POST", f"/api/blog/plan/{item_id}/submit")[0], 200)
        code, body = self.api("POST", f"/api/blog/plan/{item_id}/publish-now")
        self.assertEqual(code, 200, body)
        return item_id

    def row(self, item_id):
        return blog_plan._row(self.a, item_id)

    def linked(self, post_id):
        with db.get_connection() as c:
            r = c.execute("SELECT * FROM blog_plan WHERE post_id = ?", (post_id,)).fetchone()
        return dict(r) if r else None

    def public(self, slug):
        return handle_public_request(f"/api/public/projects/{self.pid}/posts/{slug}", {})[0]


class MergeTests(Posts):
    def test_backfill_is_a_dry_run_by_default_and_adds_each_post_once(self):
        ids = {s: self.old_post(s, slug=s) for s in ("published", "in_review", "failed", "scheduled")}
        mine = lambda: [r for r in merge_posts.plan() if r[0] in ids.values()]
        self.assertEqual(sorted(r[2] for r in mine()), ["draft", "failed", "needs_approval", "published"])
        self.assertIsNone(self.linked(ids["published"]))
        with contextlib.redirect_stdout(io.StringIO()):
            merge_posts.run(apply=True)
            self.assertEqual(mine(), [])
            merge_posts.run(apply=True)
        row = self.linked(ids["published"])
        self.assertEqual((row["status"], row["origin"], row["body"], row["keyword"], row["meta_description"]),
                         ("published", "legacy", "Body", "a, b", "Short"))
        self.assertTrue(row["published_at"])

    def test_a_deleted_draft_does_not_come_back(self):
        post_id = self.old_post("draft")
        item_id = blog_plan.mirror(post_id)
        blog_plan.delete(self.a, item_id)
        self.assertNotIn(post_id, [r[0] for r in merge_posts.plan()])
        self.assertIsNone(blog_plan.mirror(post_id))

    def test_old_approve_route_keeps_the_merged_row_in_step(self):
        post_id = self.old_post("in_review")
        blog_plan.mirror(post_id)
        self.assertEqual(self.api("POST", f"/api/posts/{post_id}/approve")[0], 200)
        self.assertEqual(self.linked(post_id)["status"], "published")


class LifecycleTests(Posts):
    def test_publish_now_from_review_records_the_approver(self):
        item_id = self.publish(publish_at="")
        self.assertEqual(self.row(item_id)["status"], "published")
        messages = [l["message"] for l in db.list_logs(self.a)]
        self.assertIn(f"Planned post #{item_id} approved by {self.owner['username']}.", messages)

    def test_publish_now_that_fails_the_checks_changes_nothing(self):
        item_id = self.new_item(publish_at="")
        self.assertEqual(self.api("POST", f"/api/blog/plan/{item_id}/submit")[0], 409)      # no cover
        without_cover_rule(self)
        blog_plan.submit(self.a, item_id)
        blog_plan._set(self.a, item_id, project_id=None)
        self.assertEqual(self.api("POST", f"/api/blog/plan/{item_id}/publish-now")[0], 409)
        self.assertEqual((self.row(item_id)["status"], self.row(item_id)["publish_at"]), ("needs_approval", ""))

    def test_a_failed_post_can_be_retried(self):
        without_cover_rule(self)
        item_id = self.new_item()
        blog_plan._set(self.a, item_id, status="failed", error="boom")
        blog_plan._set(self.a, item_id, images='[{"media_id": 1, "alt": "", "cover": true}]')
        self.assertTrue(self.api("GET", f"/api/content/posts/{item_id}")[1]["item"]["can"]["publish_now"])
        blog_plan._set(self.a, item_id, images="[]")
        blog_plan._set(self.a, item_id, body="")
        self.assertEqual(self.api("POST", f"/api/blog/plan/{item_id}/publish-now")[0], 409)
        self.assertEqual((self.row(item_id)["status"], self.row(item_id)["error"]), ("failed", "boom"))
        blog_plan._set(self.a, item_id, body="Text")
        self.assertEqual(self.agent_api("POST", f"/api/blog/plan/{item_id}/publish-now")[0], 403)
        self.assertEqual(self.api("POST", f"/api/blog/plan/{item_id}/publish-now")[0], 200)
        self.assertEqual((self.row(item_id)["status"], self.row(item_id)["error"]), ("published", ""))
        self.assertIn(f"Planned post #{item_id} publish retried by {self.owner['username']}.",
                      [l["message"] for l in db.list_logs(self.a)])

    def test_unpublish_takes_every_copy_off_and_republish_reuses_the_row(self):
        older = self.old_post(title="New post", slug="new-post")
        blog_plan.mirror(older)
        item_id = self.publish()
        post_id = self.row(item_id)["post_id"]
        self.assertEqual(self.agent_api("POST", f"/api/blog/plan/{item_id}/unpublish")[0], 403)
        self.assertEqual(self.api("DELETE", f"/api/blog/plan/{item_id}")[1]["error"], "published")
        self.assertEqual(self.api("POST", f"/api/blog/plan/{item_id}/unpublish")[0], 200)
        self.assertEqual(self.public("new-post"), 404)
        self.assertEqual((self.row(item_id)["status"], self.row(item_id)["post_url"]), ("draft", ""))
        self.assertEqual(self.linked(older)["status"], "draft")
        self.assertEqual(db.get_post(post_id)["status"], "draft")
        self.assertEqual(self.api("PATCH", f"/api/blog/plan/{item_id}", {"title": "Renamed"})[0], 200)
        blog_plan.submit(self.a, item_id)
        self.assertEqual(self.api("POST", f"/api/blog/plan/{item_id}/publish-now")[0], 200)
        self.assertEqual((self.row(item_id)["post_id"], self.public("new-post")), (post_id, 200))

    def test_live_edit_needs_a_publisher_and_keeps_the_address(self):
        item_id = self.publish()
        path = f"/api/blog/plan/{item_id}"
        self.assertEqual(self.agent_api("PATCH", path, {"body": "x"})[0], 403)
        self.assertRaises(blog_plan.PlanError, blog_plan.update, self.a, item_id, {"body": "x"})      # writers
        self.assertEqual(self.api("PATCH", path, {"project_id": None})[0], 409)
        self.assertEqual(self.api("PATCH", path, {"title": "Renamed", "body": "Changed"})[0], 200)
        post = db.get_post(self.row(item_id)["post_id"])
        self.assertEqual((post["title"], post["content_markdown"], post["slug"], post["status"]),
                         ("Renamed", "Changed", "new-post", "published"))


class ContentApiTests(Posts):
    def get(self, path, user=None, **query):
        return Caller(user or self.owner)("GET", path, query=query, account_id=None)

    def test_list_filters_sorts_pages_and_counts(self):
        late = self.new_item("Bravo", "2030-03-01T00:00:00Z", keyword="farm")
        early = self.new_item("alpha", "2030-02-01T00:00:00Z")
        undated = self.new_item("Charlie", "")
        code, body = self.get("/api/content/posts", account=self.a)
        self.assertEqual(code, 200, body)
        self.assertEqual([i["id"] for i in body["items"]], [early, late, undated])
        self.assertEqual((body["total"], body["counts"]["draft"], body["counts"]["all"]), (3, 3, 3))
        ids = lambda **q: [i["id"] for i in self.get("/api/content/posts", account=self.a, **q)[1]["items"]]
        self.assertEqual(ids(dir="desc"), [late, early, undated])
        self.assertEqual(ids(sort="title"), [early, late, undated])
        self.assertEqual(ids(q="FARM"), [late])
        self.assertEqual(ids(q="%"), [])
        self.assertEqual(ids(**{"from": "2030-02-15T00:00:00Z", "to": "2030-04-01T00:00:00Z"}), [late])
        self.assertEqual(ids(page_size="2", page="2"), [undated])
        self.assertEqual(ids(tab="published"), [])
        for bad in ({"sort": "id"}, {"tab": "x"}, {"page": "0"}, {"page_size": "101"}, {"from": "soon"},
                    {"project_id": "x"}, {"dir": "up"}):
            self.assertEqual(self.get("/api/content/posts", account=self.a, **bad)[1].get("error"),
                             "invalid_parameter", bad)

    def test_summary_shape_and_actions(self):
        item_id = self.new_item(publish_at="")
        item = self.get(f"/api/content/posts/{item_id}")[1]["item"]
        self.assertEqual((item["state"], item["missing"], item["cover"], item["url"], item["slug"], item["body"]),
                         ("draft", ["cover", "publish_date"], None, "", "new-post", "Text"))
        self.assertEqual((item["account_id"], item["project_name"], item["can"]["submit"], item["can"]["approve"]),
                         (self.a, "Site", True, False))
        viewer = self.get(f"/api/content/posts/{item_id}", user=self.viewer)[1]["item"]
        self.assertEqual(set(viewer["can"].values()), {False})

    def test_other_accounts_stay_hidden(self):
        item_id = self.new_item()
        outsider = new_user("x")
        for path in ("/api/content/posts", "/api/dashboard", "/api/content/options"):
            self.assertEqual(self.get(path, user=outsider, account=self.a)[0], 403, path)
        self.assertEqual(self.get("/api/content/posts", user=outsider)[1]["items"], [])
        self.assertEqual(self.get(f"/api/content/posts/{item_id}", user=outsider)[0], 404)
        self.assertEqual(Caller(None)("GET", "/api/dashboard", account_id=None)[0], 401)

    def test_dashboard(self):
        without_cover_rule(self)
        soon = (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z"
        waiting = self.new_item("Waiting", soon)
        blog_plan.submit(self.a, waiting)
        scheduled = self.new_item("Scheduled", soon)
        blog_plan.submit(self.a, scheduled)
        self.assertEqual(self.api("POST", f"/api/blog/plan/{scheduled}/approve")[0], 200)
        live = self.publish(title="Live")
        blog_plan.mirror(self.old_post("failed", slug="broken"))
        code, body = self.get("/api/dashboard", account=self.a)
        self.assertEqual(code, 200, body)
        self.assertEqual(body["counts"], {"in_review": 1, "scheduled_7d": 1, "published_30d": 1, "failed": 1})
        self.assertEqual([i["id"] for i in body["approval_queue"]], [waiting])
        self.assertEqual([i["id"] for i in body["upcoming"]], [scheduled])
        self.assertEqual(body["recent"][0]["id"], live)
        self.assertEqual(body["recent"][0]["url"], "https://www.example.com/blog/live")
        self.assertTrue(all("account_id" in a for a in body["alerts"]))
        options = self.get("/api/content/options", account=self.a)[1]
        self.assertEqual((options["accounts"][0]["can_publish"], options["projects"][0]["id"]), (True, self.pid))


if __name__ == "__main__":
    unittest.main()

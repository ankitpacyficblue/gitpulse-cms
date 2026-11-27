# UI Redesign Backend Implementation Plan

> Executed natively (superpowers:executing-plans) in one session; tests first per task.

**Goal:** One set of posts, plus the dashboard and posts-list endpoints in `docs/UI-REDESIGN.md`.
**Spec:** docs/UI-REDESIGN.md (approved). **Tech:** Python stdlib, SQLite locally, Postgres in production.

## Global Constraints
Additive schema only, `IF NOT EXISTS`. No new dependency. No test data in the shared database. Backfill only by
script, dry run by default. Public and writer APIs unchanged. god merges.

## Review Focus
- Unpublish with an older published copy of the same slug: nothing resurfaces.
- Deleting a draft that has a `posts` row: a later backfill must not bring it back.
- Writer token editing a published post: still refused.
- Another account's id on the new GET endpoints: 403, no rows.
- Republish or live edit after a title change: the website address does not change.

## Task 1: schema, `blog_plan.mirror/sync_from_post`, `scripts/merge_posts.py`, pipeline and old `/api/posts` routes
- `mirror(post_id, origin) -> Optional[int]` (None: already linked, deleted, or no account).
- `sync_from_post(post_id) -> None`. `merge_posts.plan() -> list[(post_id, account_name, state)]`.
- Tests `tests/test_redesign.py::MergeTests`.

## Task 2: lifecycle: `unpublish`, delete guard, live edit, publish-now from review, reuse `posts` row
- `unpublish(account_id, item_id)`, `update(account_id, item_id, data, can_publish=False)`,
  `publish_now(account_id, item_id, host="")`. Tests `::LifecycleTests`.

## Task 3: `engine/content.py` and routes
- `accounts_for(user, account) -> list`, `listing(accounts, params, host)`, `dashboard(accounts, host)`,
  `options(accounts)`, `detail(accounts, item_id, host)`. Tests `::ContentApiTests`.

## Task 4: full suite, dry run on production (read-only), PR.

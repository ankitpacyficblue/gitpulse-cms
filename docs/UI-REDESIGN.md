# GitPulse UI redesign: design and API contract

Status: approved by god on 2026-11-27, with Unpublish added. Owners: Oscar (data, API), Andy (screens).

## Why
The owner/admin runs several business sites. On opening the app they need: what needs approval, what goes
live next, what just went live (with its link), and what failed. Today the landing page is a repository list,
and blog work is split over four screens and two data models.

## Scope
- A Dashboard (landing page) and one Posts area replacing Schedule, Status, Editorial Staging and Articles Feed.
- New Lead, Deal and Broadcast move to a CRM (customer relationship management) section.
- Consistent controls; no overflow from 390 to 1440 px.
- Not in scope: website changes, MyHomes Express data, new publishing behaviour, WhatsApp behaviour.

## Approaches to the data merge
1. **Chosen:** `blog_plan` is the post. `posts` stays as the published copy that websites read. Older `posts`
   rows get a `blog_plan` row. Public API, writer API and ids do not change.
2. Move everything into `posts`. One table, but writer ids, jobs, media usage and publishing all change.
   More risk for no visible difference.
3. Merge only in the list API. No migration, but two sets of rules stay. god asked for a real merge.

## Data
- Additive: `blog_plan.origin TEXT NOT NULL DEFAULT ''` and a unique index on `blog_plan.post_id`
  (where not null), both created with `IF NOT EXISTS`. Before any deployment of that code, a read-only check on
  production confirms there are no duplicate non-null `post_id` values; the PR reports it.
- Backfill: one row per `posts` row that has no `blog_plan` row and whose website belongs to an account.
  `origin='legacy'`. Nothing in `posts` is changed or deleted.
  Status: published → published; in_review → needs_approval; failed or publishing → failed; other → draft.
- Backfill is an explicit script (`scripts/merge_posts.py`, dry run by default), **not** run at start-up.
  Running it again adds nothing. god sees the dry-run counts per account and status before saying go. Undo: delete `origin='legacy'` rows.
- **Shared database:** the schema is applied at cold start, so the PR's preview deployment adds the column and
  index to the live database. god approved that. The backfill runs only when god says.
- The generator (`engine/pipeline.py`) also creates the `blog_plan` row, so new posts cannot split again.
- Publishing a post that already has a `post_id` updates that `posts` row instead of adding one.

## Behaviour changes
- Legacy posts in review now need a cover image before approval, like every other post.
- A published post can be edited by someone with `content.publish`; the change goes live at once.
- A published post cannot be deleted (409 `published`); it would stay live and disappear from the list.
- **Unpublish** (needs `content.publish`) takes a post off the website and makes it Draft. The `posts` row is kept
  and reused on the next publish. Older published copies with the same website address (slug) come off too, so
  none resurfaces. Files already made public keep their links.
- "Publish now" works from In review: it approves, then publishes. Same checks as approval, and it records the
  approver and time as Approve does.

## UI components (Andy builds)
No new library (agreed). The app has no build step; use native `select`, `dialog`, `popover` and tables with
one set of styles in `static/css`.

---

# API contract

All endpoints need a session. Times are ISO 8601 UTC ending in `Z`, or null. Errors:
`{"success":false,"error":"code","message":"text"}`.

`account` query parameter: an account id, or `all` (default): every account the user may see. A foreign id
returns 403. No `X-Account-Id` header is needed on the new GET endpoints.

## Status values (`state`)
| state | tab (`tab=`) | meaning |
|---|---|---|
| `draft` | `draft` | being written |
| `rejected` | `draft` | sent back, see `rejected_note` |
| `in_review` | `in_review` | waits for approval |
| `scheduled` | `scheduled` | approved, waits for `publish_at` |
| `published` | `published` | live |
| `failed` | `failed` | publish failed, see `error` |

Show `state`; ignore the older `status` field.

## PostSummary
```json
{"id": 12, "account_id": "ab12", "account_name": "The Villa Projekt",
 "project_id": 16, "project_name": "Villa blog",
 "title": "…", "state": "in_review",
 "publish_at": "2026-12-01T04:30:00Z", "published_at": null, "updated_at": "…",
 "url": "", "error": "", "rejected_note": null,
 "writer_id": 3, "writer": "Toby", "assignee_id": 7, "assignee_name": "…",
 "cover": {"url": "…", "alt": "…"},
 "missing": ["cover"],
 "can": {"edit": true, "approve": false, "publish_now": false, "reject": true, "submit": false, "delete": true, "unpublish": false}}
```
`cover` may be null. `url` is the website link, empty until published or while no website address is saved.
`missing` holds any of `body`, `cover`, `website`, `publish_date`. `can` already accounts for role and state.
`publish_now` is true without a `publish_date`; `approve` is not.

## GET /api/dashboard?account=
```json
{"counts": {"in_review": 2, "scheduled_7d": 3, "published_30d": 11, "failed": 0},
 "approval_queue": [PostSummary],
 "upcoming": [PostSummary],
 "recent": [PostSummary],
 "alerts": [{"id": 5, "account_id": "ab12", "account_name": "…", "type": "blog_failed",
             "severity": "error", "message": "…", "link": "blog:12", "count": 1, "last_seen": "…"}]}
```
- `approval_queue`: up to 20, earliest `publish_at` first, undated last.
- `upcoming`: up to 20 scheduled, soonest first. `recent`: up to 10 published, newest first.
- Alert `id` null: a system notice that cannot be dismissed (`account_id` empty).
  Dismiss others with the existing `POST /api/alerts/<id>/resolve`.

## GET /api/content/posts
| param | values | default |
|---|---|---|
| `account` | id, `all` | `all` |
| `tab` | `all`, `draft`, `in_review`, `scheduled`, `published`, `failed` | `all` |
| `project_id`, `writer_id`, `assignee_id` | integer | none |
| `from`, `to` | ISO time; `from` inclusive, `to` exclusive. Matches `published_at` if published, else `publish_at` | none |
| `q` | text in title, topic or keyword, any case | none |
| `sort` | `publish_at`, `published_at`, `updated_at`, `title` | `published_at` on the published tab, else `publish_at` |
| `dir` | `asc`, `desc` | `desc` for `published_at` and `updated_at`, else `asc` |
| `page` | from 1 | 1 |
| `page_size` | 1–100 | 25 |

```json
{"items": [PostSummary], "total": 57, "page": 1, "page_size": 25, "sort": "publish_at", "dir": "asc",
 "counts": {"all": 57, "draft": 4, "in_review": 2, "scheduled": 3, "published": 48, "failed": 0}}
```
Empty dates sort last in both directions. `counts` follow every filter except `tab`. Unknown values return
400 `invalid_parameter`. The page's own address should carry the same parameter names.

## GET /api/content/options?account=
For the filter and editor dropdowns:
```json
{"accounts": [{"id": "ab12", "name": "…", "website_url": "https://…", "can_write": true, "can_publish": true}],
 "projects": [{"id": 16, "name": "…", "account_id": "ab12"}],
 "writers":  [{"id": 3, "name": "Toby", "account_id": "ab12"}],
 "members":  [{"id": 7, "name": "…", "account_id": "ab12"}]}
```

## GET /api/content/posts/<id>
`{"item": Post}`. 404 if not visible to this user. `Post` = PostSummary plus:
```json
{"topic": "…", "keyword": "a, b", "body": "markdown", "seo_title": "", "meta_description": "",
 "slug": "…", "rejected_by_name": null, "rejected_at": null,
 "images": [{"media_id": 4, "alt": "…", "cover": true, "og": false, "name": "a.jpg", "url": "signed link",
             "public_url": "…"}]}
```
Preview: render `body` as markdown with the cover on top. `slug` is what publishing will use.

## Changes: existing routes, send `X-Account-Id: <item.account_id>`
| action | route |
|---|---|
| create | `POST /api/blog/plan` |
| edit | `PATCH /api/blog/plan/<id>` with `title, topic, keyword, body, publish_at, project_id, assignee_id, writer_token_id, seo_title, meta_description, images:[{media_id,alt,cover,og}]` |
| delete | `DELETE /api/blog/plan/<id>` |
| AI draft | `POST /api/blog/plan/<id>/draft` |
| submit / approve / publish now | `POST /api/blog/plan/<id>/submit`, `/approve`, `/publish-now` |
| reject | `POST /api/blog/plan/<id>/reject` `{"note":"…"}` |
| unpublish (published only; show it in place of Delete) | `POST /api/blog/plan/<id>/unpublish` |
| images | existing `/api/media/*` routes |

Editor field `writer_token_id` is `writer_id` in responses. After any change, fetch the post and list again
rather than reading the older response shape.

Rules the UI must show: editing a scheduled post sends it back to In review; editing a failed post makes it
Draft.

The old `/api/posts*` and `GET /api/blog/plan` routes stay until the new screens ship, then are removed.

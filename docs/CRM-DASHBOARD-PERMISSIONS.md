# CRM dashboard and section permissions: design and API contract

Status: waiting for god's approval. Backend and migration: Oscar. Screens: Andy, after #18 merges.
CRM = customer relationship management.

## Permissions

### Levels
`none` < `view` < `manage` < `full`. Each includes the ones before it. `full` exists only where today's roles
already separate a stronger action:

| section key | sidebar | view | manage | full adds |
|---|---|---|---|---|
| `blog_dashboard` | Blog Dashboard | see | | |
| `posts` | Posts | see | write, edit drafts, submit, AI draft, delete drafts | **publish**: approve, reject, publish, unpublish, edit live, generate-and-publish |
| `websites` | Websites | see | connect, edit, delete | |
| `media` | Media | see | upload | delete files |
| `crm_dashboard` | CRM Dashboard | see | | |
| `inbox` | Inbox | read | reply, send template, assign, hand-off, AI on/off | |
| `contacts` | Contacts | see | add, edit | delete, custom fields, consent |
| `pipeline` | Pipeline | see | add, move | delete |
| `broadcasts` | Broadcasts | see | create, preview, run | |
| `automations` | Automations | see | add, toggle, delete | |
| `ai_assistant` | AI assistant | see | edit, test | |
| `templates` | Templates | see | sync | |
| `entry_links` | Entry links | see | add, delete | |
| `wa_setup` | WhatsApp setup | see (secrets stay masked) | credentials, test, simulator | |
| `users` | Users & Roles | | people, roles, overrides, writer tokens | |
| `logs` | Logs | see | | |
| `settings` | Settings | | account settings, name, website address, currency | |
| `database` | Database | platform admin only; no account role can grant it | | |

`logs` and `settings` are in the sidebar but were not in the list, so they are added with today's access.

### Roles
| role key | name | access |
|---|---|---|
| `owner` | Owner | everything; also delete the account, manage owners, edit roles. Not editable |
| `admin` | Admin | highest level of every section except `settings` (stays owner-only) and `database` |
| `content_editor` | Content editor | `blog_dashboard` view, `posts` full, `websites` manage, `media` manage |
| `crm_agent` | CRM agent | `crm_dashboard` view, `inbox` manage, `contacts` manage, `pipeline` manage |
| `viewer` | Viewer | view on every section except `users`, `logs`, `settings`, `database` |

- One role per person per account, plus per-person overrides (any level, including `none`, per section).
- The role grid is editable per account for every role but Owner (owner only). Only changes are stored, so
  "reset to default" removes them.
- Nobody can give a level higher than their own, change their own access, or (unless owner) touch an owner.
- Inbox users may also list and upload media (chat attachments) and read contacts and templates needed to
  reply, even with those sections hidden.

### Existing people keep what they have
Owner → `owner`, Admin → `admin`, Viewer → `viewer`. Today's **Agent** has no exact match: they become
`crm_agent` **plus overrides** that restore the rest (posts, websites view, media manage, broadcasts,
automations, AI, templates, entry links, WhatsApp setup view). The platform admin acts as owner, as today.

One difference: today's Viewer and Agent can see WhatsApp setup and AI knowledge; they still can.

### Data (additive, `IF NOT EXISTS`)
- `memberships.role_key TEXT NOT NULL DEFAULT ''`. The old `role` column and its constraint stay, holding the
  closest old role so a rollback fails closed (`content_editor`, `crm_agent` → `viewer`). Empty `role_key`
  means "use `role`", so nobody needs rewriting except agents.
- `role_permissions(account_id, role_key, section, level)`; `permission_overrides(account_id, user_id, section, level)`.
- `automation_runs(account_id, automation_id, ok, error, created_at)`.
- Agent conversion runs once at start-up, only for `role='agent' AND role_key=''`, so repeating it does nothing.

### Enforcement
Every `/api` route has a section and level; an unlisted route is refused. Failure: 403
`{"error":"forbidden","required":"posts:full"}`. `account=all` lists only accounts where the person has the
level; naming one without it is 403. A test walks every route with each seeded role. Writer tokens,
webhooks, the scheduler and public endpoints are unchanged. The existing names (`content.publish`,
`crm.write`, …) become derived values (`content.publish` = `posts:full`) so old checks keep working.

## CRM dashboard
First item under WhatsApp CRM. Read-only; every block links to its section.

**Two limits of the current data**
- **Entry-link clicks are not recorded** (links open WhatsApp directly). The block shows leads per link;
  no click count. Counting clicks would need a redirect address; not built.
- **Automation runs and failures** are counted only from this release on.

## API contract

### `GET /api/auth/me` (send `X-Account-Id`)
Adds `role_key`, `role_name`, `access`: `{"posts":"full","inbox":"none", …}` (every section key).
`permissions` stays. Hide a section when its level is `none`; hide buttons using the table above.

### `GET /api/accounts/<id>/roles` (`users` manage)
```json
{"sections":[{"key":"posts","name":"Posts","group":"blog","levels":["none","view","manage","full"],"full_name":"Publish"}],
 "roles":[{"key":"crm_agent","name":"CRM agent","editable":true,"changed":false,"access":{"inbox":"manage"}}],
 "can_edit_roles":true, "my_access":{"posts":"full"}}
```
`database` is not listed. A section's `levels` are the only values it accepts.
- `PUT /api/accounts/<id>/roles/<key>` `{"access":{section:level}}` (owner). `DELETE` same path: reset.

### People
- `GET /api/accounts/<id>/users`: each gains `role_key`, `overrides` `{section:level}`, `access`.
- `POST` and `PUT …/users[/<uid>]`: `role` takes a role key.
- `PUT …/users/<uid>/overrides` `{"overrides":{section:level}}`: replaces them all; `{}` clears.
- Errors: 400 `invalid_role` / `invalid_section` / `invalid_level`; 403 `above_your_access` / `own_access` /
  `owner_only`.

### `GET /api/crm/dashboard?account=<id|all>` (`crm_dashboard` view)
Dates are UTC; "this month" is the calendar month in India time. A block the person may not view
(its section is `none` in that account) is left out of totals; if so in every account, the block is `null`.
Money is never added across currencies.
```json
{"cards":{"unread_conversations":3,"new_contacts_7d":4,"new_contacts_30d":19,
          "open_deals":{"count":6,"values":[{"currency":"INR","value":1250000}]},
          "won_this_month":{"count":1,"values":[{"currency":"INR","value":400000}]}},
 "pipeline":[{"stage":"lead","count":2,"values":[{"currency":"INR","value":0}]}],
 "needs_reply":[{"conversation_id":9,"account_id":"…","account_name":"…","contact_name":"…",
                 "preview":"…","waiting_since":"…Z","unread":2,"needs_human":false}],
 "broadcasts":[{"id":4,"account_id":"…","account_name":"…","name":"…","status":"completed","created_at":"…Z",
                "recipients":50,"sent":48,"delivered":45,"read":20,"failed":2}],
 "automations":{"active":3,"total":5,"runs_7d":14,"failures_7d":1,"counted_since":"…Z"},
 "templates":{"APPROVED":4,"PENDING":1,"REJECTED":0},
 "entry_links":[{"id":2,"account_id":"…","account_name":"…","label":"Website","code":"WEB","leads_30d":7}],
 "alerts":[{"id":null,"account_id":"…","account_name":"…","type":"wa_not_connected","severity":"warning",
            "message":"WhatsApp is not connected.","link":"wa-config","count":1}]}
```
- `pipeline`: all six stages in order (`lead, qualified, proposal, negotiation, won, lost`). Open = the first four.
  Won this month = in `won` with its last change this month.
- `needs_reply`: last message is from the contact, or flagged for a person; longest waiting first; up to 20.
- `broadcasts`: newest 5. `entry_links`: top 10 by leads (new contacts that arrived with that code).
- Alerts: stored alerts plus computed `wa_not_connected` and `template_rejected` (`id` null: not dismissible).

## Not in scope
Custom new roles, click tracking, any change to WhatsApp sending, MyHomes Express data.

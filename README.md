# ⚡ GitPulse CMS

> **Autonomous, multi-repository blog publishing engine for GitHub projects.**  
> Automatically researches relevant topics, ingests repository context, generates in-depth technical articles via AI, validates SEO & brand safety, synthesizes 1200x630 OpenGraph banners, and serves it to your websites through a public read API (it never commits to your repositories).

---

## 🌟 Why GitPulse CMS?

Every modern software company, open-source project, and dev tool needs an active, high-quality engineering blog for SEO, user onboarding, and technical authority. However, manually coordinating daily or weekly posts across multiple project repositories is time-consuming and inconsistent.

**GitPulse CMS** is an end-to-end CMS designed specifically to plug into **any number of GitHub repositories** simultaneously:
- **Zero Third-Party Dependencies:** Written in standard modern Python (3.8+)—runs immediately without `pip install` headaches or fragile `node_modules`.
- **Publishing without releases:** websites read published posts from the public API ([docs/PUBLISHING.md](docs/PUBLISHING.md)).
- **🖼️ Automated Hero & OpenGraph Image Pipeline:** Pure Python 1200x630 SVG synthesis with gradients, title wrapping, category tags, author badge, and reading time.
- **🔄 Bi-Directional GitHub Webhook Sync:** Cryptographic HMAC-SHA256 receiver automatically tracking PR merges and updating article status in real-time.
- **✍️ Human-in-the-Loop Editorial Staging:** Hold drafts in staging, refine them in a live split-screen Markdown editor with instant HTML rendering, and approve with a single click.
- **🛡️ SEO Pre-Flight Linter & Brand Safety:** Validates title length, meta description, heading hierarchy, code fence languages, and filters out forbidden competitor words.
- **🧠 Repository Context Ingestion (RAG & Internal Linking):** Ingests target repo READMEs and automatically suggests natural internal cross-links to prior articles.
- **🔐 Defense-in-Depth Authentication & TOTP 2FA:** PBKDF2-HMAC-SHA256 password hashing, brute-force IP lockout, unguessable 256-bit session cookies, and RFC 6238 Two-Factor Authentication.
- **Multi-Framework Auto-Adapters:** Pre-configured support for **Next.js** (MDX/Contentlayer/Velite), **Astro** (Content Collections), **Hugo**, **Jekyll** (GitHub Pages), **Docusaurus**, and Generic Markdown.
- **Pluggable AI Generation:** Native support for **Google Gemini** (1.5/2.0 Flash & Pro), **OpenAI** (GPT-4o), and a high-fidelity **Built-in Architectural Generator**.
- **Real-Time Web Dashboard:** A responsive single-page application with metrics, repository manager, split editor, live markdown viewer, and audit logs.
- **Background Cron Daemon:** Built-in lightweight scheduler executing automated daily publications at each project's specified UTC time.

---

## 🏗️ Architecture Overview

```
                      +------------------------------------------+
                      |         GitPulse Web Dashboard           |
                      |   (Projects, Posts, Settings, Staging)   |
                      +--------------------+---------------------+
                                           |
                                           v
+------------------------+      +----------+----------+      +------------------------+
|   Background Daemon    | ---> |     Engine Core     | <--- |     REST API / CLI     |
| (Per-Repo Daily Cron)  |      |   (Topic Planner)   |      |  (CI/CD / Webhooks)    |
+------------------------+      +----------+----------+      +------------------------+
                                           |
                                           v
                       +-------------------+-------------------+
                       |         Context & AI Engine           |
                       |  (Repo README RAG + Gemini / OpenAI)  |
                       +-------------------+-------------------+
                                           |
                                           v
                       +-------------------+-------------------+
                       |     SEO Linter & Image Generator      |
                       |  (Brand Safety + 1200x630 SVG Hero)   |
                       +-------------------+-------------------+
                                           |
                                           v
                       +-------------------+-------------------+
                       |         Delivery Engine               |
                       | - Headless Dynamic Public Content API |
                       | - Direct Commit OR GitHub Pull Request|
                       +-------------------+-------------------+
                                           |
             +-----------------------------+-----------------------------+
             |                             |                             |
             v                             v                             v
   [ Zero-Redeploy Page ]         [ Astro Tech Blog ]           [ Next.js SaaS Repo ]
 (public/blog/index.html)     (src/content/blog/*.md)          (content/posts/*.mdx)
```

---

## 🚀 Quick Start

### 1. Launch Web Dashboard & Background Scheduler

```bash
cd /Users/ankitmalhotra/.gemini/antigravity/scratch/gitpulse-cms

# Start dashboard on port 8420
python3 app.py
```

Open your browser at **`http://localhost:8420`**.

- **Default Username:** `admin`
- **Default Password:** `GitPulse@Admin2026!`

---

### 2. Command Line Interface (CLI)

```bash
# 1. Initialize database and load sample repositories
python3 cli.py init

# 2. View all connected GitHub projects
python3 cli.py list-projects

# 3. Trigger an immediate article generation & publication
python3 cli.py publish --project-id 1

# 4. Generate draft only without publishing
python3 cli.py publish --project-id 1 --draft-only

# 5. Reset or create an admin password
python3 cli.py reset-password --username admin --password "StrongNewPassword!"
```

---

## 💬 WhatsApp Automation & CRM Architecture (Powered by ArnasDon/wacrm)

GitPulse CMS now features full native integration with **WACRM** (open-source Meta WhatsApp Cloud API-based CRM and automations architecture):

### 1. Clear Categorized Sidebar Navigation Menu
The dashboard navigation is organized into clean, dedicated sections:
- **📰 Blog & Content Engine**:
  - `Connected Repos`: Multi-framework publishing targets with 3-step guided website connector.
  - `Editorial Staging`: Draft queue with live SEO pre-flight scoring and split-screen Markdown editor.
  - `Articles Feed`: Published posts feed with live GitHub commits, PR tracking, and markdown viewer.
- **💬 WhatsApp Automation & CRM**:
  - `Shared Team Inbox`: Two-way threaded chat window with real-time delivery ticks (✓ sent, ✓✓ delivered, blue ✓✓ read), canned response chips, and message composer.
  - `Contacts & Audience (CDP)`: Contact directory with WhatsApp phone links, audience tags (`VIP`, `Customer`, `Lead`), notes, and search.
  - `Sales Pipeline (Kanban)`: 5-stage drag-and-drop/1-click Kanban pipeline (`Lead` -> `Qualified` -> `Proposal` -> `Negotiation` -> `Won`) with deal values and expected close dates.
  - `Broadcast Campaigns`: Mass WhatsApp campaigns targeted by audience tags with delivery analytics (sent, delivered, read).
  - `No-Code Automations`: Visual event triggers for welcome greetings, keyword auto-replies, and **Blog-to-WhatsApp publication alerts**.
- **⚙️ Platform & Settings**:
  - `WhatsApp API Setup`: Meta Cloud API v21.0 credentials, copyable Webhook Callback URL, verify token, and live testing simulator.
  - `Supabase Cloud DB`: PostgreSQL schema status, health check, and 1-click cloud sync.
  - `Activity & Webhook Logs`: Real-time audit trail of blog generation, GitHub commits, and Meta webhooks.
  - `Security & 2FA`: TOTP 2FA authenticator, malicious login lockout, and password management.

---

## 📡 Headless Public & Webhook API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/public/projects/{id}/posts` | `GET` | Paginated JSON feed of published posts for client websites |
| `/api/public/projects/{id}/posts/{slug}` | `GET` | Full post markdown, frontmatter, and view counter |
| `/api/public/projects/{id}/posts/{slug}/og-image.svg` | `GET` | Dynamic 1200x630 OpenGraph hero banner |
| `/api/public/projects/{id}/rss.xml` | `GET` | Auto-generated RSS 2.0 XML feed |
| `/api/webhook/github` | `POST` | Bi-directional GitHub Webhook receiver (HMAC-SHA256 verified) |
| `/api/webhook/whatsapp` | `GET` | Meta WhatsApp Cloud API Webhook verification handshake (`hub.challenge`) |
| `/api/webhook/whatsapp` | `POST` | Inbound WhatsApp messages, status ticks (`delivered`, `read`), and auto-responders |
| `/api/whatsapp/conversations` | `GET` | Threaded conversations list with unread counters |
| `/api/whatsapp/conversations/{id}/messages` | `GET / POST` | Conversation message history & outbound WhatsApp dispatch |
| `/api/whatsapp/contacts` | `GET / POST` | Customer audience directory & CDP tag filtering |
| `/api/whatsapp/deals` | `GET / POST / PUT` | Sales Pipeline Kanban deals & stage advancement |
| `/api/whatsapp/broadcasts` | `GET / POST` | Mass WhatsApp broadcast campaign runner |
| `/api/whatsapp/automations` | `GET / POST / PUT` | No-code event rules & active/paused toggles |
| `/api/whatsapp/simulate-incoming` | `POST` | Inbound WhatsApp simulator for instant testing |

---

## 🧪 Automated Test Suite

Run the comprehensive unit and integration test suite:

```bash
python3 -m unittest discover tests
```

All **29 tests** pass in under 0.7 seconds with zero external pip dependencies.

---

## 🛡️ License

MIT License. Built for modern software engineering teams and technical blogs.

## Client accounts, roles and per-account WhatsApp

Every CRM, WhatsApp and blog row belongs to one **account** (a client business). Users join accounts as
`owner`, `admin`, `agent` or `viewer`; the server checks the role on every route. The browser names the active
account with the `X-Account-Id` header. There is no sample data and no default login.

Environment (set in Vercel project settings, never in git):

| Variable | Needed for |
|---|---|
| `SESSION_SECRET` | Signs session tokens. Required on Vercel. |
| `CREDENTIAL_ENC_KEY` | 32 random bytes, base64 (`python3 -c "from engine.secrets_box import generate_key as g; print(g())"`). Encrypts WhatsApp tokens. Losing it means owners must re-enter tokens. |
| `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD` (12+ chars) | Creates the first platform admin where there is no shell. |
| `WHATSAPP_APP_SECRET` | Optional platform-wide Meta app secret for webhook signatures (accounts may store their own). |
| `WHATSAPP_MOCK=1` | Dev/tests only: simulated sends and the simulate-incoming endpoint. |

Local setup: `python3 cli.py create-platform-admin --username you`, then `python3 cli.py create-owner --account "Acme" --username acme-owner`.
Meta webhook: one URL for all accounts, `/api/webhook/whatsapp`; each account has its own verify token (shown once) and is routed by its phone number id.
Tests: `pip install -r requirements.txt && python3 -m unittest discover -s tests -t .`
Database changes for Supabase are in `supabase/migrations/` (review before applying; not applied automatically).


## Storage: SQLite or Postgres (Supabase)

- No `DATABASE_URL`: SQLite at `GITPULSE_DB_PATH` (local runs and tests). On Vercel this is `/tmp` and is wiped on cold start, so do not use it for a preview people test on.
- `DATABASE_URL=postgresql://...` (Supabase connection string, secret): all storage goes to Postgres through `pg8000`. `init_db()` creates the tables on first start and turns on row level security with no policies, so the Supabase REST API cannot read them. Use a NEW project, not the live one.
- `dbcompat.py` translates the app's SQL for Postgres. It is covered by unit tests and a syntax check, but has not been run against a live Postgres yet.

# ⚡ GitPulse CMS

> **Autonomous, multi-repository blog publishing engine for GitHub projects.**  
> Automatically researches relevant topics, ingests repository context, generates in-depth technical articles via AI, validates SEO & brand safety, synthesizes 1200x630 OpenGraph banners, and delivers content to your GitHub websites either via Pull Requests/Commits **OR dynamically via Zero-Redeploy dynamic blog pages**.

---

## 🌟 Why GitPulse CMS?

Every modern software company, open-source project, and dev tool needs an active, high-quality engineering blog for SEO, user onboarding, and technical authority. However, manually coordinating daily or weekly posts across multiple project repositories is time-consuming and inconsistent.

**GitPulse CMS** is an end-to-end CMS designed specifically to plug into **any number of GitHub repositories** simultaneously:
- **Zero Third-Party Dependencies:** Written in standard modern Python (3.8+)—runs immediately without `pip install` headaches or fragile `node_modules`.
- **⚡ Zero-Redeploy "One-Time Blog Page" Architecture:** Commit a standalone dynamic blog page to client repositories **ONCE**. Future daily articles appear in real-time dynamically without burning CI/CD minutes or triggering rebuilds!
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

## ⚡ Zero-Redeploy Architecture (No CI/CD Rebuilds Needed)

For businesses that do not want every daily blog post to trigger a full website deployment on Vercel, Netlify, or AWS, GitPulse provides the **Zero-Redeploy Dynamic Blog Page**:

```
+------------------+         Publishes New Post          +-----------------------+
|  GitPulse CMS    | ----------------------------------> | SQLite / Public Cache |
+------------------+                                     +-----------+-----------+
                                                                     |
                           Client Website (Deploys ONCE)             | Real-time JSON
                           +---------------------------+             | (/api/public/...)
                           |   public/blog/index.html  | <-----------+
                           |   - Client-side SPA route |
                           |   - Instant Search & Tags |
                           |   - Dynamic Markdown view |
                           +---------------------------+
```

1. In the GitPulse Dashboard or via CLI, click **"Install Blog Page to Repository"**.
2. GitPulse commits a single, beautiful, responsive, dark-mode blog file (e.g. `public/blog/index.html`) to the client's repository once.
3. When daily articles are published in GitPulse CMS, the client's blog updates **immediately in real-time** with **zero build time, zero deployment failures, and zero git clutter!**
4. Search engine indexing is preserved via auto-generated RSS feeds (`/api/public/projects/:id/rss.xml`) and Sitemaps.

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

# 3. Commit one-time Zero-Redeploy dynamic blog page to repo
python3 cli.py install-blog-page --project-id 1

# 4. Trigger an immediate article generation & publication
python3 cli.py publish --project-id 1

# 5. Generate draft only without committing to GitHub
python3 cli.py publish --project-id 1 --draft-only

# 6. Reset or create an admin password
python3 cli.py reset-password --username admin --password "StrongNewPassword!"
```

---

## 📡 Headless Public API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/public/projects/{id}/posts` | `GET` | Paginated JSON feed of published posts for client websites |
| `/api/public/projects/{id}/posts/{slug}` | `GET` | Full post markdown, frontmatter, and view counter |
| `/api/public/projects/{id}/posts/{slug}/og-image.svg` | `GET` | Dynamic 1200x630 OpenGraph hero banner |
| `/api/public/projects/{id}/rss.xml` | `GET` | Auto-generated RSS 2.0 XML feed |
| `/api/webhook/github` | `POST` | Bi-directional GitHub Webhook receiver (HMAC-SHA256 verified) |

---

## 🚀 Vercel Serverless Deployment Guide

GitPulse CMS is optimized for **Vercel Serverless Functions** (`@vercel/python`):

1. **Push to GitHub**: Connect your repository to Vercel.
2. **Serverless Entrypoint**: Vercel automatically detects `vercel.json` and routes all traffic to `api/index.py` (WSGI + HTTP handler).
3. **Configure Environment Variables** in the Vercel Project Dashboard:
   - `SUPABASE_URL`: `https://suvmyyonlqyipzgnmony.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY`: `eyJhbGciOi...` (Your Supabase Service Role Key)
   - `GITHUB_TOKEN`: `ghp_...` (Your default GitHub Personal Access Token)
   - `GEMINI_API_KEY`: `AIzaSy...` (Optional, for Gemini AI generation)

---

## ☁️ Supabase Multi-Tenant Schema Architecture

For persistent storage across Vercel serverless runs and multi-client blog isolation, GitPulse connects directly to **Supabase PostgreSQL**:

- **Schema Architecture (`supabase_schema.sql`)**:
  - `clients`: Multi-tenant organization grouping for client businesses.
  - `projects`: Repositories connected to GitPulse with branch, framework presets, tone, and zero-redeploy configuration.
  - `posts`: Full markdown articles, hero SVG images, SEO scores, view counts, and GitHub commit/PR references.
  - `system_logs`, `settings`, `users`, `sessions`, `login_attempts`: Complete security and audit trail.
- **Applying Schema in Supabase**:
  Run `supabase_schema.sql` in the Supabase SQL Editor (`https://supabase.com/dashboard/project/suvmyyonlqyipzgnmony/sql`).
- **Cloud Sync**:
  Use the **"Sync All to Cloud"** button in Settings or `POST /api/supabase/sync` to replicate local projects and posts to Supabase.

---

## 🧙‍♂️ Non-Technical Guided UX: Connect Website in 60s

The post-login dashboard is designed specifically for non-technical team members:

1. **Step 1: Visual Website Picker**: Click Next.js, Astro, Simple HTML, or Hugo. All technical directories, file formats, and frontmatter templates are configured automatically.
2. **Step 2: 1-Click GitHub Linker**: Select the client business, type `owner/repo`, click the 1-click token generator shortcut, and click **"Test Repository Connection ⚡"** for instant live feedback.
3. **Step 3: Topics & Tone**: Select ready-made topic inspiration chips (AI, SaaS, Health, Fintech), click an emoji tone pill (👔 Professional, 🚀 Startup Casual, 🎓 Educational), choose Review Mode or Autopilot, and click **Connect Website & Start Publishing**!

---

## 🧪 Automated Test Suite

Run the comprehensive unit and integration test suite:

```bash
python3 tests/test_engine.py
```

All 20 tests pass in under 0.6 seconds with zero external dependencies.

---

## 🛡️ License

MIT License. Built for modern software engineering teams and technical blogs.

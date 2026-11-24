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

## 🧪 Automated Test Suite

Run the comprehensive unit and integration test suite:

```bash
python3 tests/test_engine.py
```

All 16 tests pass in under 0.6 seconds with zero external dependencies.

---

## 🛡️ License

MIT License. Built for modern software engineering teams and technical blogs.

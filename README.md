# ⚡ GitPulse CMS

> **Autonomous, multi-repository blog publishing engine for GitHub projects.**  
> Automatically researches relevant topics, generates in-depth technical articles via AI, formats framework-compliant Markdown/MDX with frontmatter, and publishes directly or opens Pull Requests to your GitHub repositories every single day.

---

## 🌟 Why GitPulse CMS?

Every modern software company, open-source project, and dev tool needs an active, high-quality engineering blog for SEO, user onboarding, and technical authority. However, manually coordinating daily or weekly posts across multiple project repositories is time-consuming and inconsistent.

**GitPulse CMS** is an end-to-end CMS designed specifically to plug into **any number of GitHub repositories** simultaneously:
- **Zero Third-Party Dependencies:** Written in standard modern Python (3.8+)—runs immediately without `pip install` headaches or fragile `node_modules`.
- **Brute-Force & Malicious Login Protection:** Built-in IP & username rate-limiting with automatic 15-minute account lockout after 5 consecutive failed attempts, preventing credential stuffing and dictionary attacks.
- **Enterprise-Grade Password Security:** PBKDF2-HMAC-SHA256 password hashing (260,000 iterations) with individual cryptographically random salts and constant-time verification (`hmac.compare_digest`) against timing attacks.
- **Secure Session & Cookie Flow:** Unguessable 256-bit entropy session tokens stored in SQLite and transmitted via `HttpOnly`, `SameSite=Strict` cookies with dedicated `/login` and `/api/auth/logout` flows.
- **Multi-Framework Auto-Adapters:** Pre-configured support for **Next.js** (MDX/Contentlayer/Velite), **Astro** (Content Collections), **Hugo**, **Jekyll** (GitHub Pages), **Docusaurus**, and Generic Markdown.
- **Intelligent Topic Engine:** Analyzes previous articles to prevent repetition, rotates editorial angles (deep-dives, performance benchmarks, troubleshooting postmortems, architecture trade-offs), and tailors technical depth to your target audience.
- **Dual GitHub Publishing Modes:**
  - **Pull Request Mode (Recommended):** Opens an informative, structured Pull Request with article summaries, tags, and review checklists for maintainer approval.
  - **Direct Commit Mode:** Directly commits and pushes new posts to `main` (or any custom branch) to immediately trigger your site's CI/CD deployment.
- **Pluggable AI Generation:** Native support for **Google Gemini** (1.5/2.0 Flash & Pro), **OpenAI** (GPT-4o), and a high-fidelity **Built-in Architectural Generator** for offline or zero-token testing.
- **Real-Time Web Dashboard:** A responsive single-page application with metrics, repository manager, post inspector, live markdown viewer, and audit logs.
- **Background Cron Daemon:** Built-in lightweight scheduler executing automated daily publications at each project's specified UTC time.
- **Reusable GitHub Action Workflow:** Plug-and-play workflow (`.github/workflows/daily-blog.yml`) ready to drop into any repository.

---

## 🔐 Security & Authentication

GitPulse CMS includes built-in security protections against malicious logins:
- **Brute-Force & Credential Stuffing Defense:** Tracks failed login attempts per IP and username in a sliding 15-minute window. If 5 consecutive failures occur, the IP/account is locked out for 15 minutes, returning an HTTP lockout response and countdown timer.
- **Timing-Attack Resistance:** Password hashes are verified in constant time using `hmac.compare_digest`.
- **PBKDF2-HMAC-SHA256:** Implements the OWASP-recommended standard with 260,000 iterations and a cryptographically random 16-byte salt per user.
- **Session Tokens:** Unguessable 256-bit cryptographically random tokens (`secrets.token_urlsafe(32)`) delivered via `HttpOnly`, `SameSite=Strict` cookies or `Authorization: Bearer <token>`.
- **Initial Setup Credentials:**
  - **Username:** `admin`
  - **Password:** `GitPulse@Admin2026!`
  - *(Can be changed anytime via the Settings tab in the Web Dashboard or CLI via `python3 cli.py reset-password --password "..."`)*

---

## 🏗️ Architecture Overview

```
                      +------------------------------------------+
                      |         GitPulse Web Dashboard           |
                      |   (Projects, Posts, Settings, Logs)      |
                      +--------------------+---------------------+
                                           |
                                           v
+------------------------+      +----------+----------+      +------------------------+
|   Background Daemon    | ---> |     Engine Core     | <--- |     REST API / CLI     |
| (Per-Repo Daily Cron)  |      |   (Topic Planner)   |      |  (CI/CD / Manual Run)  |
+------------------------+      +----------+----------+      +------------------------+
                                           |
                                           v
                       +-------------------+-------------------+
                       |              AI Engine                |
                       |  (Gemini API / OpenAI / Built-in)     |
                       +-------------------+-------------------+
                                           |
                                           v
                       +-------------------+-------------------+
                       |       Framework Formatters            |
                       | (Astro, Next.js, Hugo, Jekyll, Docus) |
                       +-------------------+-------------------+
                                           |
                                           v
                       +-------------------+-------------------+
                       |       GitHub REST API Client          |
                       |   Direct Commit OR Pull Request       |
                       +-------------------+-------------------+
                                           |
             +-----------------------------+-----------------------------+
             |                             |                             |
             v                             v                             v
   [ Next.js SaaS Repo ]          [ Astro Tech Blog ]           [ Docusaurus Docs ]
 (content/posts/*.mdx)        (src/content/blog/*.md)              (blog/*.md)
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

---

### 2. Command Line Interface (CLI)

GitPulse comes with a full CLI for scripting and headless deployments:

```bash
# 1. Initialize database and load sample repositories
python3 cli.py init

# 2. View all connected GitHub projects
python3 cli.py list-projects

# 3. Test GitHub repository connection and push access
python3 cli.py test-github --project-id 1

# 4. Trigger an immediate article generation & publication
python3 cli.py publish --project-id 1

# 5. Generate draft only without committing to GitHub
python3 cli.py publish --project-id 1 --draft-only

# 6. Configure global settings (e.g., GitHub Token, Gemini Key)
python3 cli.py set-config --key github_token --value "ghp_yourTokenHere"
python3 cli.py set-config --key gemini_api_key --value "AIzaSy..."
```

---

## 🔌 How to Plug GitPulse into Any GitHub Project

### Method A: Central CMS Connector (Zero Repo Setup)

1. Open the GitPulse Web Dashboard at `http://localhost:8420`.
2. Navigate to **Settings** and enter your GitHub Personal Access Token (`repo` scope or Fine-Grained token with Read/Write to `Contents` and `Pull requests`).
3. Click **Connect Repository** and provide:
   - **Repository:** `owner/repo-name` (e.g. `acme/dev-portal`)
   - **Framework:** Select Next.js, Astro, Hugo, Jekyll, or Docusaurus (GitPulse auto-populates directory and frontmatter).
   - **Publishing Mode:** Choose `Pull Request` (for review) or `Direct Commit` (instant live publish).
   - **Niche & Topic:** Specify your domain (e.g., *DevOps, Kubernetes, Terraform, Cloud Cost*).
   - **Daily Schedule:** Specify your target publishing time in UTC (e.g., `09:00`).
4. That's it! GitPulse will autonomously publish fresh daily content according to schedule.

---

### Method B: Drop-in GitHub Action Workflow

If you prefer triggering publishing from within the target repository itself, add this file to `.github/workflows/daily-blog.yml` in your target repository:

```yaml
name: GitPulse Daily Blog Automation

on:
  schedule:
    - cron: '0 9 * * *' # Runs daily at 09:00 UTC
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  publish-daily-blog:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Trigger GitPulse Publishing Engine
        env:
          CMS_URL: ${{ secrets.GITPULSE_CMS_URL }}
          PROJECT_ID: ${{ secrets.GITPULSE_PROJECT_ID }}
        run: |
          curl -sSL -X POST "${CMS_URL}/api/projects/${PROJECT_ID}/trigger" \
            -H "Content-Type: application/json" \
            -d '{"force_publish": true}'
```

---

## 📁 Framework Directory Conventions

| Framework | Default Directory | File Extension | Frontmatter Schema |
| :--- | :--- | :--- | :--- |
| **Next.js** | `content/posts/` | `.mdx` | `title`, `description`, `date`, `author`, `tags`, `coverImage` |
| **Astro** | `src/content/blog/` | `.md` | `title`, `description`, `pubDate`, `heroImage`, `tags`, `draft` |
| **Hugo** | `content/posts/` | `.md` | `title`, `date`, `draft: false`, `tags`, `summary` |
| **Jekyll** | `_posts/` | `.md` | `layout: post`, `title`, `date`, `categories`, `excerpt` *(with `YYYY-MM-DD-slug.md` naming)* |
| **Docusaurus**| `blog/` | `.md` | `slug`, `title`, `authors`, `tags`, `date` |
| **Generic** | `content/blog/` | `.md` | Fully customizable template placeholders |

---

## 📡 REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/status` | `GET` | Health check, scheduler status, repo count, published metrics |
| `/api/projects` | `GET` | List all registered repositories |
| `/api/projects` | `POST` | Register a new repository with topic and schedule |
| `/api/projects/<id>` | `GET` / `PUT` / `DELETE` | Retrieve, update, or remove repository configuration |
| `/api/projects/<id>/trigger` | `POST` | Run immediate topic ideation, article generation, and publication |
| `/api/projects/<id>/test-github`| `POST` | Validate GitHub authentication and repository push access |
| `/api/posts` | `GET` | Query generated and published blog posts (`?project_id=X`) |
| `/api/posts/<id>` | `GET` | View full post details, frontmatter, Markdown body, and PR URL |
| `/api/posts/<id>/publish` | `POST` | Dispatch publication of a draft post to GitHub |
| `/api/logs` | `GET` | Retrieve real-time activity and generation audit logs |
| `/api/settings` | `GET` / `POST` | Retrieve or update global API keys and configuration |
| `/api/presets` | `GET` | Retrieve frontmatter and directory presets for frameworks |

---

## 🧪 Testing

Run the automated test suite covering database operations, formatters, topic planning, AI generator, simulated GitHub PR workflows, and REST API routing:

```bash
python3 tests/test_engine.py
```

All 10 tests execute in under 0.05 seconds with zero external dependencies.

---

## 🛡️ License

MIT License. Built for modern software engineering teams and technical blogs.

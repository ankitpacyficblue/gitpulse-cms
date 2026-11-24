"""
GitPulse CMS - Web Dashboard & Authentication Template Renderer
Serves the responsive single-page management dashboard and secure login view.
"""

def render_login_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In - GitPulse CMS</title>
    <link rel="stylesheet" href="/static/css/dashboard.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4">
    <div class="w-full max-w-md">
        <!-- Brand Header -->
        <div class="text-center mb-8">
            <div class="w-12 h-12 rounded-xl bg-gradient-to-tr from-indigo-500 to-cyan-400 flex items-center justify-center font-bold text-xl text-white shadow-lg shadow-indigo-500/25 mx-auto mb-3">
                GP
            </div>
            <h1 class="text-2xl font-bold tracking-tight text-white">GitPulse CMS</h1>
            <p class="text-sm text-slate-400 mt-1">Autonomous Multi-Repo Blog Publishing Engine</p>
        </div>

        <!-- Login Card -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl relative overflow-hidden">
            <div class="mb-6">
                <h2 class="text-lg font-semibold text-white">Sign In to Dashboard</h2>
                <p class="text-xs text-slate-400 mt-0.5">Enter your administrative credentials to continue.</p>
            </div>

            <!-- Error / Lockout Banner -->
            <div id="login-error-banner" class="hidden mb-4 p-3 rounded-lg border text-xs flex items-start gap-2 bg-red-500/10 border-red-500/30 text-red-300">
                <svg class="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                <div id="login-error-text">Invalid username or password.</div>
            </div>

            <!-- Lockout Countdown Banner -->
            <div id="lockout-banner" class="hidden mb-4 p-3 rounded-lg border text-xs flex items-start gap-2 bg-amber-500/10 border-amber-500/30 text-amber-300">
                <svg class="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                <div>
                    <strong>Malicious Login Protection Active:</strong>
                    <div id="lockout-text">Account locked due to consecutive failed attempts.</div>
                </div>
            </div>

            <form id="login-form" onsubmit="handleLoginSubmit(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Username</label>
                    <input type="text" id="login-username" required class="input-text" placeholder="admin" autofocus autocomplete="username">
                </div>

                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Password</label>
                    <div class="relative">
                        <input type="password" id="login-password" required class="input-text pr-10" placeholder="••••••••••••" autocomplete="current-password">
                        <button type="button" onclick="togglePasswordVisibility()" class="absolute right-3 top-2.5 text-slate-400 hover:text-slate-200 text-xs">
                            <span id="eye-icon">Show</span>
                        </button>
                    </div>
                </div>

                <!-- 2FA TOTP Field (Shown when 2FA is active) -->
                <div id="totp-container" class="hidden">
                    <label class="block text-xs font-medium text-indigo-300 mb-1">2-Factor Authentication Code (6 Digits)</label>
                    <input type="text" id="login-totp" maxlength="6" class="input-text font-mono text-center tracking-widest text-lg" placeholder="000000" autocomplete="one-time-code">
                    <p class="text-[11px] text-slate-400 mt-1">Enter the 6-digit verification code from your authenticator app.</p>
                </div>

                <button type="submit" id="login-btn" class="w-full btn-primary py-2.5 text-sm font-semibold flex items-center justify-center gap-2 mt-2">
                    <span id="btn-text">Authenticate & Continue</span>
                </button>
            </form>

            <!-- Initial Credentials Helper Notice -->
            <div class="mt-6 p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-[11px] text-slate-400 space-y-1">
                <div class="text-indigo-400 font-semibold flex items-center gap-1">
                    <span>🔑 Initial Setup Credentials</span>
                </div>
                <div>Username: <code class="text-slate-200">admin</code></div>
                <div>Password: <code class="text-slate-200">GitPulse@Admin2026!</code></div>
                <div class="text-[10px] text-slate-500 pt-1">You can change your password inside Settings after logging in.</div>
            </div>

            <!-- Security Footprint -->
            <div class="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-500">
                <span class="flex items-center gap-1">🛡️ Rate-Limit Protected</span>
                <span>PBKDF2-HMAC-256</span>
                <span>Strict Cookie</span>
            </div>
        </div>
    </div>

    <script>
        function togglePasswordVisibility() {
            const input = document.getElementById('login-password');
            const icon = document.getElementById('eye-icon');
            if (input.type === 'password') {
                input.type = 'text';
                icon.innerText = 'Hide';
            } else {
                input.type = 'password';
                icon.innerText = 'Show';
            }
        }

        async function handleLoginSubmit(e) {
            e.preventDefault();
            const btn = document.getElementById('login-btn');
            const btnText = document.getElementById('btn-text');
            const errBanner = document.getElementById('login-error-banner');
            const errText = document.getElementById('login-error-text');
            const lockBanner = document.getElementById('lockout-banner');
            const lockText = document.getElementById('lockout-text');

            errBanner.classList.add('hidden');
            lockBanner.classList.add('hidden');
            btn.disabled = true;
            btnText.innerText = 'Verifying...';

            const username = document.getElementById('login-username').value;
            const password = document.getElementById('login-password').value;
            const totpCode = document.getElementById('login-totp').value;

            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, totp_code: totpCode })
                });
                const data = await res.json();

                if (res.ok && data.token) {
                    btnText.innerText = 'Success! Redirecting...';
                    window.location.href = '/';
                } else if (data.requires_2fa) {
                    btn.disabled = false;
                    btnText.innerText = 'Verify 2FA Code & Sign In';
                    document.getElementById('totp-container').classList.remove('hidden');
                    document.getElementById('login-username').disabled = true;
                    document.getElementById('login-password').disabled = true;
                    document.getElementById('login-totp').focus();
                } else {
                    btn.disabled = false;
                    btnText.innerText = 'Authenticate & Continue';

                    if (data.locked) {
                        lockBanner.classList.remove('hidden');
                        lockText.innerText = data.error || 'Account temporarily locked out due to repeated failed logins.';
                    } else {
                        errBanner.classList.remove('hidden');
                        errText.innerText = data.error || 'Invalid username or password.';
                    }
                }
            } catch (err) {
                btn.disabled = false;
                btnText.innerText = 'Authenticate & Continue';
                errBanner.classList.remove('hidden');
                errText.innerText = 'Connection error: ' + err.message;
            }
        }
    </script>
</body>
</html>
"""

def render_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitPulse CMS - Automated Multi-Project GitHub Blog Engine</title>
    <link rel="stylesheet" href="/static/css/dashboard.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body class="bg-slate-950 text-slate-100">
    <!-- Top Navigation Bar -->
    <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-500 to-cyan-400 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/20">
                    GP
                </div>
                <div>
                    <div class="flex items-center space-x-2">
                        <span class="font-bold text-lg tracking-tight">GitPulse CMS</span>
                        <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Daemon Active
                        </span>
                    </div>
                    <p class="text-xs text-slate-400">Autonomous Multi-Repo Daily Blog Publisher</p>
                </div>
            </div>

            <!-- Header Actions & User Session -->
            <div class="flex items-center space-x-3">
                <button onclick="openAddProjectModal()" class="btn-primary flex items-center space-x-1.5 text-sm">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                    <span>Connect Repository</span>
                </button>

                <div class="h-6 w-px bg-slate-800 mx-1"></div>

                <div class="flex items-center space-x-2 bg-slate-950/60 px-2.5 py-1.5 rounded-lg border border-slate-800 text-xs">
                    <span class="w-2 h-2 rounded-full bg-indigo-400"></span>
                    <span id="header-username" class="font-medium text-slate-200">admin</span>
                    <span class="text-slate-500">(Admin)</span>
                </div>

                <button onclick="handleLogout()" class="btn-secondary text-xs py-1.5 px-3 text-red-400 hover:text-red-300 hover:bg-red-500/10 border-red-500/20">
                    Sign Out
                </button>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 py-8">
        <!-- Metric Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="metric-card">
                <div class="text-slate-400 text-xs font-medium uppercase tracking-wider">Connected Repos</div>
                <div class="text-2xl font-bold mt-1 text-white" id="stat-repos-count">-</div>
                <div class="text-xs text-indigo-400 mt-1">Multi-framework targets</div>
            </div>
            <div class="metric-card">
                <div class="text-slate-400 text-xs font-medium uppercase tracking-wider">Total Articles</div>
                <div class="text-2xl font-bold mt-1 text-white" id="stat-posts-count">-</div>
                <div class="text-xs text-slate-400 mt-1">Generated & archived</div>
            </div>
            <div class="metric-card">
                <div class="text-slate-400 text-xs font-medium uppercase tracking-wider">Published to GitHub</div>
                <div class="text-2xl font-bold mt-1 text-emerald-400" id="stat-published-count">-</div>
                <div class="text-xs text-emerald-400/80 mt-1">PRs & direct commits</div>
            </div>
            <div class="metric-card">
                <div class="text-slate-400 text-xs font-medium uppercase tracking-wider">Schedule Engine</div>
                <div class="text-2xl font-bold mt-1 text-cyan-400" id="stat-scheduler-status">Active</div>
                <div class="text-xs text-slate-400 mt-1">UTC daily cron interval</div>
            </div>
        </div>

        <!-- Tab Navigation -->
        <div class="flex border-b border-slate-800 space-x-6 mb-6 overflow-x-auto pb-1">
            <button class="nav-tab active" onclick="switchTab('repos')">Connected Projects</button>
            <button class="nav-tab flex items-center gap-1.5" onclick="switchTab('staging')">
                <span>Editorial Staging</span>
                <span id="badge-staging-count" class="text-[10px] px-1.5 py-0.2 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">0</span>
            </button>
            <button class="nav-tab" onclick="switchTab('posts')">Blog Feed & Articles</button>
            <button class="nav-tab flex items-center gap-1.5" onclick="switchTab('zeroredeploy')">
                <span>Zero-Redeploy Setup</span>
                <span class="text-[10px] px-1.5 py-0.2 rounded-full bg-indigo-500/20 text-indigo-300">1-Time Install</span>
            </button>
            <button class="nav-tab" onclick="switchTab('logs')">Activity Logs</button>
            <button class="nav-tab" onclick="switchTab('settings')">Settings & 2FA</button>
        </div>

        <!-- TAB: REPOSITORIES -->
        <div id="tab-repos" class="tab-content">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">Active GitHub Publishing Targets</h2>
                    <p class="text-sm text-slate-400">Each project is scheduled for unique daily topic ideation, AI authoring, and automated commit/PR creation.</p>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" id="projects-grid">
                <!-- Dynamically populated -->
            </div>
        </div>

        <!-- TAB: EDITORIAL STAGING QUEUE -->
        <div id="tab-staging" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">Editorial Staging & Review Queue</h2>
                    <p class="text-sm text-slate-400">Review, edit, and approve AI-generated drafts with live SEO pre-flight scoring before publishing to GitHub.</p>
                </div>
                <button onclick="loadStagingPosts()" class="btn-secondary text-xs">Refresh Queue</button>
            </div>

            <div id="staging-cards-container" class="space-y-4">
                <!-- Dynamically populated -->
            </div>
        </div>

        <!-- TAB: POSTS & ARTICLES -->
        <div id="tab-posts" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">Generated Blog Posts</h2>
                    <p class="text-sm text-slate-400">Review published articles, inspect markdown, and follow GitHub Pull Requests.</p>
                </div>
                <div class="flex space-x-2">
                    <select id="post-filter-project" onchange="loadPosts()" class="input-select text-xs">
                        <option value="">All Repositories</option>
                    </select>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-950/60 border-b border-slate-800 text-xs uppercase text-slate-400">
                        <tr>
                            <th class="px-5 py-3">Article Title & Target Path</th>
                            <th class="px-5 py-3">Repository</th>
                            <th class="px-5 py-3">SEO Score</th>
                            <th class="px-5 py-3">Status</th>
                            <th class="px-5 py-3">GitHub Delivery</th>
                            <th class="px-5 py-3 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="posts-table-body" class="divide-y divide-slate-800">
                        <!-- Dynamically populated -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- TAB: ZERO-REDEPLOY SETUP & PUBLIC API -->
        <div id="tab-zeroredeploy" class="tab-content hidden">
            <div class="max-w-4xl bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
                <div>
                    <h2 class="text-xl font-bold text-white">Zero-Redeploy "One-Time Blog Page" Architecture</h2>
                    <p class="text-sm text-slate-400 mt-1">
                        Connect any GitHub website repo once. GitPulse commits a single dynamic blog page. Future daily posts publish instantly with <strong>ZERO builds, ZERO CI/CD runs, and ZERO redeployments</strong>.
                    </p>
                </div>

                <!-- 1-Click Installer Card -->
                <div class="bg-slate-950 p-5 rounded-xl border border-indigo-500/30 space-y-4">
                    <h3 class="text-base font-semibold text-indigo-300 flex items-center gap-2">
                        <span>⚡ 1-Click GitHub Repository Installer</span>
                    </h3>
                    <p class="text-xs text-slate-400">Select any connected project to commit the standalone dynamic blog page to its repository:</p>

                    <div class="flex flex-col sm:flex-row gap-3 items-center">
                        <select id="zeroredeploy-project-select" class="input-select text-xs flex-1">
                            <!-- Populated dynamically -->
                        </select>
                        <button onclick="installZeroRedeployBlog()" id="btn-install-blog" class="btn-primary text-xs whitespace-nowrap">
                            Install Blog Page to Repository
                        </button>
                    </div>
                    <div id="install-result" class="hidden text-xs p-3 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300"></div>
                </div>

                <!-- Headless Public Endpoints -->
                <div class="space-y-3">
                    <h3 class="text-sm font-semibold text-slate-200">Public Headless Content API Endpoints</h3>
                    <div class="space-y-2 text-xs font-mono">
                        <div class="bg-slate-950 p-3 rounded border border-slate-800 flex justify-between items-center">
                            <span class="text-cyan-400">GET /api/public/projects/{id}/posts</span>
                            <span class="text-slate-500">Paginated JSON feed of published posts</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded border border-slate-800 flex justify-between items-center">
                            <span class="text-cyan-400">GET /api/public/projects/{id}/posts/{slug}</span>
                            <span class="text-slate-500">Full post markdown, frontmatter, & view counter</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded border border-slate-800 flex justify-between items-center">
                            <span class="text-cyan-400">GET /api/public/projects/{id}/posts/{slug}/og-image.svg</span>
                            <span class="text-slate-500">Dynamic 1200x630 OpenGraph hero banner</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded border border-slate-800 flex justify-between items-center">
                            <span class="text-cyan-400">GET /api/public/projects/{id}/rss.xml</span>
                            <span class="text-slate-500">Auto-generated RSS 2.0 XML feed</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB: ACTIVITY LOGS -->
        <div id="tab-logs" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">System & Generation Logs</h2>
                    <p class="text-sm text-slate-400">Real-time audit log of topic planning, AI text generation, authentication attempts, webhooks, and GitHub API transactions.</p>
                </div>
                <button onclick="loadLogs()" class="btn-secondary text-xs">Refresh Logs</button>
            </div>
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-xs max-h-[500px] overflow-y-auto space-y-2" id="logs-container">
                <!-- Dynamically populated -->
            </div>
        </div>

        <!-- TAB: SETTINGS & 2FA -->
        <div id="tab-settings" class="tab-content hidden">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- Global Secrets & AI Provider -->
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-5">
                    <h2 class="text-lg font-semibold text-white">Global Configuration & Tokens</h2>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">GitHub Personal Access Token</label>
                            <input type="password" id="setting-github-token" class="input-text" placeholder="ghp_xxxxxxxxxxxxxxxxxxxx">
                            <p class="text-[11px] text-slate-500 mt-1">Requires <code>repo</code> permissions (or Fine-Grained token with Read & Write to Contents and Pull Requests).</p>
                        </div>

                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">AI Provider Engine</label>
                            <select id="setting-ai-provider" class="input-select">
                                <option value="gemini">Google Gemini (Recommended / Ultra Fast)</option>
                                <option value="openai">OpenAI (GPT-4o / GPT-4o-mini)</option>
                                <option value="local">Built-in Architectural Synthesis (Offline / Zero Token)</option>
                            </select>
                        </div>

                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Google Gemini API Key</label>
                            <input type="password" id="setting-gemini-key" class="input-text" placeholder="AIzaSy...">
                        </div>

                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">OpenAI API Key</label>
                            <input type="password" id="setting-openai-key" class="input-text" placeholder="sk-proj-...">
                        </div>

                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">GitHub Webhook Secret (HMAC-SHA256)</label>
                            <input type="text" id="setting-webhook-secret" class="input-text" placeholder="whsec_xxxxxxxx">
                            <p class="text-[11px] text-slate-500 mt-1">Point GitHub repo webhook to <code>https://&lt;domain&gt;/api/webhook/github</code> (Payload: JSON, Events: Pull Requests).</p>
                        </div>

                        <button onclick="saveSettings()" class="btn-primary text-sm">Save Configuration</button>
                    </div>
                </div>

                <!-- Two-Factor Authentication & Security -->
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-5">
                    <div class="flex justify-between items-center">
                        <h2 class="text-lg font-semibold text-white">Two-Factor Authentication (2FA)</h2>
                        <span id="badge-2fa-status" class="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">Disabled</span>
                    </div>
                    <p class="text-xs text-slate-400">Protect write access to your GitHub repositories by requiring a TOTP code (Google Authenticator, 1Password) at sign-in.</p>

                    <div id="totp-setup-container" class="space-y-3 bg-slate-950 p-4 rounded-lg border border-slate-800 text-xs">
                        <button onclick="initiate2FASetup()" id="btn-setup-2fa" class="btn-secondary text-xs">Set Up Authenticator App</button>
                        
                        <div id="totp-setup-details" class="hidden space-y-3 pt-2">
                            <div>
                                <span class="text-slate-400">Authenticator Secret:</span>
                                <code id="totp-secret-display" class="block font-mono bg-slate-900 p-2 rounded text-indigo-300 select-all mt-1"></code>
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Verify 6-Digit Code:</label>
                                <div class="flex gap-2">
                                    <input type="text" id="totp-verify-input" maxlength="6" class="input-text text-center font-mono text-base tracking-widest w-36" placeholder="000000">
                                    <button onclick="confirmEnable2FA()" class="btn-primary text-xs">Activate 2FA</button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="pt-4 border-t border-slate-800">
                        <h3 class="text-sm font-semibold text-white mb-2">Change Admin Password</h3>
                        <form onsubmit="handleChangePassword(event)" class="space-y-3">
                            <input type="password" id="change-current-pw" required class="input-text" placeholder="Current Password">
                            <input type="password" id="change-new-pw" minlength="8" required class="input-text" placeholder="New Password (Min 8 chars)">
                            <input type="password" id="change-confirm-pw" minlength="8" required class="input-text" placeholder="Confirm New Password">
                            <button type="submit" id="change-pw-btn" class="btn-secondary text-xs">Update Password</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- Post Preview & Markdown Modal -->
    <div id="modal-post" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-4xl">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 class="text-lg font-bold text-white" id="modal-post-title">Article Preview</h3>
                <button onclick="closePostModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label class="text-xs font-medium text-slate-400 uppercase">Frontmatter (YAML)</label>
                    <pre class="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs font-mono text-cyan-300 mt-1 overflow-x-auto max-h-48" id="modal-post-frontmatter"></pre>
                    
                    <label class="text-xs font-medium text-slate-400 uppercase mt-4 block">SEO & Image Prompt</label>
                    <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs text-slate-300 mt-1 space-y-1">
                        <div><strong>Excerpt:</strong> <span id="modal-post-excerpt"></span></div>
                        <div><strong>Image Prompt:</strong> <span id="modal-post-image-prompt" class="italic text-indigo-300"></span></div>
                        <div><strong>Target Path:</strong> <code id="modal-post-path" class="text-emerald-400"></code></div>
                    </div>
                </div>
                <div>
                    <label class="text-xs font-medium text-slate-400 uppercase">Article Markdown</label>
                    <textarea id="modal-post-content" class="w-full bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs font-mono text-slate-200 mt-1 h-96 resize-none focus:outline-none" readonly></textarea>
                </div>
            </div>
        </div>
    </div>

    <!-- Split Screen Editorial Staging Editor Modal -->
    <div id="modal-staging-editor" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-6xl">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <div class="flex items-center gap-3">
                    <h3 class="text-lg font-bold text-white">Editorial Staging & Split Markdown Editor</h3>
                    <span id="editor-seo-badge" class="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">SEO: 100/100</span>
                </div>
                <button onclick="closeStagingEditor()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            
            <input type="hidden" id="edit-post-id">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <!-- Left: Markdown & Metadata Inputs -->
                <div class="space-y-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Title</label>
                        <input type="text" id="edit-post-title" class="input-text text-sm font-semibold" oninput="updateSplitPreview()">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Excerpt / Meta Description</label>
                        <textarea id="edit-post-excerpt" rows="2" class="input-text text-xs resize-none" oninput="updateSplitPreview()"></textarea>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Content Markdown</label>
                        <textarea id="edit-post-markdown" class="w-full bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs font-mono text-slate-200 h-96 resize-none focus:outline-none focus:border-indigo-500" oninput="updateSplitPreview()"></textarea>
                    </div>
                </div>

                <!-- Right: Real-Time Rendered Preview & SEO Issues -->
                <div class="flex flex-col space-y-3">
                    <div id="editor-seo-issues-box" class="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs space-y-1 max-h-24 overflow-y-auto">
                        <span class="text-slate-400 font-semibold">SEO & Brand Safety Guardrails:</span>
                        <div id="editor-issues-list" class="text-[11px] text-slate-400">All checks passed.</div>
                    </div>

                    <div class="flex-1 bg-slate-950 p-4 rounded-lg border border-slate-800 overflow-y-auto max-h-[420px] text-slate-200 text-xs leading-relaxed" id="editor-live-preview">
                        <!-- Rendered Markdown -->
                    </div>
                </div>
            </div>

            <div class="flex justify-between items-center pt-4 border-t border-slate-800 mt-4">
                <button type="button" onclick="closeStagingEditor()" class="btn-secondary text-xs">Close</button>
                <div class="flex gap-2">
                    <button type="button" onclick="saveStagedDraft()" class="btn-secondary text-xs">Save Changes</button>
                    <button type="button" onclick="approveAndPublishStagedPost()" id="btn-approve-post" class="btn-primary text-xs">Approve & Publish to GitHub 🚀</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Add Repository Modal -->
    <div id="modal-add-project" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-2xl">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 class="text-lg font-bold text-white">Connect New GitHub Repository</h3>
                <button onclick="closeAddProjectModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form id="form-add-project" onsubmit="submitAddProject(event)" class="space-y-4">
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Project Name *</label>
                        <input type="text" id="add-name" required class="input-text" placeholder="e.g. Acme Tech Blog">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">GitHub Repo (owner/repo) *</label>
                        <input type="text" id="add-repo" required class="input-text" placeholder="e.g. acme-inc/website">
                    </div>
                </div>

                <div class="grid grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Framework Preset</label>
                        <select id="add-framework" onchange="onFrameworkSelect()" class="input-select">
                            <option value="nextjs">Next.js (MDX / Contentlayer)</option>
                            <option value="astro">Astro (Content Collections)</option>
                            <option value="hugo">Hugo</option>
                            <option value="jekyll">Jekyll / GitHub Pages</option>
                            <option value="docusaurus">Docusaurus</option>
                            <option value="generic">Generic Markdown</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Branch</label>
                        <input type="text" id="add-branch" value="main" class="input-text">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Publishing Mode</label>
                        <select id="add-publishing-mode" class="input-select">
                            <option value="pr">Pull Request (Recommended)</option>
                            <option value="direct">Direct Commit</option>
                        </select>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Content Directory</label>
                        <input type="text" id="add-content-dir" value="content/posts" class="input-text">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Daily Publish Time (UTC)</label>
                        <input type="text" id="add-publish-time" value="09:00" class="input-text" placeholder="HH:MM e.g. 09:00">
                    </div>
                </div>

                <div>
                    <label class="block text-xs font-medium text-slate-400 mb-1">Core Topic & Niche *</label>
                    <textarea id="add-topic" required rows="2" class="input-text resize-none" placeholder="e.g. Distributed database architecture, Raft consensus, vector search, and cloud scalability."></textarea>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Target Audience</label>
                        <input type="text" id="add-audience" value="Senior Backend Engineers & Architects" class="input-text">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Tone of Voice</label>
                        <input type="text" id="add-tone" value="Authoritative, practical, and code-rich" class="input-text">
                    </div>
                </div>

                <div>
                    <label class="block text-xs font-medium text-slate-400 mb-1">Seed Keywords (comma-separated)</label>
                    <input type="text" id="add-keywords" class="input-text" placeholder="databases, distributed systems, golang, performance, storage">
                </div>

                <div class="flex justify-end space-x-3 pt-3 border-t border-slate-800">
                    <button type="button" onclick="closeAddProjectModal()" class="btn-secondary">Cancel</button>
                    <button type="submit" class="btn-primary">Save & Activate</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Notification Toast -->
    <div id="toast" class="toast hidden"></div>

    <script src="/static/js/app.js"></script>
</body>
</html>
"""

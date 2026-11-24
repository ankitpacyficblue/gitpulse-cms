"""
GitPulse CMS - Web Dashboard & Authentication Template Renderer
Serves the responsive single-page management dashboard and secure login view.
"""

from pathlib import Path

_STATIC_CSS_CACHE = None
_STATIC_JS_CACHE = None

def _get_embedded_css() -> str:
    global _STATIC_CSS_CACHE
    if _STATIC_CSS_CACHE is None:
        candidates = [
            Path(__file__).resolve().parent.parent / "static" / "css" / "dashboard.css",
            Path(__file__).resolve().parent.parent / "public" / "static" / "css" / "dashboard.css",
            Path("/var/task/static/css/dashboard.css"),
            Path("/var/task/public/static/css/dashboard.css")
        ]
        for p in candidates:
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        _STATIC_CSS_CACHE = f.read()
                        break
                except Exception:
                    pass
        if _STATIC_CSS_CACHE is None:
            _STATIC_CSS_CACHE = ""
    return _STATIC_CSS_CACHE

def _get_embedded_js() -> str:
    global _STATIC_JS_CACHE
    if _STATIC_JS_CACHE is None:
        candidates = [
            Path(__file__).resolve().parent.parent / "static" / "js" / "app.js",
            Path(__file__).resolve().parent.parent / "public" / "static" / "js" / "app.js",
            Path("/var/task/static/js/app.js"),
            Path("/var/task/public/static/js/app.js")
        ]
        for p in candidates:
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        _STATIC_JS_CACHE = f.read()
                        break
                except Exception:
                    pass
        if _STATIC_JS_CACHE is None:
            _STATIC_JS_CACHE = ""
    return _STATIC_JS_CACHE

def render_login_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In - GitPulse CMS</title>
    <!-- Tailwind CSS Framework CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        slate: {
                            950: '#020617',
                            900: '#0f172a',
                            800: '#1e293b',
                            700: '#334155',
                        }
                    }
                }
            }
        }
    </script>
    <link rel="stylesheet" href="/static/css/dashboard.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
""" + _get_embedded_css() + """
    </style>
    <script>
        (function() {
            try {
                const token = localStorage.getItem('gitpulse_token');
                if (token && !document.cookie.includes('session_token=')) {
                    const isHttps = window.location.protocol === 'https:';
                    document.cookie = `session_token=${encodeURIComponent(token)}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
                }
            } catch (e) {}
        })();
    </script>
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
                    try {
                        localStorage.setItem('gitpulse_token', data.token);
                        const isHttps = window.location.protocol === 'https:';
                        document.cookie = `session_token=${encodeURIComponent(data.token)}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
                    } catch (e) {
                        console.error('Local token store error', e);
                    }
                    setTimeout(() => {
                        window.location.href = '/';
                    }, 50);
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

        document.addEventListener('DOMContentLoaded', async () => {
            try {
                const token = localStorage.getItem('gitpulse_token');
                if (token) {
                    const isHttps = window.location.protocol === 'https:';
                    document.cookie = `session_token=${encodeURIComponent(token)}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
                    const res = await fetch('/api/auth/me', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (res.ok) {
                        const data = await res.json();
                        if (data && data.user) {
                            window.location.href = '/';
                        }
                    } else {
                        localStorage.removeItem('gitpulse_token');
                    }
                }
            } catch (e) {}
        });
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
    <!-- Tailwind CSS Framework CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        slate: {
                            950: '#020617',
                            900: '#0f172a',
                            800: '#1e293b',
                            700: '#334155',
                        }
                    }
                }
            }
        }
    </script>
    <link rel="stylesheet" href="/static/css/dashboard.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
""" + _get_embedded_css() + """
    </style>
    <script>
        (function() {
            try {
                const token = localStorage.getItem('gitpulse_token');
                if (token && !document.cookie.includes('session_token=')) {
                    const isHttps = window.location.protocol === 'https:';
                    document.cookie = `session_token=${encodeURIComponent(token)}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
                }
            } catch (e) {}
        })();
    </script>
</head>
<body class="bg-slate-950 text-slate-100">
    <div class="app-layout">
        <!-- Persistent Left Sidebar Navigation with Clear Sections -->
        <div id="sidebar-backdrop" class="sidebar-backdrop" onclick="toggleSidebar(false)"></div>
        <aside class="sidebar" id="sidebar" aria-label="Main navigation">
            <!-- Sidebar Header & Brand -->
            <div class="p-4 border-b border-slate-800/80">
                <div class="flex items-center space-x-3 mb-3">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-cyan-400 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/25 flex-shrink-0">
                        GP
                    </div>
                    <div class="min-w-0">
                        <div class="flex items-center space-x-1.5">
                            <span class="font-bold text-base tracking-tight text-white">GitPulse</span>
                            <span class="text-[10px] px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold">CMS+CRM</span>
                        </div>
                        <div class="flex items-center gap-1.5 text-[11px] text-emerald-400 mt-0.5">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                            <span>Engine Online</span>
                        </div>
                    </div>
                </div>

                <!-- Multi-Tenant Client Selector -->
                <div class="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800">
                    <div class="flex justify-between items-center mb-1">
                        <label for="client-select-filter" class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Client account</label>
                        <button onclick="openAddClientModal()" class="text-[10px] text-indigo-400 hover:text-indigo-300 font-semibold">+ Add</button>
                    </div>
                    <select id="client-select-filter" onchange="onClientFilterChange()" class="w-full bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 outline-none">
                        <option value="">All accounts (admin view)</option>
                    </select>
                </div>
            </div>

            <!-- Sidebar Navigation Links grouped by clear sections -->
            <div class="sidebar-content">
                <!-- SECTION 1: BLOG & CONTENT ENGINE -->
                <div class="sidebar-section">
                    <div class="sidebar-section-title">
                        <span>📰</span>
                        <span>Blog & Content Engine</span>
                    </div>
                    <a class="sidebar-nav-item active" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('repos')">
                        <span class="flex items-center gap-2">
                            <span>📦</span>
                            <span>Connected Repos</span>
                        </span>
                        <span id="sidebar-badge-repos" class="sidebar-badge bg-slate-800 text-slate-300">-</span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('staging')">
                        <span class="flex items-center gap-2">
                            <span>✍️</span>
                            <span>Editorial Staging</span>
                        </span>
                        <span id="badge-staging-count" class="sidebar-badge bg-amber-500/20 text-amber-300 border border-amber-500/30">0</span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('posts')">
                        <span class="flex items-center gap-2">
                            <span>📑</span>
                            <span>Articles Feed</span>
                        </span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('zeroredeploy')">
                        <span class="flex items-center gap-2">
                            <span>⚡</span>
                            <span>1-Click Blog Embed</span>
                        </span>
                        <span class="sidebar-badge bg-indigo-500/20 text-indigo-300">1-Time</span>
                    </a>
                </div>

                <!-- SECTION 2: WHATSAPP AUTOMATION & CRM (WACRM) -->
                <div class="sidebar-section">
                    <div class="sidebar-section-title">
                        <span>💬</span>
                        <span>WhatsApp CRM & Automation</span>
                    </div>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-inbox')">
                        <span class="flex items-center gap-2">
                            <span>📥</span>
                            <span>Shared Team Inbox</span>
                        </span>
                        <span id="sidebar-badge-inbox" class="sidebar-badge bg-slate-800 text-slate-400">0</span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-contacts')">
                        <span class="flex items-center gap-2">
                            <span>👥</span>
                            <span>Contacts & Audience</span>
                        </span>
                        <span id="sidebar-badge-contacts" class="sidebar-badge bg-slate-800 text-slate-400">0</span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-deals')">
                        <span class="flex items-center gap-2">
                            <span>🎯</span>
                            <span>Sales Pipeline (Kanban)</span>
                        </span>
                        <span id="sidebar-badge-deals" class="sidebar-badge bg-emerald-500/10 text-emerald-400 font-mono">$0</span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-broadcasts')">
                        <span class="flex items-center gap-2">
                            <span>📢</span>
                            <span>Broadcast Campaigns</span>
                        </span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-automations')">
                        <span class="flex items-center gap-2">
                            <span>🤖</span>
                            <span>No-Code Automations</span>
                        </span>
                        <span id="sidebar-badge-automations" class="sidebar-badge bg-indigo-500/20 text-indigo-300">3 live</span>
                    </a>
                </div>

                <!-- SECTION 3: PLATFORM & CLOUD -->
                <div class="sidebar-section">
                    <div class="sidebar-section-title">
                        <span>⚙️</span>
                        <span>Platform & Settings</span>
                    </div>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-config')">
                        <span class="flex items-center gap-2">
                            <span>📱</span>
                            <span>WhatsApp API Setup</span>
                        </span>
                    </a>
                    <a class="sidebar-nav-item" id="nav-users" role="button" tabindex="0" onclick="switchTab('users')" onkeydown="navKey(event,this)">
                        <span class="flex items-center gap-2">
                            <span>👥</span>
                            <span>Users & Roles</span>
                        </span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('supabase')">
                        <span class="flex items-center gap-2">
                            <span>☁️</span>
                            <span>Supabase Cloud DB</span>
                        </span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('logs')">
                        <span class="flex items-center gap-2">
                            <span>📋</span>
                            <span>Activity & Webhook Logs</span>
                        </span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('settings')">
                        <span class="flex items-center gap-2">
                            <span>🛡️</span>
                            <span>Security & 2FA</span>
                        </span>
                    </a>
                </div>
            </div>

            <!-- Sidebar User Profile Footer -->
            <div class="sidebar-footer">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-2 min-w-0">
                        <div class="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-xs text-white">
                            A
                        </div>
                        <div class="min-w-0">
                            <div id="header-username" class="text-xs font-semibold text-white truncate">admin</div>
                            <div class="text-[10px] text-slate-400">Super Administrator</div>
                        </div>
                    </div>
                    <button onclick="handleLogout()" class="text-slate-400 hover:text-red-400 text-xs p-1" title="Sign Out">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                    </button>
                </div>
            </div>
        </aside>

        <!-- Main Content Area -->
        <div class="main-content">
            <!-- Top Action Bar -->
            <header class="top-bar">
                <button type="button" class="menu-toggle" aria-label="Open menu" aria-controls="sidebar" aria-expanded="false" onclick="toggleSidebar()">☰</button>
                <div class="min-w-0 flex-1">
                    <h1 id="view-header-title" class="text-lg font-bold text-white tracking-tight">Connected Projects</h1>
                    <p id="view-header-sub" class="text-xs text-slate-400">Autonomous multi-repo daily blog publishing targets</p>
                </div>

                <div class="flex items-center space-x-2.5">
                    <button onclick="openAddProjectModal()" class="btn-primary flex items-center space-x-1.5 text-xs py-2 px-3 shadow-indigo-500/25">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                        <span>Connect Website in 60s</span>
                    </button>
                    <button onclick="openAddContactModal()" class="btn-secondary text-xs py-2 px-3 flex items-center gap-1 text-emerald-400 hover:text-emerald-300">
                        <span>💬 + New Lead</span>
                    </button>
                    <button onclick="openAddDealModal()" class="btn-secondary text-xs py-2 px-3 flex items-center gap-1 text-indigo-400 hover:text-indigo-300">
                        <span>💰 + Deal</span>
                    </button>
                    <button onclick="openAddBroadcastModal()" class="btn-secondary text-xs py-2 px-3 flex items-center gap-1 text-cyan-400 hover:text-cyan-300">
                        <span>📢 + Broadcast</span>
                    </button>
                </div>
            </header>

            <!-- Dashboard Body -->
            <main class="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto" id="main-content">
                <p class="text-[11px] text-slate-400 mb-3">Working in: <strong id="account-banner-name" class="text-slate-200">All accounts</strong></p>
                <!-- 5 Top Metric Stat Cards -->
                <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
                    <div class="metric-card">
                        <div class="text-slate-400 text-[11px] font-semibold uppercase tracking-wider">Connected Repos</div>
                        <div class="text-xl font-bold mt-1 text-white" id="stat-repos-count">-</div>
                        <div class="text-[10px] text-indigo-400 mt-0.5">Multi-framework targets</div>
                    </div>
                    <div class="metric-card">
                        <div class="text-slate-400 text-[11px] font-semibold uppercase tracking-wider">Published Articles</div>
                        <div class="text-xl font-bold mt-1 text-emerald-400" id="stat-published-count">-</div>
                        <div class="text-[10px] text-emerald-400/80 mt-0.5">GitHub PRs & Commits</div>
                    </div>
                    <div class="metric-card">
                        <div class="text-slate-400 text-[11px] font-semibold uppercase tracking-wider">CRM Contacts</div>
                        <div class="text-xl font-bold mt-1 text-cyan-400" id="stat-contacts-count">-</div>
                        <div class="text-[10px] text-slate-400 mt-0.5">Audience & Leads</div>
                    </div>
                    <div class="metric-card">
                        <div class="text-slate-400 text-[11px] font-semibold uppercase tracking-wider">WhatsApp Chats</div>
                        <div class="text-xl font-bold mt-1 text-indigo-400" id="stat-chats-count">-</div>
                        <div class="text-[10px] text-slate-400 mt-0.5">2-way active threads</div>
                    </div>
                    <div class="metric-card">
                        <div class="text-slate-400 text-[11px] font-semibold uppercase tracking-wider">Pipeline Value</div>
                        <div class="text-xl font-bold mt-1 text-amber-400" id="stat-pipeline-value">-</div>
                        <div class="text-[10px] text-slate-400 mt-0.5">Active sales Kanban</div>
                    </div>
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
            <!-- Supabase Cloud PostgreSQL Database -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4 mb-6">
                <div class="flex justify-between items-center">
                    <div>
                        <h2 class="text-base font-semibold text-white flex items-center gap-2">
                            <span>☁️ Supabase Cloud Database Architecture</span>
                            <span id="badge-supabase-status" class="text-xs px-2.5 py-0.5 rounded-full font-medium bg-slate-800 text-slate-400">Checking...</span>
                        </h2>
                        <p class="text-xs text-slate-400 mt-0.5">Persist articles, multi-client repositories, and system configurations permanently in Supabase PostgreSQL across Vercel serverless runs.</p>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Supabase REST URL</label>
                        <input type="text" id="setting-supabase-url" class="input-text font-mono text-xs" value="https://suvmyyonlqyipzgnmony.supabase.co" placeholder="https://<ref>.supabase.co">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Supabase API Key (Service Role or Anon Key)</label>
                        <input type="password" id="setting-supabase-key" class="input-text font-mono text-xs" placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...">
                        <p class="text-[11px] text-slate-500 mt-1">Project Ref: <code>suvmyyonlqyipzgnmony</code>. Found in Supabase Project Settings -> API.</p>
                    </div>
                </div>

                <div class="flex items-center gap-3 pt-1">
                    <button type="button" onclick="testSupabaseFromUI()" class="btn-secondary text-xs flex items-center gap-1.5">
                        <span>⚡ Test Supabase Connection</span>
                    </button>
                    <button type="button" onclick="syncAllToSupabaseFromUI()" class="btn-secondary text-xs flex items-center gap-1.5 text-indigo-300 border-indigo-500/30">
                        <span>☁️ Sync All Content to Cloud</span>
                    </button>
                    <span id="supabase-test-feedback" class="text-xs font-mono"></span>
                </div>
            </div>

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

        <!-- TAB: WHATSAPP SHARED TEAM INBOX -->
        <div id="tab-wa-inbox" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white flex items-center gap-2">
                        <span>💬 WhatsApp Shared Team Inbox</span>
                        <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1 font-normal">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Meta Cloud API Live
                        </span>
                    </h2>
                    <p class="text-sm text-slate-400">Two-way live threaded messaging, delivery ticks (sent, delivered, read), quick replies, and lead assignment.</p>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="loadWhatsAppInbox()" class="btn-secondary text-xs">🔄 Refresh Chats</button>
                    <button onclick="openAddContactModal()" class="btn-primary text-xs">+ New Lead</button>
                </div>
            </div>

            <!-- Two-Pane Live Chat UI -->
            <div class="chat-container">
                <!-- Left Sidebar: Conversations Threads -->
                <div class="chat-sidebar">
                    <div class="p-3 border-b border-slate-800">
                        <input type="text" id="wa-inbox-search" placeholder="Search conversations..." class="input-text text-xs py-1.5" oninput="loadWhatsAppInbox()">
                    </div>
                    <div id="wa-threads-list" class="chat-thread-list">
                        <!-- Populated dynamically -->
                    </div>
                </div>

                <!-- Right Pane: Active Chat Window -->
                <div class="chat-main">
                    <!-- Active State -->
                    <div id="wa-chat-active-state" class="flex flex-col h-full">
                        <!-- Chat Header -->
                        <div class="p-3.5 border-b border-slate-800 bg-slate-950/60 flex justify-between items-center">
                            <div class="flex items-center space-x-3">
                                <div class="w-9 h-9 rounded-full bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center font-bold text-sm text-indigo-300">
                                    WA
                                </div>
                                <div>
                                    <div class="flex items-center space-x-2">
                                        <h3 id="wa-chat-contact-name" class="font-bold text-sm text-white">Select a contact</h3>
                                        <div id="wa-chat-contact-tags" class="flex gap-1"></div>
                                    </div>
                                    <div id="wa-chat-contact-phone" class="text-xs text-slate-400 font-mono"></div>
                                </div>
                            </div>

                            <div class="flex items-center space-x-2">
                                <button onclick="openAddDealModal(activeConversationId)" class="btn-secondary text-xs py-1 px-2.5 text-indigo-400 hover:text-indigo-300">
                                    💰 + Create Deal
                                </button>
                            </div>
                        </div>

                        <!-- Chat Messages Scroll Feed -->
                        <div id="wa-messages-container" class="chat-messages-scroll">
                            <!-- Populated dynamically -->
                        </div>

                        <!-- Canned Quick Replies -->
                        <div class="px-4 py-2 border-t border-slate-800/80 bg-slate-950/40 flex items-center gap-1.5 overflow-x-auto">
                            <span class="text-[10px] text-slate-500 uppercase font-semibold mr-1 flex-shrink-0">Quick Replies:</span>
                            <button type="button" class="quick-chip" onclick="insertCannedReply('Hi! 👋 Thanks for reaching out to GitPulse. How can our autonomous blog publishing and CRM help your company grow?')">👋 Welcome</button>
                            <button type="button" class="quick-chip" onclick="insertCannedReply('Here is our pricing: Starter $49/mo (3 Repos), Pro $149/mo (10 Repos, Unlimited WA CRM). Reply demo to schedule a call!')">📊 Pricing</button>
                            <button type="button" class="quick-chip" onclick="insertCannedReply('We would love to show you the zero-redeploy 1-click blog embed! Are you free for a 15-minute demo this week?')">⚡ 1-Click Embed Demo</button>
                            <button type="button" class="quick-chip" onclick="insertCannedReply('Thanks for your message! Our engineering team has received this and will follow up shortly.')">🙏 Thank You</button>
                        </div>

                        <!-- Message Composer Input -->
                        <form onsubmit="sendWhatsAppReply(event)" class="p-3 border-t border-slate-800 bg-slate-950 flex items-center gap-2">
                            <input type="text" id="wa-message-input" placeholder="Type WhatsApp message (Enter to send)..." class="input-text text-xs flex-1 py-2">
                            <button type="submit" class="btn-primary text-xs py-2 px-4 flex items-center gap-1.5 shadow-indigo-500/30">
                                <span>Send</span>
                                <span>↗</span>
                            </button>
                        </form>
                    </div>

                    <!-- Empty State -->
                    <div id="wa-chat-empty-state" class="hidden flex-1 flex items-center justify-center p-8 text-center">
                        <div class="max-w-sm space-y-3">
                            <div class="w-14 h-14 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-3xl flex items-center justify-center mx-auto text-indigo-400">
                                💬
                            </div>
                            <h3 class="text-base font-bold text-white">Select a WhatsApp Conversation</h3>
                            <p class="text-xs text-slate-400">Choose a thread from the left or test an incoming message using the WhatsApp API Simulator.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB: WHATSAPP CONTACTS & AUDIENCE CRM -->
        <div id="tab-wa-contacts" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">Contacts & Audience CRM</h2>
                    <p class="text-sm text-slate-400">Manage customer audience, customer data platform (CDP) tags, and launch instant 1-click WhatsApp conversations.</p>
                </div>
                <button onclick="openAddContactModal()" class="btn-primary text-xs flex items-center gap-1.5 shadow-emerald-500/20">
                    <span>+ Add New Lead</span>
                </button>
            </div>

            <!-- Filter & Search Toolbar -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 mb-4 flex flex-col sm:flex-row justify-between items-center gap-3">
                <div class="flex items-center gap-2 w-full sm:w-auto flex-1">
                    <input type="text" id="wa-contact-search" placeholder="Search contacts by name, phone, or email..." class="input-text text-xs flex-1" oninput="loadWhatsAppContacts()">
                    <select id="wa-contact-tag-filter" onchange="loadWhatsAppContacts()" class="input-select text-xs w-36">
                        <option value="">All Tags</option>
                        <option value="VIP">VIP</option>
                        <option value="Customer">Customer</option>
                        <option value="Lead">Lead</option>
                        <option value="Trial">Trial</option>
                    </select>
                </div>
                <button onclick="loadWhatsAppContacts()" class="btn-secondary text-xs whitespace-nowrap">Refresh List</button>
            </div>

            <!-- Contacts Table -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-950/60 border-b border-slate-800 text-xs uppercase text-slate-400">
                        <tr>
                            <th class="px-5 py-3">Contact Profile</th>
                            <th class="px-5 py-3">WhatsApp Phone</th>
                            <th class="px-5 py-3">Audience Tags</th>
                            <th class="px-5 py-3">Internal Notes</th>
                            <th class="px-5 py-3 text-right">Quick Actions</th>
                        </tr>
                    </thead>
                    <tbody id="wa-contacts-table-body" class="divide-y divide-slate-800">
                        <!-- Populated dynamically -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- TAB: SALES PIPELINE DEALS KANBAN -->
        <div id="tab-wa-deals" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white flex items-center gap-2">
                        <span>🎯 Sales Pipeline (Deals Kanban)</span>
                        <span id="kanban-pipeline-badge" class="text-xs px-2.5 py-0.5 rounded-full font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">Total Pipeline</span>
                    </h2>
                    <p class="text-sm text-slate-400">Track and advance high-value deals from inbound WhatsApp leads through qualification to closed-won revenue.</p>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="loadWhatsAppDeals()" class="btn-secondary text-xs">🔄 Refresh</button>
                    <button onclick="openAddDealModal()" class="btn-primary text-xs">+ Add Sales Deal</button>
                </div>
            </div>

            <!-- 5-Stage Kanban Board -->
            <div class="kanban-board">
                <!-- Column: Lead -->
                <div class="kanban-col">
                    <div class="flex justify-between items-center pb-2 mb-3 border-b border-slate-800">
                        <span class="text-xs font-bold text-slate-300 uppercase">1. Lead (<span id="kanban-count-lead">0</span>)</span>
                        <span id="kanban-total-lead" class="text-xs font-mono font-bold text-slate-400">$0</span>
                    </div>
                    <div id="kanban-cards-lead" class="space-y-2 flex-1"></div>
                </div>

                <!-- Column: Qualified -->
                <div class="kanban-col">
                    <div class="flex justify-between items-center pb-2 mb-3 border-b border-slate-800">
                        <span class="text-xs font-bold text-cyan-400 uppercase">2. Qualified (<span id="kanban-count-qualified">0</span>)</span>
                        <span id="kanban-total-qualified" class="text-xs font-mono font-bold text-cyan-300">$0</span>
                    </div>
                    <div id="kanban-cards-qualified" class="space-y-2 flex-1"></div>
                </div>

                <!-- Column: Proposal -->
                <div class="kanban-col">
                    <div class="flex justify-between items-center pb-2 mb-3 border-b border-slate-800">
                        <span class="text-xs font-bold text-indigo-400 uppercase">3. Proposal (<span id="kanban-count-proposal">0</span>)</span>
                        <span id="kanban-total-proposal" class="text-xs font-mono font-bold text-indigo-300">$0</span>
                    </div>
                    <div id="kanban-cards-proposal" class="space-y-2 flex-1"></div>
                </div>

                <!-- Column: Negotiation -->
                <div class="kanban-col">
                    <div class="flex justify-between items-center pb-2 mb-3 border-b border-slate-800">
                        <span class="text-xs font-bold text-amber-400 uppercase">4. Negotiation (<span id="kanban-count-negotiation">0</span>)</span>
                        <span id="kanban-total-negotiation" class="text-xs font-mono font-bold text-amber-300">$0</span>
                    </div>
                    <div id="kanban-cards-negotiation" class="space-y-2 flex-1"></div>
                </div>

                <!-- Column: Won -->
                <div class="kanban-col">
                    <div class="flex justify-between items-center pb-2 mb-3 border-b border-slate-800">
                        <span class="text-xs font-bold text-emerald-400 uppercase">5. Closed Won (<span id="kanban-count-won">0</span>)</span>
                        <span id="kanban-total-won" class="text-xs font-mono font-bold text-emerald-300">$0</span>
                    </div>
                    <div id="kanban-cards-won" class="space-y-2 flex-1"></div>
                </div>
            </div>
        </div>

        <!-- TAB: WHATSAPP BROADCAST CAMPAIGNS -->
        <div id="tab-wa-broadcasts" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">Broadcast Campaigns</h2>
                    <p class="text-sm text-slate-400">Dispatch mass WhatsApp announcements, product updates, and newsletters targeted by audience tags.</p>
                </div>
                <button onclick="openAddBroadcastModal()" class="btn-primary text-xs flex items-center gap-1.5 shadow-indigo-500/25">
                    <span>+ New Broadcast Campaign</span>
                </button>
            </div>

            <div id="wa-broadcasts-container" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- Populated dynamically -->
            </div>
        </div>

        <!-- TAB: NO-CODE AUTOMATIONS ENGINE -->
        <div id="tab-wa-automations" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white flex items-center gap-2">
                        <span>🤖 No-Code WhatsApp Automations Engine</span>
                        <span class="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">Event Triggers & Auto-Responders</span>
                    </h2>
                    <p class="text-sm text-slate-400">Automate welcome greetings, keyword auto-replies, and automatic WhatsApp broadcasts whenever blog articles are published.</p>
                </div>
                <button onclick="openAddAutomationModal()" class="btn-primary text-xs flex items-center gap-1.5 shadow-indigo-500/25">
                    <span>+ New Automation Rule</span>
                </button>
            </div>

            <div id="wa-automations-container" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- Populated dynamically -->
            </div>
        </div>

        <!-- TAB: WHATSAPP API & WEBHOOK SETUP -->
        <div id="tab-users" class="tab-content hidden">
            <div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <section class="xl:col-span-2 bg-slate-900 border border-slate-800 rounded-xl shadow-xl" aria-labelledby="users-h">
                    <div class="p-5 border-b border-slate-800 flex flex-wrap justify-between items-center gap-2">
                        <h2 id="users-h" class="text-base font-semibold text-white">People with access to <span id="users-account-name">this account</span></h2>
                        <span id="users-role-note" class="text-[11px] text-slate-400"></span>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm">
                            <thead class="text-[11px] uppercase text-slate-400 bg-slate-950/40"><tr>
                                <th scope="col" class="px-5 py-3">User</th><th scope="col" class="px-5 py-3">Role</th><th scope="col" class="px-5 py-3 text-right">Actions</th>
                            </tr></thead>
                            <tbody id="users-table-body" class="divide-y divide-slate-800"></tbody>
                        </table>
                    </div>
                    <div id="users-empty"></div>
                </section>
                <section id="users-invite-card" class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4" aria-labelledby="invite-h" data-requires="users.manage">
                    <h2 id="invite-h" class="text-base font-semibold text-white">Invite a person</h2>
                    <form onsubmit="submitInviteUser(event)" class="space-y-3">
                        <div>
                            <label for="invite-username" class="block text-xs font-medium text-slate-300 mb-1">Username or email *</label>
                            <input type="text" id="invite-username" required class="input-text text-xs" autocomplete="off">
                        </div>
                        <div>
                            <label for="invite-role" class="block text-xs font-medium text-slate-300 mb-1">Role</label>
                            <select id="invite-role" class="input-text text-xs"></select>
                            <p id="invite-role-help" class="text-[11px] text-slate-500 mt-1"></p>
                        </div>
                        <button type="submit" class="btn-primary text-xs py-2 px-3 w-full">Send invite</button>
                    </form>
                </section>
            </div>
        </div>

        <div id="tab-wa-config" class="tab-content hidden">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- Meta Cloud API Credentials Form -->
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-5">
                    <div class="flex justify-between items-center">
                        <h2 class="text-base font-semibold text-white flex items-center gap-2">
                            <span>📱 Meta WhatsApp Cloud API Credentials</span>
                            <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">Official Graph API v21.0</span>
                        </h2>
                    </div>
                    <p class="text-xs text-slate-400">Configure your official Meta Business Cloud API credentials. Leave tokens set to mock mode for offline simulation.</p>

                    <form onsubmit="saveWhatsAppConfig(event)" class="space-y-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-300 mb-1">Phone Number ID *</label>
                            <input type="text" id="wa-cfg-phone-id" required class="input-text font-mono text-xs" placeholder="e.g. 109876543210123">
                            <p class="text-[11px] text-slate-500 mt-1">Found in Meta App Dashboard -> WhatsApp -> API Setup.</p>
                        </div>

                        <div>
                            <label class="block text-xs font-medium text-slate-300 mb-1">WhatsApp Business Account ID (WABA ID)</label>
                            <input type="text" id="wa-cfg-waba-id" class="input-text font-mono text-xs" placeholder="e.g. 987654321098765">
                        </div>

                        <div>
                            <label class="block text-xs font-medium text-slate-300 mb-1">Permanent System User Access Token *</label>
                            <input type="password" id="wa-cfg-token" autocomplete="new-password" class="input-text font-mono text-xs" placeholder="Paste the access token from Meta">
                            <p class="text-[11px] text-slate-500 mt-1">Permanent Meta Business Token with <code>whatsapp_business_messaging</code> permissions.</p>
                        </div>

                        <div>
                            <label class="block text-xs font-medium text-slate-300 mb-1">Business Display Name</label>
                            <input type="text" id="wa-cfg-biz-name" class="input-text text-xs" placeholder="e.g. GitPulse Business">
                        </div>

                        <div class="pt-2">
                            <button type="submit" class="btn-primary text-xs py-2 px-4 shadow-indigo-500/25">
                                Save WhatsApp Credentials
                            </button>
                        </div>
                    </form>
                </div>

                <!-- Webhook Callback URL & Verify Token + Live Simulator -->
                <div class="space-y-6">
                    <!-- Webhook Callback Box -->
                    <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
                        <h2 class="text-base font-semibold text-white flex items-center gap-2">
                            <span>⚡ Meta Webhook Verification Handshake</span>
                        </h2>
                        <p class="text-xs text-slate-400">Add this endpoint in your Meta App Dashboard under WhatsApp -> Configuration -> Edit Webhook.</p>

                        <div class="space-y-3 text-xs">
                            <div>
                                <label class="block font-medium text-slate-400 mb-1">Callback URL (GET / POST)</label>
                                <div class="flex gap-2">
                                    <input type="text" id="wa-webhook-url-display" readonly value="https://gitpulse-cms.vercel.app/api/webhook/whatsapp" class="input-text font-mono text-xs bg-slate-950 flex-1">
                                    <button type="button" onclick="navigator.clipboard.writeText(document.getElementById('wa-webhook-url-display').value); showToast('Webhook URL copied to clipboard!', 'success')" class="btn-secondary text-xs">Copy</button>
                                </div>
                            </div>

                            <div>
                                <label class="block font-medium text-slate-400 mb-1">Verify Token</label>
                                <div class="flex gap-2">
                                    <input type="text" id="wa-cfg-verify-token" value="gitpulse_webhook_verify" class="input-text font-mono text-xs bg-slate-950 flex-1">
                                    <button type="button" onclick="navigator.clipboard.writeText(document.getElementById('wa-cfg-verify-token').value); showToast('Verify token copied!', 'success')" class="btn-secondary text-xs">Copy</button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Interactive Live WhatsApp Message Simulator -->
                    <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
                        <div class="flex justify-between items-center">
                            <h2 class="text-base font-semibold text-white flex items-center gap-2">
                                <span>🧪 Inbound WhatsApp Simulator</span>
                                <span class="text-xs px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">Test Auto-Responders</span>
                            </h2>
                        </div>
                        <p class="text-xs text-slate-400">Simulate incoming WhatsApp messages from new leads or existing contacts to test auto-responders and live inbox updates instantly.</p>

                        <form onsubmit="simulateIncomingWhatsApp(event)" class="space-y-3">
                            <div class="grid grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Sender Name</label>
                                    <input type="text" id="wa-sim-name" value="Michael Chang" class="input-text text-xs">
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Sender Phone</label>
                                    <input type="text" id="wa-sim-phone" value="+12065554321" class="input-text text-xs font-mono">
                                </div>
                            </div>

                            <div>
                                <label class="block text-xs font-medium text-slate-400 mb-1">Incoming Message Body</label>
                                <div class="flex gap-2">
                                    <input type="text" id="wa-sim-message" value="Hi! Can you share your pricing and schedule a demo?" class="input-text text-xs flex-1">
                                    <button type="submit" class="btn-primary text-xs py-2 px-3 whitespace-nowrap shadow-cyan-500/20">
                                        Test Message
                                    </button>
                                </div>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB: SUPABASE CLOUD DATABASE -->
        <div id="tab-supabase" class="tab-content hidden">
            <div class="max-w-4xl bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
                <div>
                    <h2 class="text-lg font-semibold text-white flex items-center gap-2">
                        <span>☁️ Supabase Cloud Database Architecture</span>
                        <span id="badge-supabase-status" class="text-xs px-2.5 py-0.5 rounded-full font-medium bg-slate-800 text-slate-400">Checking...</span>
                    </h2>
                    <p class="text-sm text-slate-400 mt-1">
                        Persist articles, multi-client repositories, CRM contacts, conversations, deals, and configurations permanently in Supabase PostgreSQL across Vercel serverless runs.
                    </p>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Supabase REST URL</label>
                        <input type="text" id="setting-supabase-url" class="input-text font-mono text-xs" value="https://suvmyyonlqyipzgnmony.supabase.co" placeholder="https://<ref>.supabase.co">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Supabase API Key (Service Role or Anon Key)</label>
                        <input type="password" id="setting-supabase-key" class="input-text font-mono text-xs" placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...">
                        <p class="text-[11px] text-slate-500 mt-1">Project Ref: <code>suvmyyonlqyipzgnmony</code>. Found in Supabase Project Settings -> API.</p>
                    </div>
                </div>

                <div class="flex items-center gap-3 pt-1">
                    <button type="button" onclick="testSupabaseFromUI()" class="btn-secondary text-xs flex items-center gap-1.5">
                        <span>⚡ Test Supabase Connection</span>
                    </button>
                    <button type="button" onclick="syncAllToSupabaseFromUI()" class="btn-secondary text-xs flex items-center gap-1.5 text-indigo-300 border-indigo-500/30">
                        <span>☁️ Sync All Content to Cloud</span>
                    </button>
                    <span id="supabase-test-feedback" class="text-xs font-mono"></span>
                </div>

                <div class="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-2 text-xs text-slate-300">
                    <h4 class="font-semibold text-white">PostgreSQL Multi-Tenant Schema Tables:</h4>
                    <ul class="list-disc list-inside space-y-1 text-slate-400 font-mono text-[11px]">
                        <li><code>public.clients</code> - Multi-tenant business organization scoping</li>
                        <li><code>public.projects</code> - Connected GitHub repositories & automation schedules</li>
                        <li><code>public.posts</code> - AI-generated articles & editorial staging queue</li>
                        <li><code>public.contacts</code> - WhatsApp CRM customer profiles & CDP audience tags</li>
                        <li><code>public.conversations</code> - Live threaded chat sessions & unread counts</li>
                        <li><code>public.messages</code> - Inbound & outbound messages with delivery ticks</li>
                        <li><code>public.deals</code> - Sales Pipeline Kanban stages ($ value & close dates)</li>
                        <li><code>public.broadcasts</code> - Mass WhatsApp campaign performance metrics</li>
                        <li><code>public.automations</code> - No-code event triggers & auto-responders</li>
                    </ul>
                </div>
            </div>
        </div>
    </main>
    </div>
</div>

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

    <!-- Interactive 3-Step Website Connection Wizard (Built for Non-Technical Users) -->
    <div id="modal-add-project" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-2xl">
            <!-- Header -->
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <div>
                    <h3 class="text-lg font-bold text-white flex items-center gap-2">
                        <span>⚡ Connect Your Website</span>
                        <span class="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-normal">3-Step Easy Setup</span>
                    </h3>
                    <p class="text-xs text-slate-400 mt-0.5">Automate daily SEO blog publishing directly into any GitHub project.</p>
                </div>
                <button onclick="closeAddProjectModal()" class="text-slate-400 hover:text-white text-xl leading-none">&times;</button>
            </div>

            <!-- Visual Step Indicator -->
            <div class="wizard-step-bar">
                <div id="step-node-1" class="wizard-step-node active">
                    <span class="wizard-step-number">1</span>
                    <span>Website Platform</span>
                </div>
                <div class="h-0.5 flex-1 bg-slate-800 mx-2"></div>
                <div id="step-node-2" class="wizard-step-node">
                    <span class="wizard-step-number">2</span>
                    <span>GitHub Repo</span>
                </div>
                <div class="h-0.5 flex-1 bg-slate-800 mx-2"></div>
                <div id="step-node-3" class="wizard-step-node">
                    <span class="wizard-step-number">3</span>
                    <span>Topics & Tone</span>
                </div>
            </div>

            <!-- STEP 1: Website Platform Picker -->
            <div id="wizard-step-1" class="space-y-4">
                <div>
                    <div class="text-xs font-semibold text-slate-300 mb-1">What kind of website is this?</div>
                    <p class="text-xs text-slate-400 mb-3">Click your platform and GitPulse will automatically configure file folders and templates for you.</p>
                </div>

                <div class="grid grid-cols-2 gap-3">
                    <div class="wizard-card selected" onclick="selectWizardFramework('nextjs', this)">
                        <div class="check-icon">✓</div>
                        <div class="text-2xl mb-1.5">⚛️</div>
                        <div class="font-bold text-white text-sm">Next.js</div>
                        <div class="text-xs text-slate-400 mt-1">Modern React website. Automatically writes rich MDX to <code>content/posts</code>.</div>
                    </div>

                    <div class="wizard-card" onclick="selectWizardFramework('astro', this)">
                        <div class="check-icon">✓</div>
                        <div class="text-2xl mb-1.5">🚀</div>
                        <div class="font-bold text-white text-sm">Astro</div>
                        <div class="text-xs text-slate-400 mt-1">Superfast content collections. Writes Markdown to <code>src/content/blog</code>.</div>
                    </div>

                    <div class="wizard-card" onclick="selectWizardFramework('generic', this)">
                        <div class="check-icon">✓</div>
                        <div class="text-2xl mb-1.5">🌐</div>
                        <div class="font-bold text-white text-sm">HTML / Simple Website</div>
                        <div class="text-xs text-slate-400 mt-1">Turnkey zero-redeploy blog. Automatically renders live articles without code changes.</div>
                    </div>

                    <div class="wizard-card" onclick="selectWizardFramework('hugo', this)">
                        <div class="check-icon">✓</div>
                        <div class="text-2xl mb-1.5">⚡</div>
                        <div class="font-bold text-white text-sm">Hugo / Jekyll / Docs</div>
                        <div class="text-xs text-slate-400 mt-1">Classic static site or GitHub Pages repo. Writes Markdown to <code>content/posts</code>.</div>
                    </div>
                </div>

                <!-- Hidden inputs maintained automatically for form submission -->
                <input type="hidden" id="wizard-framework" value="nextjs">
                <input type="hidden" id="wizard-content-dir" value="content/posts">
                <input type="hidden" id="wizard-file-ext" value=".mdx">

                <!-- Collapsible technical settings for developers -->
                <details class="text-xs text-slate-400 pt-1">
                    <summary class="cursor-pointer text-indigo-400 hover:text-indigo-300">⚙️ Advanced Folder Settings (Optional)</summary>
                    <div class="grid grid-cols-2 gap-3 mt-2 bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                        <div>
                            <label class="block text-slate-400 mb-1">Target Directory</label>
                            <input type="text" id="wizard-custom-dir" value="content/posts" class="input-text text-xs font-mono" oninput="document.getElementById('wizard-content-dir').value = this.value">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">Branch</label>
                            <input type="text" id="wizard-branch" value="main" class="input-text text-xs font-mono">
                        </div>
                    </div>
                </details>

                <div class="flex justify-end pt-3 border-t border-slate-800">
                    <button type="button" onclick="goToWizardStep(2)" class="btn-primary text-sm flex items-center gap-1.5">
                        <span>Continue to GitHub</span>
                        <span>→</span>
                    </button>
                </div>
            </div>

            <!-- STEP 2: GitHub Repository Linker -->
            <div id="wizard-step-2" class="space-y-4 hidden">
                <div class="space-y-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Business / Client *</label>
                        <div class="flex gap-2">
                            <select id="wizard-client-id" class="input-select text-xs">
                                <option value="">(Select or create business)</option>
                            </select>
                            <button type="button" onclick="openAddClientModal()" class="btn-secondary text-xs whitespace-nowrap">+ Add Client</button>
                        </div>
                    </div>

                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Website Name or Label *</label>
                        <input type="text" id="wizard-name" class="input-text text-sm" placeholder="e.g. Acme Health Blog">
                    </div>

                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">GitHub Repository (owner/repo) *</label>
                        <input type="text" id="wizard-repo" class="input-text text-sm font-mono" placeholder="e.g. your-org/your-website" oninput="resetWizardVerify()">
                        <p class="text-[11px] text-slate-400 mt-1">Format: <code>username/repository</code></p>
                    </div>

                    <!-- 1-Click Token Callout -->
                    <div class="p-3 rounded-lg bg-indigo-950/40 border border-indigo-500/20 text-xs space-y-1.5">
                        <div class="flex items-center justify-between">
                            <span class="font-semibold text-indigo-300 flex items-center gap-1">🔑 GitHub Access Token</span>
                            <a href="https://github.com/settings/tokens/new?scopes=repo&description=GitPulse+CMS" target="_blank" class="text-cyan-400 hover:underline flex items-center gap-0.5">
                                <span>Create Token in 1-Click</span>
                                <span>↗</span>
                            </a>
                        </div>
                        <input type="password" id="wizard-token" class="input-text text-xs" placeholder="ghp_... (Leave blank to use the token saved in Settings)">
                        <p class="text-[10px] text-slate-400">Requires <code>repo</code> permissions to create blog commits or pull requests.</p>
                    </div>

                    <!-- Interactive Live Verify Button & Status Banner -->
                    <div>
                        <button type="button" id="btn-wizard-verify" onclick="verifyWizardGitHub()" class="btn-secondary w-full text-xs py-2 flex items-center justify-center gap-2">
                            <span>⚡ Test Repository Connection</span>
                        </button>
                        <div id="wizard-verify-result" class="hidden mt-2 p-2.5 rounded text-xs"></div>
                    </div>
                </div>

                <div class="flex justify-between pt-3 border-t border-slate-800">
                    <button type="button" onclick="goToWizardStep(1)" class="btn-secondary text-sm">← Back</button>
                    <button type="button" onclick="goToWizardStep(3)" class="btn-primary text-sm flex items-center gap-1.5">
                        <span>Continue to Topics & Tone</span>
                        <span>→</span>
                    </button>
                </div>
            </div>

            <!-- STEP 3: Topic & Autopilot Preferences -->
            <div id="wizard-step-3" class="space-y-4 hidden">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">What should GitPulse write about? *</label>
                    <textarea id="wizard-topic" rows="2" class="input-text text-xs resize-none" placeholder="e.g. Health innovations, intermittent fasting, clinical nutrition, and preventative wellness."></textarea>
                    
                    <!-- Instant Inspiration Chips -->
                    <div class="flex flex-wrap gap-1.5 mt-2">
                        <span class="text-[11px] text-slate-400 mr-1 flex items-center">Inspiration:</span>
                        <span class="inspiration-chip" onclick="applyInspiration('AI & Machine Learning', 'Cutting-edge LLM architectures, agentic AI frameworks, prompt engineering, vector databases, and real-world deployment.')">🤖 AI & LLMs</span>
                        <span class="inspiration-chip" onclick="applyInspiration('SaaS & Startups', 'Product-led growth, churn reduction, MRR scaling, user onboarding, and B2B SaaS architecture.')">🚀 SaaS & Growth</span>
                        <span class="inspiration-chip" onclick="applyInspiration('Health & Wellness', 'Preventative health, evidence-based nutrition, longevity science, fitness routines, and mental wellness.')">🌿 Health & Wellness</span>
                        <span class="inspiration-chip" onclick="applyInspiration('Fintech & Investing', 'Algorithmic trading, personal finance, automated wealth building, index funds, and financial independence.')">📈 Fintech & Finance</span>
                    </div>
                </div>

                <!-- Tone Selector -->
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Writing Tone</label>
                    <input type="hidden" id="wizard-tone" value="Authoritative, practical, and engaging">
                    <div class="grid grid-cols-3 gap-2">
                        <div class="tone-pill selected" onclick="selectTone('Authoritative, practical, and engaging', this)">
                            <div class="font-bold text-white text-xs">👔 Professional</div>
                            <div class="text-[10px] text-slate-400 mt-0.5">Authoritative & clear</div>
                        </div>
                        <div class="tone-pill" onclick="selectTone('Conversational, modern, punchy, and direct', this)">
                            <div class="font-bold text-white text-xs">🚀 Startup Casual</div>
                            <div class="text-[10px] text-slate-400 mt-0.5">Energetic & punchy</div>
                        </div>
                        <div class="tone-pill" onclick="selectTone('Educational, benchmark-driven, step-by-step, and beginner-friendly', this)">
                            <div class="font-bold text-white text-xs">🎓 Educational</div>
                            <div class="text-[10px] text-slate-400 mt-0.5">Step-by-step guides</div>
                        </div>
                    </div>
                </div>

                <!-- Publishing Safety Choice -->
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Publishing Mode</label>
                    <input type="hidden" id="wizard-publishing-mode" value="pr">
                    <div class="grid grid-cols-2 gap-3">
                        <div class="wizard-card selected" onclick="selectPublishMode('pr', this)">
                            <div class="check-icon">✓</div>
                            <div class="font-bold text-white text-xs flex items-center gap-1">🛡️ Review First (Recommended)</div>
                            <div class="text-[11px] text-slate-400 mt-1">Generates articles into your Review Queue so you can review before they go live on GitHub.</div>
                        </div>
                        <div class="wizard-card" onclick="selectPublishMode('direct', this)">
                            <div class="check-icon">✓</div>
                            <div class="font-bold text-white text-xs flex items-center gap-1">⚡ Full Autopilot</div>
                            <div class="text-[11px] text-slate-400 mt-1">Directly commits and publishes articles to your website every day without manual steps.</div>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Daily Publishing Time (UTC)</label>
                        <select id="wizard-publish-time" class="input-select text-xs">
                            <option value="09:00">Morning (09:00 UTC / 2:30 PM IST)</option>
                            <option value="13:00">Midday (13:00 UTC / 6:30 PM IST)</option>
                            <option value="18:00">Evening (18:00 UTC / 11:30 PM IST)</option>
                            <option value="04:00">Early Morning (04:00 UTC / 9:30 AM IST)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Author Name</label>
                        <input type="text" id="wizard-author" value="Editorial Team" class="input-text text-xs">
                    </div>
                </div>

                <div class="flex justify-between pt-3 border-t border-slate-800">
                    <button type="button" onclick="goToWizardStep(2)" class="btn-secondary text-sm">← Back</button>
                    <button type="button" id="btn-wizard-submit" onclick="submitWizardProject()" class="btn-primary text-sm flex items-center gap-1.5 shadow-indigo-500/40">
                        <span>✨ Connect Website & Start Publishing</span>
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal: Add New Business / Client -->
    <div id="modal-add-client" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-md">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 class="text-base font-bold text-white">Add New Client or Business</h3>
                <button onclick="closeAddClientModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddClient(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Business Name *</label>
                    <input type="text" id="new-client-name" required class="input-text" placeholder="e.g. Acme Digital or Fintech Labs">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Contact Email (Optional)</label>
                    <input type="email" id="new-client-email" class="input-text" placeholder="team@business.com">
                </div>
                <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button type="button" onclick="closeAddClientModal()" class="btn-secondary text-xs">Cancel</button>
                    <button type="submit" class="btn-primary text-xs">Save Client</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal: Add WhatsApp Contact / Lead -->
    <div id="modal-add-contact" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-md">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 class="text-base font-bold text-white flex items-center gap-2">
                    <span>👥 Add Contact / Lead</span>
                </h3>
                <button onclick="closeAddContactModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddContact(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Full Name *</label>
                    <input type="text" id="new-contact-name" required class="input-text" placeholder="e.g. Sarah Jenkins">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">WhatsApp Phone (+CountryCode...) *</label>
                    <input type="text" id="new-contact-phone" required class="input-text font-mono" placeholder="e.g. +14155552671">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Email Address (Optional)</label>
                    <input type="email" id="new-contact-email" class="input-text" placeholder="sarah@example.com">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Audience Tags (Comma-separated)</label>
                    <input type="text" id="new-contact-tags" value="Lead" class="input-text" placeholder="e.g. VIP, Customer, Lead, Enterprise">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Notes / Company Context</label>
                    <textarea id="new-contact-notes" rows="2" class="input-text text-xs resize-none" placeholder="Notes on lead source, interest, or requirements..."></textarea>
                </div>
                <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button type="button" onclick="closeAddContactModal()" class="btn-secondary text-xs">Cancel</button>
                    <button type="submit" class="btn-primary text-xs">Save Contact</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal: Add Sales Pipeline Deal -->
    <div id="modal-add-deal" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-md">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 class="text-base font-bold text-white flex items-center gap-2">
                    <span>💰 Add Sales Pipeline Deal</span>
                </h3>
                <button onclick="closeAddDealModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddDeal(event)" class="space-y-4">
                <input type="hidden" id="new-deal-contact-id">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Deal Title *</label>
                    <input type="text" id="new-deal-title" required class="input-text" placeholder="e.g. Enterprise Blog Automation Suite">
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Deal Value ($) *</label>
                        <input type="number" step="100" id="new-deal-value" required class="input-text font-mono" placeholder="4200">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Pipeline Stage</label>
                        <select id="new-deal-stage" class="input-select text-xs">
                            <option value="lead">1. Lead</option>
                            <option value="qualified">2. Qualified</option>
                            <option value="proposal" selected>3. Proposal</option>
                            <option value="negotiation">4. Negotiation</option>
                            <option value="won">5. Closed Won</option>
                        </select>
                    </div>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Expected Close Date</label>
                    <input type="date" id="new-deal-close" class="input-text text-xs">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Deal Notes / Next Action</label>
                    <textarea id="new-deal-notes" rows="2" class="input-text text-xs resize-none" placeholder="Contract sent, awaiting legal review..."></textarea>
                </div>
                <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button type="button" onclick="closeAddDealModal()" class="btn-secondary text-xs">Cancel</button>
                    <button type="submit" class="btn-primary text-xs">Create Deal</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal: New Broadcast Campaign -->
    <div id="modal-add-broadcast" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-lg">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 class="text-base font-bold text-white flex items-center gap-2">
                    <span>📢 New WhatsApp Broadcast Campaign</span>
                </h3>
                <button onclick="closeAddBroadcastModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddBroadcast(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Campaign Name *</label>
                    <input type="text" id="new-broadcast-name" required class="input-text" placeholder="e.g. Black Friday Special & Blog Feature Update">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Target Audience Tag</label>
                    <select id="new-broadcast-tag" class="input-select text-xs">
                        <option value="all">All Contacts</option>
                        <option value="VIP">VIP Contacts</option>
                        <option value="Customer">Current Customers</option>
                        <option value="Lead">Inbound Leads</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Message Template *</label>
                    <textarea id="new-broadcast-template" required rows="4" class="input-text text-xs font-mono resize-none" placeholder="Hi {{name}}! 🚀 Big news from GitPulse: we have just launched..."></textarea>
                    <p class="text-[11px] text-slate-500 mt-1">Available variables: <code>{{name}}</code>, <code>{{phone}}</code></p>
                </div>
                <div class="flex items-center gap-2 pt-1">
                    <input type="checkbox" id="new-broadcast-send-now" class="w-4 h-4 rounded text-indigo-600">
                    <label for="new-broadcast-send-now" class="text-xs text-slate-300 cursor-pointer">Dispatch immediately upon saving</label>
                </div>
                <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button type="button" onclick="closeAddBroadcastModal()" class="btn-secondary text-xs">Cancel</button>
                    <button type="submit" class="btn-primary text-xs">Save Campaign</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal: New No-Code Automation Rule -->
    <div id="modal-add-automation" class="modal-backdrop hidden">
        <div class="modal-dialog max-w-lg">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 class="text-base font-bold text-white flex items-center gap-2">
                    <span>🤖 Create No-Code Automation Rule</span>
                </h3>
                <button onclick="closeAddAutomationModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddAutomation(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Rule Name *</label>
                    <input type="text" id="new-auto-name" required class="input-text" placeholder="e.g. Schedule Demo Auto-Responder">
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Trigger Event *</label>
                        <select id="new-auto-trigger" required class="input-select text-xs">
                            <option value="welcome">Welcome (First inbound message from new lead)</option>
                            <option value="keyword" selected>Keyword Match (Contains trigger keywords)</option>
                            <option value="blog_publish">Blog Publish (Auto-alert when article goes live)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Keywords (Comma-separated)</label>
                        <input type="text" id="new-auto-keyword" class="input-text text-xs" placeholder="e.g. demo, call, talk, meet">
                    </div>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Outbound Reply Message Template *</label>
                    <textarea id="new-auto-template" required rows="4" class="input-text text-xs font-mono resize-none" placeholder="Hey {{name}}! 📅 We would love to show you a demo. Book a time here: https://cal.com/gitpulse or reply with your preferred day!"></textarea>
                    <p class="text-[11px] text-slate-500 mt-1">Variables: <code>{{name}}</code>, <code>{{phone}}</code>, <code>{{title}}</code>, <code>{{url}}</code></p>
                </div>
                <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button type="button" onclick="closeAddAutomationModal()" class="btn-secondary text-xs">Cancel</button>
                    <button type="submit" class="btn-primary text-xs">Create Rule</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Notification Toast -->
    <div id="toast" class="toast hidden"></div>

    <script src="/static/js/app.js"></script>
    <script>
        // Automatic runtime fallback if external script failed to load
        if (typeof initApp !== 'function') {
""" + _get_embedded_js() + """
        }
    </script>
</body>
</html>
"""

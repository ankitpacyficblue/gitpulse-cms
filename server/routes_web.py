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
                    document.cookie = `session_token=${token}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
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
                <p class="text-xs text-slate-400 mt-0.5">Sign in with the username and password from your account owner.</p>
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
                    <input type="text" id="login-username" required class="input-text" placeholder="your username" autofocus autocomplete="username">
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

            <!-- Security Footprint -->
            <div class="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-500">
                <span>Forgot your password? Ask your account owner to reset it.</span>
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

        (function () {
            try {
                const r = sessionStorage.getItem('gitpulse_login_reason');
                if (r) {
                    sessionStorage.removeItem('gitpulse_login_reason');
                    const b = document.getElementById('login-error-banner'), t = document.getElementById('login-error-text');
                    if (b && t) { t.innerText = r; b.classList.remove('hidden'); }
                }
            } catch (e) {}
        })();

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
            const slowTimer = setTimeout(() => { btnText.innerText = 'Still working... the server may be waking up'; }, 5000);
            window.__loginSlow = slowTimer;

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
                        document.cookie = `session_token=${data.token}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
                    } catch (e) {
                        console.error('Local token store error', e);
                    }
                    try { if (data.must_change_password) localStorage.setItem('gitpulse_must_change', '1'); else localStorage.removeItem('gitpulse_must_change'); } catch (e) {}
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
                clearTimeout(window.__loginSlow);
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
                    document.cookie = `session_token=${token}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
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
    <title>GitPulse CMS - Dashboard</title>
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
                    document.cookie = `session_token=${token}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
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
                <div id="account-switch" class="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800">
                    <div class="flex justify-between items-center mb-1">
                        <label for="client-select-filter" class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Client account</label>
                        <button data-platform-admin onclick="openAddClientModal()" class="hidden text-[10px] text-indigo-400 hover:text-indigo-300 font-semibold">+ New account</button>
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
                        <span>Blog</span>
                    </div>
                    <a class="sidebar-nav-item active" id="nav-dashboard" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('dashboard')"><span class="flex items-center gap-2"><span aria-hidden="true">🏠</span><span>Dashboard</span></span></a>
                    <a class="sidebar-nav-item" id="nav-posts" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('posts')"><span class="flex items-center gap-2"><span aria-hidden="true">📝</span><span>Posts</span></span></a>
                    <a class="sidebar-nav-item" id="nav-repos" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('repos')"><span class="flex items-center gap-2"><span aria-hidden="true">🌐</span><span>Websites</span></span></a>
                    <a class="sidebar-nav-item" id="nav-media" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('media')">
                        <span class="flex items-center gap-2"><span aria-hidden="true">🖼️</span><span>Media Library</span></span>
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
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-knowledge')">
                        <span class="flex items-center gap-2"><span aria-hidden="true">📚</span><span>AI Assistant</span></span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-templates')">
                        <span class="flex items-center gap-2"><span aria-hidden="true">🧾</span><span>Message Templates</span></span>
                    </a>
                    <a class="sidebar-nav-item" role="button" tabindex="0" onkeydown="navKey(event,this)" onclick="switchTab('wa-entry')">
                        <span class="flex items-center gap-2"><span aria-hidden="true">🔗</span><span>Entry Links</span></span>
                    </a>
                </div>

                <!-- SECTION 3: PLATFORM & CLOUD -->
                <div class="sidebar-section" id="nav-platform-section">
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
                        <div class="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-xs text-white" id="header-avatar" aria-hidden="true">
                            &nbsp;
                        </div>
                        <div class="min-w-0">
                            <div id="header-username" class="text-xs font-semibold text-white truncate">&nbsp;</div>
                            <div class="text-[10px] text-slate-400">&nbsp;</div>
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
                    <h1 id="view-header-title" class="text-lg font-bold text-white tracking-tight">Dashboard</h1>
                    <p id="view-header-sub" class="text-xs text-slate-400">What needs you, what goes live next, what just went live</p>
                </div>

                <div id="top-actions" class="top-actions flex items-center gap-2">
                    <button data-tabs="repos" onclick="openAddProjectModal()" class="btn-primary text-xs py-2 px-3">Connect website</button>
                    <button data-tabs="wa-contacts" style="display:none" onclick="openAddContactModal()" class="btn-primary text-xs py-2 px-3">+ New lead</button>
                    <button data-tabs="wa-deals" style="display:none" onclick="openAddDealModal()" class="btn-primary text-xs py-2 px-3">+ New deal</button>
                    <button data-tabs="wa-broadcasts" style="display:none" onclick="openAddBroadcastModal()" class="btn-primary text-xs py-2 px-3">+ New broadcast</button>
                </div>
            </header>

            <!-- Dashboard Body -->
            <main class="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto" id="main-content">
                <p class="text-[11px] text-slate-400 mb-3">Working in: <strong id="account-banner-name" class="text-slate-200">All accounts</strong></p>
                <section id="no-account-panel" class="hidden bg-slate-900 border border-slate-800 rounded-xl p-8 text-center" aria-labelledby="no-account-h">
                    <h2 id="no-account-h" class="text-lg font-semibold text-white">Create your first client account</h2>
                    <p class="text-sm text-slate-400 mt-2 mb-5">This screen shows one client's data, and there are no client accounts yet.</p>
                    <button type="button" class="btn-primary" onclick="openAddClientModal()">+ New account</button>
                </section>
                <!-- TAB: REPOSITORIES -->
                <div id="tab-repos" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">Websites</h2>
                    <p class="text-sm text-slate-400">The websites your blog posts are published to.</p>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" id="projects-grid">
                <!-- Dynamically populated -->
            </div>
        </div>

        <div id="tab-dashboard" class="tab-content">
            <div class="rd-toolbar">
                <div><label for="dashboard-account">Account</label><select id="dashboard-account" class="input-select text-sm" onchange="dashboardAccountChanged()"></select></div>
                <button type="button" id="dashboard-new" class="btn-primary text-xs rd-push hidden" onclick="newPost('dashboard')">+ New post</button>
            </div>
            <div id="dashboard-body"><p class="rd-empty" role="status">Loading…</p></div>
        </div>

        <div id="tab-posts" class="tab-content hidden">
            <div class="rd-toolbar">
                <div><label for="posts-account">Account</label><select id="posts-account" class="input-select text-sm" onchange="postsAccountChanged()"></select></div>
                <div><label for="posts-project">Website</label><select id="posts-project" class="input-select text-sm" onchange="postsFilterChanged()"></select></div>
                <div><label for="posts-author">Author or writer</label><select id="posts-author" class="input-select text-sm" onchange="postsFilterChanged()"></select></div>
                <div><label for="posts-from">From</label><input id="posts-from" type="date" class="input-text text-sm" onchange="postsFilterChanged()"></div>
                <div><label for="posts-to">To</label><input id="posts-to" type="date" class="input-text text-sm" onchange="postsFilterChanged()"></div>
                <div><label for="posts-q">Search</label><input id="posts-q" type="search" class="input-text text-sm" placeholder="Title, topic or keyword" oninput="postsSearch()"></div>
                <div class="rd-sort-small"><label for="posts-sort">Sort by</label><select id="posts-sort" class="input-select text-sm" onchange="sortSelected()"><option value="publish_at:asc">Scheduled, soonest first</option><option value="publish_at:desc">Scheduled, latest first</option><option value="published_at:asc">Published, oldest first</option><option value="published_at:desc">Published, newest first</option><option value="updated_at:asc">Updated, oldest first</option><option value="updated_at:desc">Updated, newest first</option><option value="title:asc">Title, A to Z</option><option value="title:desc">Title, Z to A</option></select></div>
                <button type="button" id="posts-clear" class="btn-secondary text-xs hidden" onclick="clearPostFilters()">Clear filters</button>
                <button type="button" id="posts-new" class="btn-primary text-xs rd-push hidden" onclick="newPost('posts')">+ New post</button>
            </div>
            <div id="posts-tabs" class="rd-tabs" role="group" aria-label="Status"></div>
            <div id="posts-state"></div>
            <table id="posts-table" class="rd-table hidden">
                <caption class="sr-only">Posts</caption>
                <thead><tr><th scope="col" data-sort="title"><button type="button" onclick="sortBy('title')">Title <span aria-hidden="true"></span></button></th><th scope="col">Status</th><th scope="col">Website</th><th scope="col">Author</th><th scope="col" data-sort="publish_at"><button type="button" onclick="sortBy('publish_at')">Scheduled <span aria-hidden="true"></span></button></th><th scope="col" data-sort="published_at"><button type="button" onclick="sortBy('published_at')">Published <span aria-hidden="true"></span></button></th><th scope="col" data-sort="updated_at"><button type="button" onclick="sortBy('updated_at')">Updated <span aria-hidden="true"></span></button></th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
                <tbody id="posts-rows"></tbody>
            </table>
            <div id="posts-pages" class="rd-pages"></div>
        </div>

        <div id="tab-logs" class="tab-content hidden">
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">System & Generation Logs</h2>
                    <p class="text-sm text-slate-400">Real-time audit log of topic planning, AI text generation, authentication attempts, webhooks and publishing.</p>
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
                        <p class="text-xs text-slate-400 mt-0.5">Persist articles, client websites, and system configurations permanently in Supabase PostgreSQL across Vercel serverless runs.</p>
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
                    <p class="text-xs text-slate-400">Protect your account by requiring a TOTP code (Google Authenticator, 1Password) at sign-in.</p>

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
            <div class="flex flex-wrap justify-between items-center gap-3 mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white flex items-center gap-2">
                        <span>💬 WhatsApp Shared Team Inbox</span>
                        <span id="wa-mode-badge" class="hidden text-xs px-2 py-0.5 rounded-full border flex items-center gap-1 font-normal"></span>
                    </h2>
                    <p class="text-sm text-slate-400">Two-way threaded WhatsApp messaging for this client account.</p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                    <label class="sr-only" for="wa-assigned-filter">Show conversations</label>
                    <select id="wa-assigned-filter" class="input-select text-xs py-1.5" onchange="loadWhatsAppInbox()">
                        <option value="">All conversations</option>
                        <option value="me">Assigned to me</option>
                        <option value="human">Needs human</option>
                    </select>
                    <button onclick="loadWhatsAppInbox()" class="btn-secondary text-xs">🔄 Refresh Chats</button>
                    <button data-requires="crm.write" onclick="openAddContactModal()" class="btn-primary text-xs">+ New Lead</button>
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
                        <div class="p-3.5 border-b border-slate-800 bg-slate-950/60 flex flex-wrap justify-between items-center gap-2">
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

                            <div class="flex flex-wrap items-center gap-2">
                                <label class="sr-only" for="wa-assign-select">Assign conversation</label>
                                <select id="wa-assign-select" data-requires="crm.write" class="input-select text-xs py-1 min-w-[9rem]" onchange="assignConversation(this.value)"></select>
                                <button data-requires="crm.write" onclick="openAddDealModal(activeConversationId)" class="btn-secondary text-xs py-1 px-2.5 text-indigo-400 hover:text-indigo-300">
                                    💰 + Create Deal
                                </button>
                            </div>
                        </div>

                        <!-- Chat Messages Scroll Feed -->
                        <div id="wa-needs-human" class="hidden flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs text-amber-200 bg-amber-500/10 border-b border-amber-500/30" role="status">
                            <span id="wa-needs-human-text"></span>
                            <button type="button" id="wa-ai-btn" data-requires="crm.write" class="btn-secondary text-xs" onclick="toggleConversationAi()">Resume AI</button>
                        </div>
                        <div id="wa-messages-container" class="chat-messages-scroll">
                            <!-- Populated dynamically -->
                        </div>

                        <!-- Message Composer Input -->
                        <p id="wa-window-note" class="px-3 text-[11px] text-slate-500"></p>
                        <form id="wa-window-closed" class="hidden px-3 py-2 border-t border-slate-800 space-y-2" onsubmit="sendChatTemplate(event)">
                            <p class="text-xs text-amber-200">More than 24 hours since their last message: only an approved template can be sent.</p>
                            <label for="chat-tpl" class="block text-xs font-medium text-slate-300 mb-1">Template</label>
                    <select id="chat-tpl" class="input-select text-xs w-full" onchange="showTemplateFields('chat')"></select>
                    <div id="chat-tpl-vars" class="space-y-2 mt-2"></div>
                    <p id="chat-tpl-preview" class="text-[11px] text-slate-400 mt-1 whitespace-pre-wrap break-words" aria-live="polite"></p>
                            <div id="chat-media-wrap" class="hidden flex flex-wrap items-center gap-2 text-xs text-slate-300">
                                <span data-label></span><button type="button" class="btn-secondary text-xs" onclick="attachMedia('tpl', this.parentElement.dataset.format)">Choose file</button>
                                <span id="tpl-media-name" class="break-all" aria-live="polite"></span><button type="button" id="tpl-media-clear" class="hidden underline" onclick="clearMedia('tpl')">Remove</button>
                            </div>
                            <button type="submit" class="btn-primary text-xs">Send template</button>
                        </form>
                        <div data-requires="crm.write" class="px-3 pt-2 flex flex-wrap items-center gap-2 text-xs text-slate-300 bg-slate-950">
                            <button type="button" class="btn-secondary text-xs" onclick="attachMedia('chat')">Attach file</button>
                            <span id="chat-media-name" class="break-all" aria-live="polite"></span><button type="button" id="chat-media-clear" class="hidden underline" onclick="clearMedia('chat')">Remove</button>
                        </div>
                        <form onsubmit="sendWhatsAppReply(event)" data-requires="crm.write" class="p-3 border-t border-slate-800 bg-slate-950 flex items-center gap-2">
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
                <button data-requires="crm.write" onclick="openAddContactModal()" class="btn-primary text-xs flex items-center gap-1.5 shadow-emerald-500/20">
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

            <div id="cf-filters" class="hidden flex flex-wrap items-end gap-2 mb-3"></div>
            <details id="cf-settings" data-requires="automations.manage" class="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-4">
                <summary class="text-sm font-semibold text-white cursor-pointer">Custom fields</summary>
                <div id="cf-list" class="mt-3 space-y-2"></div>
                <form onsubmit="saveContactField(event)" class="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-2 items-end">
                    <div><label for="cf-name" class="block text-xs text-slate-400 mb-1">Field name</label><input id="cf-name" class="input-text text-sm w-full" required maxlength="60"></div>
                    <div><label for="cf-type" class="block text-xs text-slate-400 mb-1">Type</label><select id="cf-type" class="input-select text-sm w-full" onchange="document.getElementById('cf-options-wrap').classList.toggle('hidden', this.value !== 'select')"><option value="text">Text</option><option value="number">Number</option><option value="date">Date</option><option value="select">Choice list</option></select></div>
                    <div id="cf-options-wrap" class="hidden"><label for="cf-options" class="block text-xs text-slate-400 mb-1">Choices (comma separated)</label><input id="cf-options" class="input-text text-sm w-full"></div>
                    <button type="submit" class="btn-secondary text-xs">Add field</button>
                </form>
            </details>

            <!-- Contacts Table -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-x-auto shadow-xl">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-950/60 border-b border-slate-800 text-xs uppercase text-slate-400">
                        <tr>
                            <th class="px-5 py-3">Contact Profile</th>
                            <th class="px-5 py-3">WhatsApp Phone</th>
                            <th class="px-5 py-3">Audience Tags</th>
                            <th class="px-5 py-3">Lead source</th>
                            <th class="px-5 py-3">Consent</th>
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
                    <button data-requires="crm.write" onclick="openAddDealModal()" class="btn-primary text-xs">+ Add Sales Deal</button>
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
            <p id="wa-bc-viewonly" class="hidden mb-3 text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2" role="note">View only. Your role can read campaigns but not create or send them.</p>
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white">Broadcast Campaigns</h2>
                    <p class="text-sm text-slate-400">Dispatch mass WhatsApp announcements, product updates, and newsletters targeted by audience tags.</p>
                </div>
                <button data-requires="broadcasts.run" onclick="openAddBroadcastModal()" class="btn-primary text-xs flex items-center gap-1.5 shadow-indigo-500/25">
                    <span>+ New Broadcast Campaign</span>
                </button>
            </div>

            <div id="wa-broadcasts-container" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- Populated dynamically -->
            </div>
        </div>

        <!-- TAB: NO-CODE AUTOMATIONS ENGINE -->
        <div id="tab-wa-automations" class="tab-content hidden">
            <p id="wa-auto-viewonly" class="hidden mb-3 text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2" role="note">View only. Your role can read the rules but not change them.</p>
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-white flex items-center gap-2">
                        <span>🤖 No-Code WhatsApp Automations Engine</span>
                        <span class="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">Event Triggers & Auto-Responders</span>
                    </h2>
                    <p class="text-sm text-slate-400">Automate welcome greetings, keyword auto-replies, and automatic WhatsApp broadcasts whenever blog articles are published.</p>
                </div>
                <button data-requires="automations.manage" onclick="openAddAutomationModal()" class="btn-primary text-xs flex items-center gap-1.5 shadow-indigo-500/25">
                    <span>+ New Automation Rule</span>
                </button>
            </div>

            <div id="wa-automations-container" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- Populated dynamically -->
            </div>
        </div>

        <!-- TAB: WHATSAPP API & WEBHOOK SETUP -->
        <div id="tab-wa-knowledge" class="tab-content hidden">
            <p id="ai-viewonly" class="hidden mb-3 text-xs text-amber-200 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2" role="note">View only. Only an owner or admin can change what the AI knows.</p>
            <form id="kb-form" onsubmit="saveKnowledge(event)">
              <fieldset id="kb-fields" class="space-y-4" disabled>
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <label class="flex items-center gap-3 text-sm text-white font-semibold cursor-pointer"><input type="checkbox" id="kb-ai-enabled" class="w-5 h-5"> AI auto-reply to incoming WhatsApp messages</label>
                    <p id="kb-status" class="text-xs text-slate-400 mt-2" role="status">Loading...</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
                    <div><label for="kb-facts" class="block text-xs text-slate-400 mb-1">Business facts</label><p class="text-[11px] text-slate-500 mb-1">What you do, services, opening hours, next step for a customer.</p><textarea id="kb-facts" class="input-text text-sm w-full" rows="6"></textarea></div>
                    <div><label for="kb-locations" class="block text-xs text-slate-400 mb-1">Locations (one per line)</label><textarea id="kb-locations" class="input-text text-sm w-full" rows="3"></textarea></div>
                    <div><label for="kb-tone" class="block text-xs text-slate-400 mb-1">Tone</label><textarea id="kb-tone" class="input-text text-sm w-full" rows="2"></textarea></div>
                    <div><label for="kb-languages" class="block text-xs text-slate-400 mb-1">Languages (one per line)</label><textarea id="kb-languages" class="input-text text-sm w-full" rows="2"></textarea></div>
                    <div><label for="kb-banned" class="block text-xs text-slate-400 mb-1">Claims the AI must never make (one per line)</label><textarea id="kb-banned" class="input-text text-sm w-full" rows="4"></textarea></div>
                    <div><label for="kb-handoff" class="block text-xs text-slate-400 mb-1">Handoff message</label><p class="text-[11px] text-slate-500 mb-1">Sent once when the AI passes the chat to a person.</p><textarea id="kb-handoff" class="input-text text-sm w-full" rows="2"></textarea></div>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-4"><h2 class="text-sm font-semibold text-white mb-2">Questions and answers</h2><div id="kb-faq" class="space-y-3"></div>
                    <button type="button" class="btn-secondary text-xs mt-3" onclick="addFaqRow()">+ Add question</button></div>
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-4"><h2 class="text-sm font-semibold text-white mb-1">Price items</h2><p class="text-[11px] text-slate-500 mb-2">The AI quotes a price only when its box is ticked.</p><div id="kb-prices" class="space-y-2"></div>
                    <button type="button" class="btn-secondary text-xs mt-3" onclick="addPriceRow()">+ Add price item</button></div>
                <button type="submit" class="btn-primary text-xs">Save</button>
              </fieldset>
            </form>
            <form onsubmit="testQuestion(event)" data-requires="ai.manage" class="bg-slate-900 border border-slate-800 rounded-xl p-4 mt-4 space-y-3">
                <h2 class="text-sm font-semibold text-white">Test a question</h2>
                <p class="text-[11px] text-slate-500">Uses the saved settings. Nothing is sent to any customer.</p>
                <div><label for="kb-test-q" class="block text-xs text-slate-400 mb-1">Customer question</label><input id="kb-test-q" class="input-text text-sm w-full" required></div>
                <button type="submit" id="kb-test-btn" class="btn-secondary text-xs">Test</button>
                <div id="kb-test-result" class="text-sm text-slate-200 whitespace-pre-wrap break-words" aria-live="polite"></div>
            </form>
        </div>

        <div id="tab-wa-templates" class="tab-content hidden">
            <div class="flex flex-wrap justify-between items-center gap-3 mb-4">
                <p class="text-xs text-slate-400">Create templates in Meta's WhatsApp Manager, then sync them here. Only approved ones can be sent.</p>
                <button type="button" data-requires="automations.manage" class="btn-primary text-xs" onclick="syncTemplates(this)">Sync from Meta</button>
            </div>
            <div id="tpl-list" class="space-y-3"></div>
        </div>

        <!-- TAB: WHATSAPP API & WEBHOOK SETUP -->
        <div id="tab-wa-entry" class="tab-content hidden">
            <form data-requires="automations.manage" onsubmit="saveEntryLink(event)" class="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-4 space-y-3">
                <h2 class="text-sm font-semibold text-white">New entry link</h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div><label for="entry-source" class="block text-xs text-slate-400 mb-1">Source</label>
                        <select id="entry-source" class="input-select text-sm w-full"><option value="website">Website</option><option value="ad">Ad</option><option value="social">Social</option><option value="other">Other</option></select></div>
                    <div><label for="entry-label" class="block text-xs text-slate-400 mb-1">Label</label><input id="entry-label" class="input-text text-sm w-full" required maxlength="100" placeholder="Website button"></div>
                    <div><label for="entry-code" class="block text-xs text-slate-400 mb-1">Source code (optional)</label><input id="entry-code" class="input-text text-sm w-full" maxlength="40" pattern="[A-Za-z0-9_-]+" placeholder="WEB-HOME"></div>
                    <div><label for="entry-campaign" class="block text-xs text-slate-400 mb-1">Campaign (optional)</label><input id="entry-campaign" class="input-text text-sm w-full" maxlength="100"></div>
                </div>
                <div><label for="entry-message" class="block text-xs text-slate-400 mb-1">Message the customer starts with</label><input id="entry-message" class="input-text text-sm w-full" maxlength="300" placeholder="Hi, I would like to know more."></div>
                <button type="submit" class="btn-primary text-xs">Create link</button>
            </form>
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-4"><h2 class="text-sm font-semibold text-white mb-2">Enquiries by source</h2><div id="entry-counts" class="flex flex-wrap gap-2"></div></div>
            <div id="entry-list" class="space-y-3"></div>
        </div>

        <!-- TAB: WHATSAPP API & WEBHOOK SETUP -->
        <div id="tab-media" class="tab-content hidden">
            <p id="media-not-ready" class="hidden text-sm text-amber-200 mb-3" role="status">File storage is not set up on the server yet, so nothing can be uploaded.</p>
            <div class="flex flex-wrap items-end gap-3 mb-4">
                <div class="flex-1 min-w-[12rem]"><label for="media-search" class="block text-xs text-slate-400 mb-1">Search by name</label><input id="media-search" type="search" class="input-text text-sm w-full" oninput="searchMedia()"></div>
                <div id="media-upload" class="hidden min-w-0">
                    <label for="media-file" class="block text-xs text-slate-400 mb-1">Upload: JPEG, PNG, WebP 5 MB · PDF 20 MB · MP4 16 MB</label>
                    <input id="media-file" type="file" accept="image/jpeg,image/png,image/webp,application/pdf,video/mp4" class="text-xs text-slate-300 max-w-full" onchange="handleUpload(this, 'media', loadMedia)">
                    <progress id="media-progress" class="hidden w-full" max="100" value="0" aria-label="Upload progress"></progress>
                </div>
            </div>
            <div id="media-grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3"></div>
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
                <section id="account-manage-card" class="xl:col-span-3 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-3" aria-labelledby="acct-h" data-requires="account.manage">
                    <h2 id="acct-h" class="text-base font-semibold text-white">Account settings</h2>
                    <form onsubmit="renameAccount(event)" class="flex flex-wrap items-end gap-2">
                        <div class="flex-1 min-w-[12rem]">
                            <label for="acct-name" class="block text-xs font-medium text-slate-300 mb-1">Account name</label>
                            <input type="text" id="acct-name" required class="input-text text-xs">
                        </div>
                        <button type="submit" class="btn-secondary text-xs py-2 px-3">Rename</button>
                        <button type="button" onclick="deleteAccount()" class="btn-secondary text-xs py-2 px-3 text-red-400">Delete account</button>
                    </form>
                    <p class="text-[11px] text-slate-500">Deleting hides the account and its data from everyone. Type the account name to confirm.</p>
                </section>
                <section id="writer-tokens-card" class="hidden xl:col-span-3 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-3" aria-labelledby="tokens-h">
                    <h2 id="tokens-h" class="text-base font-semibold text-white">Writer tokens</h2>
                    <p class="text-xs text-slate-400">For AI writer agents. A token can only upload images and submit drafts. It can never publish: every draft waits for an admin to approve it.</p>
                    <form onsubmit="createWriterToken(event)" class="flex flex-wrap items-end gap-2">
                        <div class="flex-1 min-w-[12rem]"><label for="token-name" class="block text-xs font-medium text-slate-300 mb-1">Writer name</label><input id="token-name" class="input-text text-xs w-full" required maxlength="80" placeholder="e.g. Toby"></div>
                        <div class="min-w-[10rem]"><label for="token-project" class="block text-xs font-medium text-slate-300 mb-1">Default blog project</label><select id="token-project" class="input-select text-xs w-full"></select></div>
                        <button type="submit" class="btn-primary text-xs py-2 px-3">Create token</button>
                    </form>
                    <div id="token-new" class="hidden border border-amber-500/40 rounded-lg p-3 space-y-2" role="status">
                        <label for="token-value" class="block text-xs text-amber-200">Copy this token now. It is shown only once.</label>
                        <input id="token-value" class="input-text text-xs w-full font-mono" readonly>
                        <div class="flex gap-2"><button type="button" class="btn-secondary text-xs" onclick="copyNewToken()">Copy</button><button type="button" class="btn-secondary text-xs" onclick="hideNewToken()">Done</button></div>
                    </div>
                    <ul id="token-list" class="space-y-2"></ul>
                </section>
                <section id="account-keys-card" class="xl:col-span-3 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-3" aria-labelledby="keys-h" data-requires="account.manage">
                    <h2 id="keys-h" class="text-base font-semibold text-white">Blog AI and currency</h2>
                    <p class="text-[11px] text-slate-500">Keys are stored encrypted and never shown again. Leave a field blank to keep what is saved.</p>
                    <form onsubmit="saveAccountSettings(event)" class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                            <label for="set-ai-provider" class="block text-xs font-medium text-slate-300 mb-1">AI provider</label>
                            <select id="set-ai-provider" class="input-text text-xs"><option value="gemini">Gemini</option><option value="openai">OpenAI</option><option value="mock">Built-in template (no key)</option></select>
                            <p id="set-ai-source" class="text-[11px] text-slate-500 mt-1"></p>
                        </div>
                        <div>
                            <label for="set-website" class="block text-xs font-medium text-slate-300 mb-1">Website address</label>
                            <input id="set-website" type="url" class="input-text text-xs w-full" placeholder="https://www.example.com" maxlength="200">
                            <p class="text-[11px] text-slate-500 mt-1">Post links open here, at /blog/&lt;post&gt;.</p>
                        </div>
                        <div>
                            <label for="set-currency" class="block text-xs font-medium text-slate-300 mb-1">Default deal currency</label>
                            <select id="set-currency" class="input-text text-xs"><option value="INR">INR ₹</option><option value="USD">USD $</option><option value="EUR">EUR €</option><option value="GBP">GBP £</option><option value="AED">AED</option></select>
                        </div>
                        <div>
                            <label for="set-ai-key" class="block text-xs font-medium text-slate-300 mb-1">AI API key</label>
                            <input type="password" id="set-ai-key" autocomplete="new-password" class="input-text text-xs font-mono" placeholder="Paste a key">
                            <label class="text-[11px] text-slate-400 flex items-center gap-1 mt-1"><input type="checkbox" id="set-ai-clear"> Remove the saved key</label>
                        </div>
                        <div class="md:col-span-2"><button type="submit" class="btn-primary text-xs py-2 px-3">Save settings</button></div>
                    </form>
                </section>
                <section id="users-invite-card" class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4" aria-labelledby="invite-h" data-requires="users.manage">
                    <h2 id="invite-h" class="text-base font-semibold text-white">Add a person</h2>
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
                        <button type="submit" class="btn-primary text-xs py-2 px-3 w-full">Add to account</button>
                        <p id="invite-result" class="text-[11px] text-slate-300" role="status" aria-live="polite"></p>
                    </form>
                </section>
            </div>
        </div>

        <div id="tab-wa-config" class="tab-content hidden">
            <nav aria-label="WhatsApp setup steps" class="max-w-3xl mb-5">
                <ol id="wa-stepper" class="grid grid-cols-4 gap-2 text-[11px]"></ol>
            </nav>
            <div class="grid grid-cols-1 gap-6 max-w-3xl">
                <!-- Step 1: Meta Cloud API Credentials Form -->
                <div class="wa-step bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-5" data-step="1">
                    <h3 class="text-sm font-semibold text-indigo-300">Step 1 of 4: Credentials</h3>
                    <div class="flex justify-between items-center">
                        <h2 class="text-base font-semibold text-white flex items-center gap-2">
                            <span>📱 Meta WhatsApp Cloud API Credentials</span>
                            <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">Official Graph API v21.0</span>
                            <span id="wa-mock-badge" class="hidden text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30">Mock mode: messages are not sent</span>
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
                            <label for="wa-cfg-app-secret" class="block text-xs font-medium text-slate-300 mb-1">Meta App Secret</label>
                            <input type="password" id="wa-cfg-app-secret" autocomplete="new-password" class="input-text font-mono text-xs" placeholder="Paste the Meta app secret">
                            <p class="text-[11px] text-slate-500 mt-1">Needed to check that incoming messages really come from Meta. Without it they are rejected.</p>
                            <p id="wa-cfg-status" class="text-[11px] text-slate-300 mt-1" role="status"></p>
                        </div>

                        <div>
                            <label class="block text-xs font-medium text-slate-300 mb-1">Business Display Name</label>
                            <input type="text" id="wa-cfg-biz-name" class="input-text text-xs" placeholder="e.g. GitPulse Business">
                        </div>

                        <div class="pt-2">
                            <button type="submit" class="btn-primary text-xs py-2 px-4 shadow-indigo-500/25">
                                Save and continue
                            </button>
                            <button type="button" onclick="waGoStep(2)" id="wa-skip-1" class="hidden btn-secondary text-xs py-2 px-4 ml-2">Already saved: next</button>
                        </div>
                    </form>
                </div>

                <!-- Webhook Callback URL & Verify Token + Live Simulator -->
                <div class="contents">
                    <!-- Step 2: Webhook Callback Box -->
                    <div class="wa-step hidden bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4" data-step="2">
                        <h3 class="text-sm font-semibold text-indigo-300">Step 2 of 4: Connect the webhook in Meta</h3>
                        <h2 class="text-base font-semibold text-white flex items-center gap-2">
                            <span>⚡ Meta Webhook Verification Handshake</span>
                        </h2>
                        <p class="text-xs text-slate-400">Add this endpoint in your Meta App Dashboard under WhatsApp -> Configuration -> Edit Webhook.</p>

                        <div class="space-y-3 text-xs">
                            <div>
                                <label class="block font-medium text-slate-400 mb-1">Callback URL (GET / POST)</label>
                                <div class="flex gap-2">
                                    <input type="text" id="wa-webhook-url-display" readonly value="" class="input-text font-mono text-xs bg-slate-950 flex-1">
                                    <button type="button" onclick="navigator.clipboard.writeText(document.getElementById('wa-webhook-url-display').value); showToast('Webhook URL copied to clipboard!', 'success')" class="btn-secondary text-xs">Copy</button>
                                </div>
                            </div>

                            <div>
                                <label class="block font-medium text-slate-400 mb-1">Verify Token</label>
                                <div class="flex gap-2">
                                    <input type="text" id="wa-cfg-verify-token" readonly placeholder="Created by the server and shown once when you first save" class="input-text font-mono text-xs bg-slate-950 flex-1">
                                    <button type="button" onclick="rotateVerifyToken()" class="btn-secondary text-xs">New token</button>
                                    <button type="button" onclick="navigator.clipboard.writeText(document.getElementById('wa-cfg-verify-token').value); showToast('Verify token copied!', 'success')" class="btn-secondary text-xs">Copy</button>
                                </div>
                            </div>
                        </div>
                        <ol class="text-xs text-slate-300 list-decimal pl-5 space-y-1">
                            <li>In Meta, open your app, then WhatsApp, then Configuration, then Edit webhook.</li>
                            <li>Paste the Callback URL and the Verify token above, then Verify and save.</li>
                            <li>Subscribe to the <code>messages</code> field.</li>
                            <li>Send a WhatsApp message to your business number. This page turns green when Meta reaches us.</li>
                        </ol>
                        <p id="wa-verify-once" class="hidden text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded p-2">This verify token is shown only now. Copy it before you leave this page.</p>
                        <p id="wa-hook-state" class="text-xs text-slate-300" role="status"></p>
                        <div class="flex gap-2 flex-wrap">
                            <button type="button" onclick="waGoStep(1)" class="btn-secondary text-xs">Back</button>
                            <button type="button" onclick="waGoStep(3)" class="btn-primary text-xs">Next: test</button>
                        </div>
                    </div>

                    <!-- Step 3: test -->
                    <div class="wa-step hidden bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4" data-step="3">
                        <h3 class="text-sm font-semibold text-indigo-300">Step 3 of 4: Test the connection</h3>
                        <p class="text-xs text-slate-400">This asks Meta to confirm your Phone Number ID and token. It does not send any message.</p>
                        <div class="flex gap-2 flex-wrap items-center">
                            <button type="button" id="wa-test-btn" onclick="waRunTest()" class="btn-primary text-xs">Run test</button>
                            <span id="wa-test-result" class="text-xs" role="status"></span>
                        </div>
                        <p id="wa-hook-state-3" class="text-xs text-slate-300" role="status"></p>
                        <div class="flex gap-2 flex-wrap">
                            <button type="button" onclick="waGoStep(2)" class="btn-secondary text-xs">Back</button>
                            <button type="button" onclick="waGoStep(4)" class="btn-primary text-xs">Next: finish</button>
                        </div>
                    </div>

                    <!-- Step 4: done -->
                    <div class="wa-step hidden bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4" data-step="4">
                        <h3 class="text-sm font-semibold text-indigo-300">Step 4 of 4: Done</h3>
                        <div id="wa-done-box" class="rounded-lg border p-4 text-sm" role="status"></div>
                        <div class="flex gap-2 flex-wrap">
                            <button type="button" onclick="waGoStep(3)" class="btn-secondary text-xs">Back</button>
                            <button type="button" onclick="refreshWaStatus()" class="btn-secondary text-xs">Check again</button>
                        </div>
                    </div>

                    <!-- Interactive Live WhatsApp Message Simulator -->
                    <div id="wa-sim-card" data-requires="wa.config" class="hidden bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
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
                                    <input type="text" id="wa-sim-name" placeholder="Contact name" class="input-text text-xs">
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Sender Phone</label>
                                    <input type="text" id="wa-sim-phone" placeholder="+countrycode number" class="input-text text-xs font-mono">
                                </div>
                            </div>

                            <div>
                                <label class="block text-xs font-medium text-slate-400 mb-1">Incoming Message Body</label>
                                <div class="flex gap-2">
                                    <input type="text" id="wa-sim-message" placeholder="Message text" class="input-text text-xs flex-1">
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
                        Persist articles, client websites, CRM contacts, conversations, deals, and configurations permanently in Supabase PostgreSQL across Vercel serverless runs.
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
                        <li><code>public.projects</code> - Connected websites and their schedules</li>
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

    <!-- Connect a website: name, address, account -->
    <div id="modal-add-project" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-add-project-heading">
        <div class="modal-dialog max-w-md">
            <h2 id="modal-add-project-heading" class="text-base font-bold text-white mb-3">Connect a website</h2>
            <form onsubmit="submitProject(event)" class="space-y-3">
                <div><label for="project-account" class="block text-xs text-slate-400 mb-1">Account</label><select id="project-account" class="input-select text-sm" required onchange="fillProjectAddress()"></select></div>
                <div><label for="project-name" class="block text-xs text-slate-400 mb-1">Website name</label><input id="project-name" class="input-text text-sm" required maxlength="100" placeholder="Villa blog"></div>
                <div><label for="project-url" class="block text-xs text-slate-400 mb-1">Website address</label><input id="project-url" type="url" class="input-text text-sm" required maxlength="200" placeholder="https://www.example.com">
                    <p class="text-[11px] text-slate-500 mt-1">This website's posts open at /blog/&lt;post&gt; on this address.</p></div>
                <div class="flex flex-wrap justify-end gap-2 pt-1">
                    <button type="button" class="btn-secondary text-xs" onclick="closeAddProjectModal()">Cancel</button>
                    <button type="submit" id="project-save" class="btn-primary text-xs">Connect website</button>
                </div>
            </form>
        </div>
    </div>

    <div id="modal-add-client" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-add-client-heading">
        <div class="modal-dialog max-w-md">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 id="modal-add-client-heading" class="text-base font-bold text-white">New client account</h3>
                <button type="button" aria-label="Close" onclick="closeAddClientModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddClient(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Business Name *</label>
                    <input type="text" id="new-client-name" required class="input-text" placeholder="e.g. Acme Digital or Fintech Labs">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Owner username</label>
                    <input type="text" id="new-client-owner" class="input-text mb-3" placeholder="Existing or new login for the account owner">
                    <label class="block text-xs font-medium text-slate-300 mb-1">Owner email (optional)</label>
                    <input type="email" id="new-client-email" class="input-text" placeholder="team@business.com">
                </div>
                <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button type="button" onclick="closeAddClientModal()" class="btn-secondary text-xs">Cancel</button>
                    <button type="submit" class="btn-primary text-xs">Create account</button>
                </div>
            <p id="new-client-result" class="text-xs text-slate-300 mt-3" role="status" aria-live="polite"></p>
            </form>
        </div>
    </div>

    <!-- Modal: Add WhatsApp Contact / Lead -->
    <div id="modal-add-contact" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-add-contact-heading">
        <div class="modal-dialog max-w-md">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 id="modal-add-contact-heading" class="text-base font-bold text-white flex items-center gap-2">
                    <span>👥 Add Contact / Lead</span>
                </h3>
                <button type="button" aria-label="Close" onclick="closeAddContactModal()" class="text-slate-400 hover:text-white">&times;</button>
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
                <div id="new-contact-custom" class="space-y-2"></div>
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
    <div id="modal-add-deal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-add-deal-heading">
        <div class="modal-dialog max-w-md">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 id="modal-add-deal-heading" class="text-base font-bold text-white flex items-center gap-2">
                    <span>💰 Add Sales Pipeline Deal</span>
                </h3>
                <button type="button" aria-label="Close" onclick="closeAddDealModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddDeal(event)" class="space-y-4">
                <input type="hidden" id="new-deal-contact-id">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Deal Title *</label>
                    <input type="text" id="new-deal-title" required class="input-text" placeholder="e.g. Enterprise Blog Automation Suite">
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label for="new-deal-value" class="block text-xs font-medium text-slate-300 mb-1">Deal value *</label>
                        <div class="flex gap-2">
                            <select id="new-deal-currency" aria-label="Currency" class="input-text text-xs w-24">
                                <option value="INR" selected>INR ₹</option><option value="USD">USD $</option><option value="EUR">EUR €</option><option value="GBP">GBP £</option><option value="AED">AED</option>
                            </select>
                            <input type="number" step="1" min="0" id="new-deal-value" required class="input-text font-mono flex-1" placeholder="45000">
                        </div>
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
    <div id="modal-add-broadcast" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-add-broadcast-heading">
        <div class="modal-dialog max-w-lg">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 id="modal-add-broadcast-heading" class="text-base font-bold text-white flex items-center gap-2">
                    <span>📢 New WhatsApp Broadcast Campaign</span>
                </h3>
                <button type="button" aria-label="Close" onclick="closeAddBroadcastModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddBroadcast(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Campaign Name *</label>
                    <input type="text" id="new-broadcast-name" required class="input-text" placeholder="e.g. Black Friday Special & Blog Feature Update">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Target Audience Tag</label>
                    <select id="new-broadcast-tag" class="input-select text-xs" onchange="updateBroadcastAudience()">
                        <option value="all">All contacts</option>
                    </select>
                    <p id="new-broadcast-count" class="text-[11px] text-slate-400 mt-1" aria-live="polite"></p>
                </div>
                <div>
                    <label for="bc-tpl" class="block text-xs font-medium text-slate-300 mb-1">Approved template *</label>
                    <select id="bc-tpl" class="input-select text-xs w-full" onchange="showTemplateFields('bc')"></select>
                    <div id="bc-tpl-vars" class="space-y-2 mt-2"></div>
                    <p id="bc-tpl-preview" class="text-[11px] text-slate-400 mt-1 whitespace-pre-wrap break-words" aria-live="polite"></p>
                    <div id="bc-media-wrap" class="hidden flex flex-wrap items-center gap-2 text-xs text-slate-300 mt-2">
                        <span data-label></span><button type="button" class="btn-secondary text-xs" onclick="attachMedia('bc', this.parentElement.dataset.format)">Choose file</button>
                        <span id="bc-media-name" class="break-all" aria-live="polite"></span><button type="button" id="bc-media-clear" class="hidden underline" onclick="clearMedia('bc')">Remove</button>
                    </div>
                </div>
                <div class="flex items-center gap-2 pt-1">
                    <input type="checkbox" id="new-broadcast-send-now" class="w-4 h-4 rounded text-indigo-600">
                    <label for="new-broadcast-send-now" class="text-xs text-slate-300 cursor-pointer">Dispatch immediately upon saving</label>
                </div>
                <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button type="button" onclick="closeAddBroadcastModal()" class="btn-secondary text-xs">Cancel</button>
                    <button type="submit" id="new-broadcast-save" class="btn-primary text-xs disabled:opacity-50">Save Campaign</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal: New No-Code Automation Rule -->
    <div id="modal-add-automation" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-add-automation-heading">
        <div class="modal-dialog max-w-lg">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 id="modal-add-automation-heading" class="text-base font-bold text-white flex items-center gap-2">
                    <span>🤖 Create No-Code Automation Rule</span>
                </h3>
                <button type="button" aria-label="Close" onclick="closeAddAutomationModal()" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="submitAddAutomation(event)" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-300 mb-1">Rule Name *</label>
                    <input type="text" id="new-auto-name" required class="input-text" placeholder="e.g. Opening hours reply">
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Trigger Event *</label>
                        <select id="new-auto-trigger" onchange="updateAutomationFields()" required class="input-select text-xs">
                            <option value="welcome">Welcome (First inbound message from new lead)</option>
                            <option value="keyword" selected>Keyword Match (Contains trigger keywords)</option>
                            <option value="blog_publish">Blog Publish (Auto-alert when article goes live)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-300 mb-1">Keywords (Comma-separated)</label>
                        <input type="text" id="new-auto-keyword" class="input-text text-xs" placeholder="e.g. hours, price, book">
                    </div>
                </div>
                <div id="au-tpl-wrap" class="hidden">
                    <label for="au-tpl" class="block text-xs font-medium text-slate-300 mb-1">Approved template *</label>
                    <select id="au-tpl" class="input-select text-xs w-full" onchange="showTemplateFields('au')"></select>
                    <div id="au-tpl-vars" class="space-y-2 mt-2"></div>
                    <p id="au-tpl-preview" class="text-[11px] text-slate-400 mt-1 whitespace-pre-wrap break-words" aria-live="polite"></p>
                </div>
                <div id="au-text-wrap">
                    <label class="block text-xs font-medium text-slate-300 mb-1">Outbound Reply Message Template *</label>
                    <textarea id="new-auto-template" required rows="4" class="input-text text-xs font-mono resize-none" placeholder="Hi {{name}}! Thanks for your message. We will get back to you shortly."></textarea>
                    <p class="text-[11px] text-slate-500 mt-1">Variables: <code>{{name}}</code>, <code>{{phone}}</code>, <code>{{title}}</code>, <code>{{url}}</code></p>
                </div>
                <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button type="button" onclick="closeAddAutomationModal()" class="btn-secondary text-xs">Cancel</button>
                    <button type="submit" class="btn-primary text-xs">Create Rule</button>
                </div>
            </form>
        </div>
    </div>

    <div id="modal-contact-fields" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-contact-fields-h">
        <div class="modal-dialog max-w-lg">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                <h3 id="modal-contact-fields-h" class="text-base font-bold text-white">Contact fields</h3>
                <button type="button" aria-label="Close" onclick="document.getElementById('modal-contact-fields').classList.add('hidden')" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <form onsubmit="saveContactValues(event)" class="space-y-3">
                <div id="edit-contact-custom" class="space-y-2"></div>
                <button type="submit" class="btn-primary text-xs">Save</button>
            </form>
        </div>
    </div>

    <!-- Notification Toast -->
    <div id="toast" class="toast hidden"></div>

    <script src="/static/js/qrcode.js"></script>
    <div id="modal-post" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="plan-form-h">
        <div class="rd-drawer">
            <form id="plan-form" onsubmit="savePlan(event)" class="p-4 space-y-3">
                <h2 id="plan-form-h" class="text-sm font-semibold text-white">Plan a post</h2>
                <p id="plan-form-note" class="text-xs text-amber-200"></p>
                <p id="plan-missing" class="text-xs text-amber-200"></p>
                <p id="plan-rejected" class="hidden text-xs text-red-300 break-words"></p>
                <fieldset id="plan-fields" class="space-y-3">
                    <div><label for="plan-title" class="block text-xs text-slate-400 mb-1">Title</label><input id="plan-title" class="input-text text-sm w-full" required maxlength="200"></div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div><label for="plan-topic" class="block text-xs text-slate-400 mb-1">Topic</label><input id="plan-topic" class="input-text text-sm w-full" maxlength="300"></div>
                        <div><label for="plan-keyword" class="block text-xs text-slate-400 mb-1">Target keyword</label><input id="plan-keyword" class="input-text text-sm w-full" maxlength="100"></div>
                        <div><label for="plan-seo-title" class="block text-xs text-slate-400 mb-1">Search title (empty: the title)</label><input id="plan-seo-title" class="input-text text-sm w-full" maxlength="120"></div>
                        <div><label for="plan-meta" class="block text-xs text-slate-400 mb-1">Meta description</label><input id="plan-meta" class="input-text text-sm w-full" maxlength="300"></div>
                        <div><label for="plan-when" class="block text-xs text-slate-400 mb-1">Publish date and time (India time)</label><input id="plan-when" class="input-text text-sm w-full" type="datetime-local"></div>
                        <div><label for="plan-project" class="block text-xs text-slate-400 mb-1">Website</label><select id="plan-project" class="input-select text-sm w-full"></select></div>
                        <div><label for="plan-assignee" class="block text-xs text-slate-400 mb-1">Assignee</label><select id="plan-assignee" class="input-select text-sm w-full" ></select></div>
                        <div id="plan-writer-wrap" class="hidden"><label for="plan-writer" class="block text-xs text-slate-400 mb-1">AI writer</label><select id="plan-writer" class="input-select text-sm w-full"></select></div>
                    </div>
                    <div><label for="plan-body" class="block text-xs text-slate-400 mb-1">Article (Markdown)</label><textarea id="plan-body" class="input-text text-sm w-full font-mono" rows="10" oninput="previewPlan()"></textarea></div>
                    <div>
                        <div class="flex justify-between items-center gap-2 mb-1"><h3 class="text-xs text-slate-400">Images</h3><button type="button" id="plan-add-image" class="btn-secondary text-xs" onclick="addPlanImage()">Add image</button></div>
                        <ul id="plan-images" class="space-y-2"></ul>
                        <p class="text-[11px] text-slate-500 mt-1">The cover goes at the top. Other images not linked in the text are added at the end.</p>
                    </div>
                </fieldset>
                <details><summary class="text-xs text-indigo-300 cursor-pointer">Preview</summary><div id="plan-preview" class="text-sm text-slate-200 mt-2 break-words"></div></details>
                <p class="text-[11px] text-slate-500">Approved posts publish within 3 hours of the scheduled time, directly to the website.</p>
                <div id="plan-reject-box" class="hidden space-y-2">
                    <label for="plan-reject-note" class="block text-xs text-slate-400">Why is it rejected?</label>
                    <textarea id="plan-reject-note" class="input-text text-sm w-full" rows="2" maxlength="1000"></textarea>
                    <button type="button" class="btn-secondary text-xs" onclick="rejectFromEditor()">Send back</button>
                </div>
                <div class="flex flex-wrap gap-2">
                    <button type="submit" id="plan-save" class="btn-primary text-xs">Save</button>
                    <button type="button" id="plan-draft" class="btn-secondary text-xs" onclick="planAction('draft')">Draft with AI</button>
                    <button type="button" id="plan-submit" class="btn-secondary text-xs" onclick="planAction('submit')">Submit for approval</button>
                    <button type="button" id="plan-approve" class="btn-secondary text-xs text-emerald-300" onclick="planAction('approve')">Approve</button>
                    <button type="button" id="plan-publish-now" class="btn-secondary text-xs text-emerald-300" onclick="planAction('publish-now')">Publish now</button>
                    <button type="button" id="plan-reject" class="btn-secondary text-xs text-red-300" onclick="toggleRejectBox()">Reject</button>
                    <button type="button" id="plan-unpublish" class="btn-secondary text-xs text-red-300" onclick="planAction('unpublish')">Unpublish</button>
                    <button type="button" id="plan-delete" class="btn-secondary text-xs text-red-300" onclick="deletePlan()">Delete</button>
                    <button type="button" class="btn-secondary text-xs" onclick="askClosePost()">Close</button>
                </div>
            </form>
        </div>
    </div>

    <div id="modal-media" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="modal-media-h">
        <div class="modal-dialog max-w-lg">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800 mb-3">
                <h3 id="modal-media-h" class="text-base font-bold text-white">Choose a file</h3>
                <button type="button" aria-label="Close" onclick="closePicker(null)" class="text-slate-400 hover:text-white">&times;</button>
            </div>
            <label for="picker-search" class="sr-only">Search by name</label>
            <input id="picker-search" type="search" class="input-text text-sm w-full mb-2" placeholder="Search by name" oninput="searchPicker()">
            <div id="picker-upload" class="hidden mb-2">
                <label for="picker-file" class="block text-xs text-slate-400 mb-1">Or upload a new file</label>
                <input id="picker-file" type="file" accept="image/jpeg,image/png,image/webp,application/pdf,video/mp4" class="text-xs text-slate-300 max-w-full" onchange="uploadFromPicker(this)">
                <progress id="picker-progress" class="hidden w-full" max="100" value="0" aria-label="Upload progress"></progress>
            </div>
            <div id="picker-grid" class="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[50vh] overflow-y-auto"></div>
        </div>
    </div>

    <script src="/static/js/app.js"></script>
    <script src="/static/js/phase1b.js"></script>
    <script src="/static/js/redesign.js"></script>
    <script>
        // Automatic runtime fallback if external script failed to load
        if (typeof initApp !== 'function') {
""" + _get_embedded_js() + """
        }
    </script>

    <div id="overlay-no-access" role="dialog" aria-modal="true" aria-label="Account access" class="hidden fixed inset-0 z-[100] bg-slate-950 flex items-center justify-center p-6" role="alertdialog" aria-labelledby="noaccess-h">
        <div class="max-w-md text-center space-y-3">
            <h1 id="noaccess-h" class="text-xl font-bold text-white">No access to a client account</h1>
            <p id="noaccess-text" class="text-sm text-slate-400">Your access was removed or has not been set up yet. Ask an account owner to add you.</p>
            <div id="noaccess-actions" class="flex justify-center gap-2">
                <button type="button" class="btn-secondary text-xs py-2 px-3" onclick="handleLogout()">Sign out</button>
            </div>
        </div>
    </div>
    <div id="overlay-change-password" role="dialog" aria-modal="true" aria-labelledby="chpw-h" class="hidden fixed inset-0 z-[100] bg-slate-950 flex items-center justify-center p-6">
        <form onsubmit="submitFirstLoginPassword(event)" class="w-full max-w-sm bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-3">
            <h1 id="chpw-h" class="text-lg font-bold text-white">Choose a new password</h1>
            <p class="text-xs text-slate-400">You signed in with a temporary password. Set your own to continue.</p>
            <label for="chpw-current" class="block text-xs text-slate-300">Temporary password</label>
            <input type="password" id="chpw-current" required autocomplete="current-password" class="input-text text-xs">
            <label for="chpw-new" class="block text-xs text-slate-300">New password (8+ characters)</label>
            <input type="password" id="chpw-new" required minlength="8" autocomplete="new-password" class="input-text text-xs" aria-describedby="chpw-rule">
            <p id="chpw-rule" class="text-[11px] text-slate-500">At least 8 characters. Use a password you do not use elsewhere.</p>
            <label for="chpw-confirm" class="block text-xs text-slate-300">Repeat the new password</label>
            <input type="password" id="chpw-confirm" required minlength="8" autocomplete="new-password" class="input-text text-xs">
            <label class="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" onchange="['chpw-current','chpw-new','chpw-confirm'].forEach(i=>document.getElementById(i).type=this.checked?'text':'password')"> Show passwords</label>
            <p id="chpw-msg" class="text-xs text-red-400" role="alert"></p>
            <button type="submit" class="btn-primary text-xs py-2 px-3 w-full">Save and continue</button>
        </form>
    </div>
</body>
</html>
"""

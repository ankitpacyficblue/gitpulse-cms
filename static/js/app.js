// GitPulse CMS - Frontend Application Controller

let globalPresets = {};
let accountsMode = false;
let currentUser = null;
let currentStagingPost = null;
let generated2FASecret = "";

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    // 0. Ensure session token from localStorage is synced into cookie
    try {
        const token = localStorage.getItem('gitpulse_token');
        if (token && !document.cookie.includes('session_token=')) {
            const isHttps = window.location.protocol === 'https:';
            document.cookie = `session_token=${token}; Path=/; SameSite=Lax; Max-Age=172800${isHttps ? '; Secure' : ''}`;
        }
    } catch (e) {}

    // 1. Verify user session
    const authData = await apiGet('/api/auth/me');
    if (!authData || !authData.user) {
        try { localStorage.removeItem('gitpulse_token'); } catch (e) {}
        window.location.href = '/login';
        return;
    }
    currentUser = authData.user;
    try { window.__perms = authData.permissions || null; } catch (e) {}
    const userEl = document.getElementById('header-username');
    if (userEl) userEl.innerText = currentUser.username;
    const avEl = document.getElementById('header-avatar');
    if (avEl) avEl.innerText = (currentUser.username || '?').charAt(0).toUpperCase();

    // Update 2FA status badge
    const badge2fa = document.getElementById('badge-2fa-status');
    if (badge2fa) {
        if (currentUser.totp_enabled) {
            badge2fa.innerText = "Active (Protected)";
            badge2fa.className = "text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30";
            const btn2fa = document.getElementById('btn-setup-2fa');
            if (btn2fa) btn2fa.innerText = "2FA Already Enabled";
        }
    }

    // First login with a one-time password: ask for a new one before loading anything else.
    if (needsPasswordChange()) { showPasswordChange(); return; }
    // 2. Load Dashboard Components
    await fetchPresets();
    await loadClients();
    await refreshMe();
    if (needsPasswordChange()) { showPasswordChange(); return; }
    if (!window.__accounts || window.__accounts.length === 0 || !getActiveAccountId()) {
        showNoAccess(isPlatformAdmin());
        if (!isPlatformAdmin()) return;
    }
    // Role gating first, so buttons are right even if a later load fails.
    applyRolePermissions();
    const hasAccount = !!getActiveAccountId();
    const loaders = [loadStatus, loadProjects, loadStagingPosts, loadPosts, loadLogs];
    if (hasAccount) loaders.push(loadWhatsAppInbox, loadWhatsAppContacts, loadWhatsAppDeals, loadWhatsAppBroadcasts, loadWhatsAppAutomations, loadWhatsAppConfig, loadAlerts);
    if (isPlatformAdmin()) loaders.push(loadSettings, loadSupabaseStatus);
    // Run in parallel; one failing screen must not blank the rest.
    await Promise.allSettled(loaders.map(f => { try { return Promise.resolve(f()); } catch (e) { return Promise.reject(e); } }));
    applyRolePermissions();
    updateAccountBanner();

    // Auto-refresh metrics, staging queue, and logs every 15 seconds
    setInterval(() => {
        loadStatus();
        loadStagingPosts();
        loadLogs();
        if (activeConversationId) {
            loadConversationMessages(activeConversationId, true);
        }
    }, 15000);
}

// --- Tabs & Sidebar Navigation ---
const TAB_GUARD = {
    'users': () => can('users.manage'),
    'wa-config': () => can('wa.config'),
    'supabase': () => isPlatformAdmin(),
    'settings': () => isPlatformAdmin(),
    'logs': () => can('audit.read'),
    'zeroredeploy': () => can('content.publish'),
    'wa-broadcasts': () => can('crm.read')
};

function switchTab(tabName) {
    if (TAB_GUARD[tabName] && currentUser && !TAB_GUARD[tabName]()) tabName = 'repos';
    const kpi = document.getElementById('kpi-cards');
    if (kpi) kpi.classList.toggle('hidden', tabName !== 'repos');
    if (window.innerWidth <= 900) toggleSidebar(false);
    toggleNewMenu(false);
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.sidebar-nav-item').forEach(el => el.classList.remove('active'));

    const targetTab = document.getElementById(`tab-${tabName}`);
    if (targetTab) targetTab.classList.remove('hidden');

    const clickedNav = Array.from(document.querySelectorAll('.sidebar-nav-item, .nav-tab')).filter(btn => 
        btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(tabName)
    );
    clickedNav.forEach(el => el.classList.add('active'));

    // Dynamic header title update
    const titleMap = {
        'repos': { title: 'Connected Projects', sub: 'Autonomous multi-repo daily blog publishing targets' },
        'staging': { title: 'Editorial Staging & Review', sub: 'Review, edit, and approve AI-generated drafts with live SEO scoring' },
        'posts': { title: 'Published Blog Articles', sub: 'Inspect published posts, live Markdown, and GitHub commits/PRs' },
        'zeroredeploy': { title: 'Zero-Redeploy "One-Time Blog Page"', sub: 'Turnkey dynamic blog embed with zero CI/CD rebuilds' },
        'wa-inbox': { title: 'Shared Team Inbox', sub: 'Two-way WhatsApp conversations for your team' },
        'wa-contacts': { title: 'Contacts & Audience CRM', sub: 'Manage customer profiles, lead tags, and WhatsApp communication history' },
        'wa-deals': { title: 'Sales Pipeline (Kanban)', sub: 'Track and advance deals across qualification, proposals, and closed won' },
        'wa-broadcasts': { title: 'Broadcast Campaigns', sub: 'Mass WhatsApp messaging campaigns segmented by audience tags' },
        'wa-automations': { title: 'No-Code Automations Engine', sub: 'Automated welcome bots, keyword responders, and blog publication alerts' },
        'users': { title: 'Users & Roles', sub: 'Invite people to this client account and control what each role can do' },
        'wa-knowledge': { title: 'AI Assistant', sub: 'What the AI may say to customers of this business' },
        'wa-templates': { title: 'Message Templates', sub: 'Meta-approved messages for contacting customers after 24 hours' },
        'wa-entry': { title: 'Entry Links', sub: 'Website and ad links that open a WhatsApp chat and record where it came from' },
        'blog-plan': { title: 'Blog Schedule', sub: 'Plan, approve and publish posts on their date' },
        'wa-config': { title: 'WhatsApp API & Webhook Setup', sub: 'Four steps: credentials, webhook, test, done' },
        'supabase': { title: 'Supabase Cloud Database', sub: 'PostgreSQL multi-tenant persistence and cloud backup status' },
        'logs': { title: 'System & Generation Logs', sub: 'Real-time audit log of AI generation, GitHub commits, and webhooks' },
        'settings': { title: 'Platform Settings & Security', sub: 'Global API tokens, AI provider keys, TOTP 2FA, and password management' }
    };

    const headerTitleEl = document.getElementById('view-header-title');
    const headerSubEl = document.getElementById('view-header-sub');
    if (headerTitleEl && titleMap[tabName]) headerTitleEl.innerText = titleMap[tabName].title;
    if (headerSubEl && titleMap[tabName]) headerSubEl.innerText = titleMap[tabName].sub;

    if (tabName === 'repos') loadProjects();
    if (tabName === 'staging') loadStagingPosts();
    if (tabName === 'posts') loadPosts();
    if (tabName === 'wa-inbox') loadWhatsAppInbox();
    if (tabName === 'wa-contacts') loadWhatsAppContacts();
    if (tabName === 'wa-deals') loadWhatsAppDeals();
    if (tabName === 'wa-broadcasts') loadWhatsAppBroadcasts();
    if (tabName === 'wa-automations') loadWhatsAppAutomations();
    if (tabName === 'wa-config') loadWhatsAppConfig();
    if (tabName === 'users') loadUsersAndRoles();
    if (tabName === 'wa-knowledge') loadKnowledge();
    if (tabName === 'wa-templates') loadTemplates();
    if (tabName === 'blog-plan') loadPlan();
    if (tabName === 'wa-entry') loadEntryLinks();
    updateAlertsVisibility(tabName);
    if (tabName === 'repos') loadAlerts();
    if (tabName === 'supabase' && isPlatformAdmin()) loadSupabaseStatus();
    if (tabName === 'logs') loadLogs();
    if (tabName === 'settings' && isPlatformAdmin()) loadSettings();
}

// --- Authentication & Session Actions ---
async function handleLogout() {
    if (!confirm('Are you sure you want to sign out?')) return;
    try {
        await apiPost('/api/auth/logout', {});
    } catch (e) {
    } finally {
        try {
            localStorage.removeItem('gitpulse_token');
            document.cookie = "session_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
        } catch (e) {}
        window.location.href = '/login';
    }
}

async function handleChangePassword(e) {
    e.preventDefault();
    const currentPw = document.getElementById('change-current-pw').value;
    const newPw = document.getElementById('change-new-pw').value;
    const confirmPw = document.getElementById('change-confirm-pw').value;
    const btn = document.getElementById('change-pw-btn');

    if (newPw !== confirmPw) {
        showToast('New passwords do not match.', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerText = 'Updating...';

    const res = await apiPost('/api/auth/change-password', {
        current_password: currentPw,
        new_password: newPw
    });

    btn.disabled = false;
    btn.innerText = 'Update Password';

    if (res && res.message) {
        showToast('Password updated! Please log in again.', 'success');
        setTimeout(() => {
            window.location.href = '/login';
        }, 1500);
    } else {
        showToast(res ? res.error : 'Failed to update password', 'error');
    }
}

// --- Two-Factor Authentication (2FA) ---
async function initiate2FASetup() {
    const res = await apiGet('/api/auth/2fa/setup');
    if (!res || !res.secret) {
        showToast('Failed to initialize 2FA', 'error');
        return;
    }
    generated2FASecret = res.secret;
    document.getElementById('totp-secret-display').innerText = res.secret;
    document.getElementById('totp-setup-details').classList.remove('hidden');
    document.getElementById('totp-verify-input').focus();
}

async function confirmEnable2FA() {
    const code = document.getElementById('totp-verify-input').value.trim();
    if (!code || code.length !== 6) {
        showToast('Please enter the 6-digit verification code.', 'error');
        return;
    }

    const res = await apiPost('/api/auth/2fa/enable', {
        secret: generated2FASecret,
        code: code
    });

    if (res && res.message) {
        showToast(res.message, 'success');
        document.getElementById('badge-2fa-status').innerText = "Active (Protected)";
        document.getElementById('badge-2fa-status').className = "text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30";
        document.getElementById('totp-setup-details').classList.add('hidden');
    } else {
        showToast(res ? res.error : 'Verification failed.', 'error');
    }
}

// --- API Helpers with Auth Handling ---
// --- Active account scope (the "client" chosen in the sidebar) ---
const ACCOUNT_SCOPED = ['/api/whatsapp/', '/api/projects', '/api/posts', '/api/logs'];

function getActiveAccountId() {
    const el = document.getElementById('client-select-filter');
    if (el) return el.value || '';
    try { return localStorage.getItem('gitpulse_account') || ''; } catch (e) { return ''; }
}

function isScoped(endpoint) {
    return ACCOUNT_SCOPED.some(p => endpoint.startsWith(p));
}

function scopeUrl(endpoint) { return endpoint; }
function scopeBody(endpoint, data) { return data; }

function checkApiGuards(res) {
    if (res && res.error === 'password_change_required') showPasswordChange();
    if (res && res.error === 'forbidden' && res.required === 'membership') showNoAccess(false);
    return res;
}

function getAuthHeaders(customHeaders = {}) {
    const headers = { ...customHeaders };
    try {
        const token = localStorage.getItem('gitpulse_token');
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
    } catch (e) {}
    const acct = getActiveAccountId();
    if (acct) headers['X-Account-Id'] = acct;
    return headers;
}

// One place for every API call: safe JSON, a toast for every failure, and 401 goes back to login with the reason.
const _toastSeen = {};
function toastOnce(msg) {
    const now = Date.now();
    if (_toastSeen[msg] && now - _toastSeen[msg] < 8000) return;
    _toastSeen[msg] = now;
    showToast(msg, 'error');
}

async function apiCall(method, endpoint, data, opts = {}) {
    const hasBody = data !== undefined && method !== 'GET';
    let res;
    try {
        res = await fetch(method === 'GET' ? scopeUrl(endpoint) : endpoint, {
            method,
            headers: hasBody ? getAuthHeaders({ 'Content-Type': 'application/json' }) : getAuthHeaders(),
            credentials: 'same-origin',
            ...(hasBody ? { body: JSON.stringify(method === 'DELETE' ? data : scopeBody(endpoint, data)) } : {})
        });
    } catch (err) {
        toastOnce(navigator.onLine === false ? 'You are offline. Check your connection and try again.' : `Could not reach the server (${err.message}).`);
        return null;
    }
    let body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    if (res.status === 401 && endpoint !== '/api/auth/login') {
        const reason = (body && (body.message || errorText(body, ''))) || 'Your session ended. Please sign in again.';
        try { localStorage.removeItem('gitpulse_token'); sessionStorage.setItem('gitpulse_login_reason', reason); } catch (e) {}
        window.location.href = '/login';
        return null;
    }
    if (!res.ok) {
        if (!body || typeof body !== 'object') body = { error: 'server_error', message: `The server had a problem (error ${res.status}). Try again in a moment.` };
        else if (!body.error) body.error = 'request_failed';
        const quiet = body.error === 'password_change_required' || (body.error === 'forbidden' && body.required === 'membership');
        if (!quiet && !opts.quiet) toastOnce(errorText(body, `Request failed (error ${res.status}).`));
    }
    return checkApiGuards(body);
}

const apiGet = (endpoint) => apiCall('GET', endpoint);
const apiPost = (endpoint, data = {}) => apiCall('POST', endpoint, data);
const apiPut = (endpoint, data = {}) => apiCall('PUT', endpoint, data);
const apiDelete = (endpoint, data) => apiCall('DELETE', endpoint, data);

// --- Money: always format with the deal's own currency ---
function formatMoney(amount, currency) {
    const cur = (currency || 'INR').toUpperCase();
    try { return new Intl.NumberFormat(undefined, { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(amount || 0); }
    catch (e) { return `${cur} ${Math.round(amount || 0).toLocaleString()}`; }
}
function sumByCurrency(deals) {
    const m = {};
    deals.forEach(d => { const c = (d.currency || 'INR').toUpperCase(); m[c] = (m[c] || 0) + (parseFloat(d.value) || 0); });
    const keys = Object.keys(m);
    return keys.length ? keys.map(c => formatMoney(m[c], c)).join(' + ') : formatMoney(0, 'INR');
}

// --- Presets ---
async function fetchPresets() {
    const data = await apiGet('/api/presets');
    if (data) globalPresets = data;
}

// --- Status & Metrics ---
async function loadStatus() {
    const status = await apiGet('/api/status');
    if (!status) return;

    if (document.getElementById('stat-repos-count')) document.getElementById('stat-repos-count').innerText = status.projects_count || 0;
    if (document.getElementById('stat-posts-count')) document.getElementById('stat-posts-count').innerText = status.total_posts || 0;
    if (document.getElementById('stat-published-count')) document.getElementById('stat-published-count').innerText = status.published_posts || 0;
    
    const schedEl = document.getElementById('stat-scheduler-status');
    if (schedEl) {
        if (status.scheduler_active) {
            schedEl.innerText = "Running";
            schedEl.className = "text-2xl font-bold mt-1 text-emerald-400";
        } else {
            schedEl.innerText = "Idle";
            schedEl.className = "text-2xl font-bold mt-1 text-yellow-400";
        }
    }

    // Refresh CRM metrics and sidebar badges
    try {
        const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
        const cidParam = '';

        const [cntData, convData, dealData, autoData] = await Promise.all([
            apiGet(`/api/whatsapp/contacts${cidParam}`),
            apiGet(`/api/whatsapp/conversations${cidParam}`),
            apiGet(`/api/whatsapp/deals${cidParam}`),
            apiGet(`/api/whatsapp/automations${cidParam}`)
        ]);

        if (cntData && cntData.contacts) {
            const count = cntData.contacts.length;
            const el = document.getElementById('stat-contacts-count');
            if (el) el.innerText = count;
            const badge = document.getElementById('sidebar-badge-contacts');
            if (badge) badge.innerText = count;
        }

        if (convData && convData.conversations) {
            const openChats = convData.conversations.length;
            const unreadTotal = convData.conversations.reduce((sum, c) => sum + (c.unread_count || 0), 0);
            const el = document.getElementById('stat-chats-count');
            if (el) el.innerText = openChats;
            const badge = document.getElementById('sidebar-badge-inbox');
            if (badge) {
                badge.innerText = unreadTotal > 0 ? `${unreadTotal} new` : openChats;
                badge.className = unreadTotal > 0 ? "sidebar-badge bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" : "sidebar-badge bg-slate-800 text-slate-400";
            }
        }

        if (dealData && dealData.deals) {
            const el = document.getElementById('stat-pipeline-value');
            if (el) el.innerText = sumByCurrency(dealData.deals);
            const badge = document.getElementById('sidebar-badge-deals');
            if (badge) badge.innerText = String(dealData.deals.length);
        }

        if (autoData && autoData.automations) {
            const activeCount = autoData.automations.filter(a => a.is_active).length;
            const badge = document.getElementById('sidebar-badge-automations');
            if (badge) badge.innerText = `${activeCount} live`;
        }
    } catch (e) {
        console.warn('CRM metrics fetch error:', e);
    }
}

// --- Projects Management ---
async function loadProjects() {
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    const url = '/api/projects';
    const data = await apiGet(url);
    if (!data || !data.projects) return;

    const grid = document.getElementById('projects-grid');

    const filterSelect = document.getElementById('post-filter-project');
    if (filterSelect) filterSelect.innerHTML = '<option value="">All Repositories</option>';

    const zeroRedeploySelect = document.getElementById('zeroredeploy-project-select');
    if (zeroRedeploySelect) zeroRedeploySelect.innerHTML = '';

    if (data.projects.length === 0) {
        grid.innerHTML = `
            <div class="col-span-full p-8 text-center bg-slate-900 border border-slate-800 rounded-xl">
                <div class="text-3xl mb-2">🌐</div>
                <h3 class="text-base font-bold text-white mb-1">No Websites Connected Yet</h3>
                <p class="text-xs text-slate-400 max-w-md mx-auto mb-4">Connect your GitHub repository in 60 seconds and start publishing automated SEO articles every day.</p>
                <button onclick="openAddProjectModal()" class="btn-primary text-xs py-2 px-4 shadow-indigo-500/30">⚡ Connect Website in 60s</button>
            </div>
        `;
        return;
    }

    // Drafts waiting and the last failure per project. Quiet: the cards still show if either call fails.
    const [postData, alertData] = await Promise.all([
        apiCall('GET', '/api/posts?limit=50', undefined, { quiet: true }),
        can('crm.read') ? apiCall('GET', '/api/alerts', undefined, { quiet: true }) : null
    ]);
    const focused = grid.contains(document.activeElement) ? document.activeElement.id : '';
    grid.innerHTML = '';

    data.projects.forEach(p => {
        // Populate filters
        if (filterSelect) {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.innerText = `${p.name} (${p.github_repo})`;
            filterSelect.appendChild(opt);
        }

        if (zeroRedeploySelect) {
            const opt2 = document.createElement('option');
            opt2.value = p.id;
            opt2.innerText = `${p.name} (${p.github_repo})`;
            zeroRedeploySelect.appendChild(opt2);
        }

        // Render card
        const card = document.createElement('div');
        card.className = 'project-card';
        card.id = `project-card-${p.id}`;
        card.tabIndex = -1;
        card.innerHTML = `
            <div>
                <div class="flex justify-between items-start mb-2">
                    <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="text-xs px-2 py-0.5 rounded uppercase font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                            ${p.target_framework}
                        </span>
                        ${p.client_name ? `<span class="text-[11px] px-2 py-0.5 rounded font-medium bg-slate-800 text-slate-300 border border-slate-700">🏢 ${escapeHtml(p.client_name)}</span>` : ''}
                    </div>
                    <span class="text-xs text-slate-400 flex items-center gap-1">
                        ⏰ ${escapeHtml(p.publish_time)} India time
                    </span>
                </div>
                <h3 class="font-bold text-white text-base">${escapeHtml(p.name)}</h3>
                <a href="https://github.com/${escapeHtml(p.github_repo)}" target="_blank" class="text-xs text-cyan-400 hover:underline flex items-center gap-1 mt-0.5">
                    github.com/${escapeHtml(p.github_repo)} ↗
                </a>
                <p class="text-xs text-slate-400 mt-2 line-clamp-2"><strong>Niche:</strong> ${escapeHtml(p.topic)}</p>
                
                ${projectRunHtml(p, postData, alertData)}
                <div class="mt-3 py-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                    <span>Directory: <code>${escapeHtml(p.content_dir)}</code></span>
                    <span>Mode: <strong class="text-slate-200 uppercase">${p.publishing_mode}</strong></span>
                </div>
            </div>

            <div class="mt-4 pt-3 border-t border-slate-800 space-y-2">
                <div class="flex justify-between items-center">
                    <div class="flex space-x-1.5">
                        <button onclick="triggerProjectRun(${p.id}, this)" class="btn-primary text-xs py-1 px-2.5">
                            ✨ Write Today's Article
                        </button>
                        <button onclick="testGitHubConnection(${p.id}, this)" class="btn-secondary text-xs py-1 px-2">
                            Verify Repo
                        </button>
                    </div>
                    <button onclick="deleteProject(${p.id})" class="btn-danger">
                        Delete
                    </button>
                </div>
                
                <!-- Zero Redeploy Installer button -->
                <button onclick="installZeroRedeployForProject(${p.id})" class="w-full text-center text-[11px] py-1 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 hover:bg-indigo-500/20">
                    🚀 Add 1-Time Live Blog to Website ↗
                </button>
            </div>
        `;
        grid.appendChild(card);
        if (focused === card.id) card.focus();
    });
}

// The scheduler works in India time: it runs a project once a day, at or after its publish time.
function projectRunHtml(p, postData, alertData) {
    const ist = d => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(d)
        .reduce((o, x) => (o[x.type] = x.value, o), {});
    const last = p.last_run_at ? new Date(/Z|[+-]\d\d:?\d\d$/.test(p.last_run_at) ? p.last_run_at : p.last_run_at.replace(' ', 'T') + 'Z') : null;
    const now = ist(new Date());
    const day = o => `${o.year}-${o.month}-${o.day}`;
    const ranToday = last && day(ist(last)) === day(now);
    const time = String(p.publish_time || '09:00').padStart(5, '0');
    const next = ranToday ? `tomorrow ${time}` : `${now.hour}:${now.minute}` >= time ? `due now (${time})` : `today ${time}`;
    const failure = ((alertData && alertData.alerts) || []).find(a => !a.resolved_at && a.link === `project:${p.id}`);
    const drafts = postData && postData.posts ? postData.posts.filter(x => x.project_id === p.id && (x.status === 'in_review' || x.status === 'draft')).length : null;
    const lastText = last ? last.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'never';
    return `<dl class="mt-3 text-xs text-slate-400 space-y-0.5">
        <div><dt class="inline">Next run: </dt><dd class="inline text-slate-200">${escapeHtml(next)} India time</dd></div>
        <div><dt class="inline">Last run: </dt><dd class="inline text-slate-200">${escapeHtml(lastText)}</dd>${failure ? ` <span class="text-red-300">Problem: ${escapeHtml(failure.message)}</span>` : ''}</div>
        ${drafts === null ? '' : `<div><dt class="inline">Drafts waiting: </dt><dd class="inline text-slate-200">${drafts}</dd>${drafts ? ` <button type="button" class="underline text-cyan-400" onclick="switchTab('staging')">Review</button>` : ''}</div>`}
    </dl>`;
}

async function triggerProjectRun(projectId, btn) {
    const originalText = btn.innerText;
    btn.disabled = true;
    btn.innerText = 'Publishing...';

    const res = await apiPost(`/api/projects/${projectId}/trigger`, { force_publish: true });
    btn.disabled = false;
    btn.innerText = originalText;

    if (res && res.success) {
        showToast(`Article '${res.title}' generated and published!`, 'success');
        loadStatus();
        loadProjects();
        loadPosts();
        loadStagingPosts();
        loadLogs();
    } else {
        showToast(res ? (res.error || 'Trigger failed') : 'Execution error', 'error');
    }
}

async function testGitHubConnection(projectId, btn) {
    const originalText = btn.innerText;
    btn.disabled = true;
    btn.innerText = 'Checking...';

    const res = await apiPost(`/api/projects/${projectId}/test-github`);
    btn.disabled = false;
    btn.innerText = originalText;

    if (res && res.connected) {
        showToast(res.message, 'success');
    } else {
        showToast(res ? res.message : 'Connection test failed', 'error');
    }
}

async function deleteProject(projectId) {
    if (!confirm('Are you sure you want to disconnect this repository and delete its configuration?')) return;
    const res = await apiDelete(`/api/projects/${projectId}`);
    if (res && res.message) {
        showToast('Project removed.', 'success');
        loadProjects();
        loadStatus();
    }
}

// --- Zero-Redeploy "One-Time Blog Page" Installer ---
async function installZeroRedeployBlog() {
    const select = document.getElementById('zeroredeploy-project-select');
    const projectId = select.value;
    if (!projectId) return;

    await installZeroRedeployForProject(projectId);
}

async function installZeroRedeployForProject(projectId) {
    const btn = document.getElementById('btn-install-blog');
    if (btn) {
        btn.disabled = true;
        btn.innerText = 'Committing...';
    }

    const res = await apiPost(`/api/projects/${projectId}/install-blog-page`, {
        cms_base_url: window.location.origin
    });

    if (btn) {
        btn.disabled = false;
        btn.innerText = 'Install Blog Page to Repository';
    }

    const resultBox = document.getElementById('install-result');
    if (res && res.success) {
        showToast('Zero-redeploy blog page committed to repository!', 'success');
        if (resultBox) {
            resultBox.classList.remove('hidden');
            resultBox.innerHTML = `
                <strong>Success!</strong> ${res.message}<br>
                <span class="text-slate-400">Path: <code>${res.path}</code> (Commit: ${res.commit_sha})</span><br>
                <span class="text-indigo-300">Your other project can now display all published blog posts dynamically with 0 future deployments!</span>
            `;
        }
    } else {
        showToast(res ? res.error : 'Installation failed', 'error');
    }
}

// --- Editorial Staging Queue ---
async function loadStagingPosts() {
    const data = await apiGet('/api/posts?limit=50');
    if (!data || !data.posts) return;

    const stagingContainer = document.getElementById('staging-cards-container');
    if (!stagingContainer) return;

    const inReviewPosts = data.posts.filter(p => p.status === 'in_review' || p.status === 'draft');
    const badgeCount = document.getElementById('badge-staging-count');
    if (badgeCount) badgeCount.innerText = inReviewPosts.length;

    stagingContainer.innerHTML = '';
    if (inReviewPosts.length === 0) {
        stagingContainer.innerHTML = `
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
                <svg class="w-10 h-10 mx-auto mb-2 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                <div class="text-base font-semibold text-white">Staging Queue is Clear</div>
                <div class="text-xs text-slate-500 mt-1">All generated articles have been reviewed and published. New scheduled articles requiring manual review will appear here.</div>
            </div>
        `;
        return;
    }

    inReviewPosts.forEach(post => {
        const card = document.createElement('div');
        card.className = 'bg-slate-900 border border-slate-800 rounded-xl p-4 flex justify-between items-center hover:border-slate-700 transition-colors';
        const seoScore = post.seo_score || 100;
        const scoreClass = seoScore >= 80 ? 'text-emerald-400 border-emerald-500/30' : 'text-amber-400 border-amber-500/30';

        card.innerHTML = `
            <div>
                <div class="flex items-center gap-2">
                    <span class="font-bold text-white text-base">${escapeHtml(post.title)}</span>
                    <span class="text-xs px-2 py-0.5 rounded-full font-mono bg-slate-950 border ${scoreClass}">SEO ${seoScore}/100</span>
                    <span class="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30 uppercase text-[10px] font-bold">Needs Review</span>
                </div>
                <div class="text-xs text-slate-400 mt-1">${escapeHtml(post.excerpt)}</div>
                <div class="text-[11px] text-slate-500 font-mono mt-1">Target: ${escapeHtml(post.target_path)} • ${escapeHtml(post.project_name || 'Project')}</div>
            </div>

            <div class="flex items-center gap-2">
                <button onclick="openStagingEditor(${post.id})" class="btn-primary text-xs py-1.5 px-3">
                    Edit & Approve &rarr;
                </button>
            </div>
        `;
        stagingContainer.appendChild(card);
    });
}

// --- Split Screen Editorial Editor ---
async function openStagingEditor(postId) {
    const post = await apiGet(`/api/posts/${postId}`);
    if (!post) return;
    currentStagingPost = post;

    document.getElementById('edit-post-id').value = post.id;
    document.getElementById('edit-post-title').value = post.title;
    document.getElementById('edit-post-excerpt').value = post.excerpt;
    document.getElementById('edit-post-markdown').value = post.content_markdown;

    updateSplitPreview();
    document.getElementById('modal-staging-editor').classList.remove('hidden');
}

function closeStagingEditor() {
    document.getElementById('modal-staging-editor').classList.add('hidden');
    currentStagingPost = null;
}

function updateSplitPreview() {
    const md = document.getElementById('edit-post-markdown').value;
    const title = document.getElementById('edit-post-title').value;
    const excerpt = document.getElementById('edit-post-excerpt').value;

    // Render markdown to preview pane
    const previewEl = document.getElementById('editor-live-preview');
    if (window.marked) {
        previewEl.innerHTML = marked.parse(md);
    } else {
        previewEl.innerText = md;
    }

    // Dynamic SEO Pre-Flight Check in UI
    const titleLen = title.length;
    const excerptLen = excerpt.length;
    let score = 100;
    const issues = [];

    if (titleLen < 30) { score -= 15; issues.push(`Title is too short (${titleLen} chars). Optimal: 40-65 chars.`); }
    if (excerptLen < 100) { score -= 15; issues.push(`Excerpt is too short (${excerptLen} chars). Optimal: 130-165 chars.`); }
    if (!md.includes('## ')) { score -= 20; issues.push("Article has no H2 section headers."); }

    const scoreBadge = document.getElementById('editor-seo-badge');
    scoreBadge.innerText = `SEO: ${score}/100`;
    scoreBadge.className = `text-xs px-2.5 py-0.5 rounded-full font-semibold ${score >= 80 ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' : 'bg-amber-500/10 text-amber-300 border border-amber-500/30'}`;

    const issuesBox = document.getElementById('editor-issues-list');
    issuesBox.innerHTML = issues.length ? issues.map(i => `<div class="text-amber-400">• ${i}</div>`).join('') : '<div class="text-emerald-400">✓ All SEO and formatting parameters verified.</div>';
}

async function saveStagedDraft() {
    if (!currentStagingPost) return;
    const postId = currentStagingPost.id;
    const payload = {
        title: document.getElementById('edit-post-title').value,
        excerpt: document.getElementById('edit-post-excerpt').value,
        content_markdown: document.getElementById('edit-post-markdown').value
    };

    const res = await apiPut(`/api/posts/${postId}`, payload);
    if (res && res.message) {
        showToast('Changes saved to staging draft.', 'success');
        loadStagingPosts();
    } else {
        showToast(res ? res.error : 'Save failed', 'error');
    }
}

async function approveAndPublishStagedPost() {
    if (!currentStagingPost) return;
    const postId = currentStagingPost.id;
    const btn = document.getElementById('btn-approve-post');
    btn.disabled = true;
    btn.innerText = 'Publishing to GitHub...';

    // 1. Save any pending changes
    await saveStagedDraft();

    // 2. Approve and trigger GitHub publication
    const res = await apiPost(`/api/posts/${postId}/approve`, {});
    btn.disabled = false;
    btn.innerText = 'Approve & Publish to GitHub 🚀';

    if (res && res.success) {
        showToast('Article approved and published to GitHub!', 'success');
        closeStagingEditor();
        loadStagingPosts();
        loadPosts();
        loadStatus();
    } else {
        showToast(res ? res.error : 'Approval dispatch failed', 'error');
    }
}

// --- Posts & Articles Table ---
async function loadPosts() {
    const projectId = document.getElementById('post-filter-project').value;
    const url = projectId ? `/api/posts?project_id=${projectId}` : '/api/posts';
    const data = await apiGet(url);
    if (!data || !data.posts) return;

    const tbody = document.getElementById('posts-table-body');
    tbody.innerHTML = '';

    if (data.posts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="px-5 py-6 text-center text-slate-500">No blog posts found.</td></tr>`;
        return;
    }

    data.posts.forEach(post => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-800/40 transition-colors';

        let statusBadge = '<span class="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-400">Draft</span>';
        if (post.status === 'published') {
            statusBadge = '<span class="px-2 py-0.5 rounded text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">Published</span>';
        } else if (post.status === 'in_review') {
            statusBadge = '<span class="px-2 py-0.5 rounded text-xs bg-amber-500/10 text-amber-300 border border-amber-500/30">In Staging</span>';
        } else if (post.status === 'failed') {
            statusBadge = '<span class="px-2 py-0.5 rounded text-xs bg-red-500/10 text-red-400 border border-red-500/30">Failed</span>';
        }

        let githubDelivery = '<span class="text-slate-500 text-xs">Pending delivery</span>';
        if (post.github_pr_url) {
            githubDelivery = `<a href="${post.github_pr_url}" target="_blank" class="text-cyan-400 hover:underline text-xs flex items-center gap-1">PR #${post.github_pr_number || 'Link'} ↗</a>`;
        } else if (post.github_commit_sha) {
            githubDelivery = `<span class="text-slate-400 font-mono text-xs">Commit: ${post.github_commit_sha.substring(0, 7)}</span>`;
        }

        const seoScore = post.seo_score || 100;
        const seoBadge = `<span class="text-xs font-mono ${seoScore >= 80 ? 'text-emerald-400' : 'text-amber-400'}">${seoScore}/100</span>`;

        tr.innerHTML = `
            <td class="px-5 py-3">
                <div class="font-semibold text-white">${escapeHtml(post.title)}</div>
                <div class="text-xs text-slate-400 font-mono mt-0.5">${escapeHtml(post.target_path)}</div>
            </td>
            <td class="px-5 py-3 text-xs text-slate-300">
                ${escapeHtml(post.project_name || 'Repo')}
            </td>
            <td class="px-5 py-3">${seoBadge}</td>
            <td class="px-5 py-3">${statusBadge}</td>
            <td class="px-5 py-3">${githubDelivery}</td>
            <td class="px-5 py-3 text-right">
                <button onclick="viewPost(${post.id})" class="btn-secondary text-xs py-1 px-2.5">
                    Inspect Markdown
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function viewPost(postId) {
    const post = await apiGet(`/api/posts/${postId}`);
    if (!post) return;

    document.getElementById('modal-post-title').innerText = post.title;
    document.getElementById('modal-post-frontmatter').innerText = post.frontmatter_yaml;
    document.getElementById('modal-post-excerpt').innerText = post.excerpt;
    document.getElementById('modal-post-image-prompt').innerText = post.image_prompt || 'N/A';
    document.getElementById('modal-post-path').innerText = post.target_path;
    document.getElementById('modal-post-content').value = post.content_markdown;

    document.getElementById('modal-post').classList.remove('hidden');
}

function closePostModal() {
    document.getElementById('modal-post').classList.add('hidden');
}

// --- Multi-Tenant Clients Management ---
async function loadClients() {
    // Final contract: GET /api/accounts -> {accounts:[{id,name,role}]}. Falls back to the old /api/clients list.
    let data = await apiGet('/api/accounts');
    accountsMode = !!(data && Array.isArray(data.accounts));
    data = { clients: accountsMode ? data.accounts : [] };
    window.__accounts = data.clients;

    // Header client filter
    const headerFilter = document.getElementById('client-select-filter');
    if (headerFilter) {
        const curVal = headerFilter.value;
        headerFilter.innerHTML = accountsMode ? '' : '<option value="">All accounts (admin view)</option>';
        data.clients.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.innerText = c.name;
            headerFilter.appendChild(opt);
        });
        let want = curVal;
        if (!want) { try { want = localStorage.getItem('gitpulse_account') || ''; } catch (e) {} }
        if (accountsMode && !data.clients.some(c => String(c.id) === String(want)) && data.clients.length) want = String(data.clients[0].id);
        headerFilter.value = want;
        if (accountsMode && headerFilter.value) { try { localStorage.setItem('gitpulse_account', headerFilter.value); } catch (e) {} }
    }

    // Wizard client selector
    const wizardClient = document.getElementById('wizard-client-id');
    if (wizardClient) {
        wizardClient.innerHTML = '<option value="">(Select or create business)</option>';
        data.clients.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.innerText = c.name;
            wizardClient.appendChild(opt);
        });
    }
}

async function onClientFilterChange() {
    try { localStorage.setItem('gitpulse_account', getActiveAccountId()); } catch (e) {}
    activeConversationId = null;
    updateAccountBanner();
    await refreshMe();
    applyRolePermissions();
    reloadAccountData();
    reloadPhase1();
    if (!document.getElementById('tab-users').classList.contains('hidden')) loadUsersAndRoles();
}

// Permissions depend on the active account, so re-read them after every switch.
async function refreshMe() {
    const me = await apiGet('/api/auth/me');
    if (me && me.user) {
        currentUser = me.user;
        window.__perms = Array.isArray(me.permissions) ? me.permissions : null;
        window.__memberships = me.memberships || [];
        window.__platformAdmin = !!me.user.is_platform_admin;
        const acct = getActiveAccountId();
        const m = (me.memberships || []).find(x => String(x.account_id) === String(acct));
        if (m) currentUser.role = m.role;
    }
    const acctId = getActiveAccountId();
    if (acctId) {
        const d = await apiGet(`/api/accounts/${encodeURIComponent(acctId)}`);
        if (d && d.default_currency) {
            window.__acctCurrency = d.default_currency;
            const dc = document.getElementById('new-deal-currency');
            if (dc) dc.value = d.default_currency;
            const sc = document.getElementById('set-currency');
            if (sc) sc.value = d.default_currency;
        }
    }
}

function reloadAccountData() {
    return Promise.all([
        loadStatus(), loadProjects(), loadStagingPosts(), loadPosts(),
        loadWhatsAppInbox(), loadWhatsAppContacts(), loadWhatsAppDeals(),
        loadWhatsAppBroadcasts(), loadWhatsAppAutomations(), loadWhatsAppConfig(),
        loadLogs()
    ]);
}

function updateAccountBanner() {
    const el = document.getElementById('client-select-filter');
    const label = el && el.selectedOptions[0] ? el.selectedOptions[0].text : '';
    const banner = document.getElementById('account-banner-name');
    if (banner) banner.innerText = label || 'All accounts';
}

// Shared empty-state row/card so blank screens explain what to do next.
function emptyStateHtml(title, hint) {
    return `<div class="p-8 text-center text-slate-400 text-sm" role="status">
        <div class="font-semibold text-slate-300 mb-1">${escapeHtml(title)}</div>
        <div class="text-xs text-slate-500">${escapeHtml(hint)}</div></div>`;
}

function openAddClientModal() {
    document.getElementById('modal-add-client').classList.remove('hidden');
}

function closeAddClientModal() {
    document.getElementById('modal-add-client').classList.add('hidden');
}

async function submitAddClient(e) {
    e.preventDefault();
    const name = document.getElementById('new-client-name').value.trim();
    const owner = (document.getElementById('new-client-owner') || {}).value || '';
    const email = document.getElementById('new-client-email').value.trim();
    const res = await apiPost('/api/accounts', { name, owner_username: owner.trim() || undefined, owner_email: email || undefined });
    if (res && res.id && !res.error) {
        const box = document.getElementById('new-client-result');
        const pw = res.owner_temporary_password;
        if (box) box.innerHTML = `Account <strong>${escapeHtml(res.name)}</strong> created.` + (pw ? ` Owner temporary password, shown once: <code class="text-emerald-300">${escapeHtml(pw)}</code>. Share it privately.` : ' The owner can sign in with their existing login.');
        showToast('Account created.', 'success');
        document.getElementById('new-client-name').value = '';
        document.getElementById('new-client-email').value = '';
        if (document.getElementById('new-client-owner')) document.getElementById('new-client-owner').value = '';
        await loadClients();
    } else {
        showToast(errorText(res, 'Failed to create account'), 'error');
    }
}

// --- Interactive 3-Step Wizard (Built for Non-Technical UX) ---
let currentWizardStep = 1;

function openAddProjectModal() {
    currentWizardStep = 1;
    goToWizardStep(1);
    document.getElementById('modal-add-project').classList.remove('hidden');
    loadClients();
}

function openConnectWizard() {
    openAddProjectModal();
}

function closeAddProjectModal() {
    document.getElementById('modal-add-project').classList.add('hidden');
}

function goToWizardStep(step) {
    // Validation before proceeding to step 3
    if (step === 3) {
        const repo = document.getElementById('wizard-repo').value.trim();
        const name = document.getElementById('wizard-name').value.trim();
        if (!repo) {
            showToast('Please enter your GitHub repository (e.g. username/repo)', 'error');
            return;
        }
        if (!name) {
            document.getElementById('wizard-name').value = repo.split('/')[1] || repo;
        }
    }

    currentWizardStep = step;

    // Show/hide step panels
    document.getElementById('wizard-step-1').classList.toggle('hidden', step !== 1);
    document.getElementById('wizard-step-2').classList.toggle('hidden', step !== 2);
    document.getElementById('wizard-step-3').classList.toggle('hidden', step !== 3);

    // Update step bar visual nodes
    for (let i = 1; i <= 3; i++) {
        const node = document.getElementById(`step-node-${i}`);
        if (!node) continue;
        node.classList.remove('active', 'completed');
        if (i === step) node.classList.add('active');
        else if (i < step) node.classList.add('completed');
    }
}

function selectWizardFramework(framework, cardEl) {
    document.querySelectorAll('#wizard-step-1 .wizard-card').forEach(c => c.classList.remove('selected'));
    cardEl.classList.add('selected');

    document.getElementById('wizard-framework').value = framework;
    const preset = globalPresets[framework] || globalPresets['generic'];
    if (preset) {
        document.getElementById('wizard-content-dir').value = preset.content_dir;
        document.getElementById('wizard-file-ext').value = preset.file_extension;
        const customDir = document.getElementById('wizard-custom-dir');
        if (customDir) customDir.value = preset.content_dir;
    }
}

function resetWizardVerify() {
    const resEl = document.getElementById('wizard-verify-result');
    if (resEl) {
        resEl.className = 'hidden';
        resEl.innerHTML = '';
    }
}

async function verifyWizardGitHub() {
    const repo = document.getElementById('wizard-repo').value.trim();
    const token = document.getElementById('wizard-token').value.trim();
    const btn = document.getElementById('btn-wizard-verify');
    const resEl = document.getElementById('wizard-verify-result');

    if (!repo) {
        showToast('Please enter your GitHub repository first.', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="inline-block animate-spin mr-1">🔄</span> Verifying GitHub Access...';

    const res = await apiPost('/api/github/verify', {
        github_repo: repo,
        github_token: token
    });

    btn.disabled = false;
    btn.innerHTML = '<span>⚡ Test Repository Connection</span>';

    resEl.classList.remove('hidden');
    if (res && res.valid) {
        resEl.className = 'mt-2 p-2.5 rounded text-xs bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 flex items-center gap-2';
        resEl.innerHTML = `<span>✅ <strong>Connected!</strong> Found <code>${escapeHtml(res.repo)}</code> on branch <code>${escapeHtml(res.branch)}</code>.</span>`;
    } else {
        resEl.className = 'mt-2 p-2.5 rounded text-xs bg-amber-500/10 border border-amber-500/30 text-amber-300 flex items-center gap-2';
        resEl.innerHTML = `<span>⚠️ ${escapeHtml(res ? res.message : 'Could not verify repository. Please check name and token permissions.')}</span>`;
    }
}

function applyInspiration(niche, topicText) {
    document.getElementById('wizard-topic').value = topicText;
    const nameInput = document.getElementById('wizard-name');
    if (!nameInput.value) {
        nameInput.value = niche;
    }
    showToast(`Applied topic inspiration: ${niche}`, 'info');
}

function selectTone(tone, pillEl) {
    document.querySelectorAll('.tone-pill').forEach(p => p.classList.remove('selected'));
    pillEl.classList.add('selected');
    document.getElementById('wizard-tone').value = tone;
}

function selectPublishMode(mode, cardEl) {
    document.querySelectorAll('#wizard-step-3 .wizard-card').forEach(c => c.classList.remove('selected'));
    cardEl.classList.add('selected');
    document.getElementById('wizard-publishing-mode').value = mode;
}

async function submitWizardProject() {
    const btn = document.getElementById('btn-wizard-submit');
    const name = document.getElementById('wizard-name').value.trim();
    const repo = document.getElementById('wizard-repo').value.trim();
    const topic = document.getElementById('wizard-topic').value.trim();

    if (!name || !repo || !topic) {
        showToast('Please fill in the website name, GitHub repository, and topic.', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerText = 'Connecting Website...';

    const payload = {
        name: name,
        github_repo: repo,
        github_branch: document.getElementById('wizard-branch').value || 'main',
        github_token: document.getElementById('wizard-token').value || '',
        target_framework: document.getElementById('wizard-framework').value || 'nextjs',
        content_dir: document.getElementById('wizard-content-dir').value || 'content/posts',
        publishing_mode: document.getElementById('wizard-publishing-mode').value || 'pr',
        publish_time: document.getElementById('wizard-publish-time').value || '09:00',
        author_name: document.getElementById('wizard-author').value || 'Editorial Team',
        topic: topic,
        tone: document.getElementById('wizard-tone').value || 'Authoritative, practical, and engaging',
        target_audience: 'Customers and Industry Readers'
    };

    const res = await apiPost('/api/projects', payload);
    btn.disabled = false;
    btn.innerText = '✨ Connect Website & Start Publishing';

    if (res && res.id) {
        showToast('🎉 Website successfully connected! Your daily blog pipeline is ready.', 'success');
        closeAddProjectModal();
        await loadProjects();
        await loadStatus();
    } else {
        showToast(res ? res.error : 'Failed to register website', 'error');
    }
}

// --- Supabase Cloud Database UI Controller ---
async function loadSupabaseStatus() {
    const badge = document.getElementById('badge-supabase-status');
    if (!badge) return;

    const data = await apiGet('/api/supabase/status');
    if (data && data.configured && data.connected) {
        badge.innerText = "Connected (Cloud Active)";
        badge.className = "text-xs px-2.5 py-0.5 rounded-full font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30";
    } else if (data && data.configured && !data.connected) {
        badge.innerText = "Auth Error";
        badge.className = "text-xs px-2.5 py-0.5 rounded-full font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30";
    } else {
        badge.innerText = "Offline (Local SQLite)";
        badge.className = "text-xs px-2.5 py-0.5 rounded-full font-medium bg-slate-800 text-slate-400 border border-slate-700";
    }
}

async function testSupabaseFromUI() {
    const url = document.getElementById('setting-supabase-url').value.trim();
    const key = document.getElementById('setting-supabase-key').value.trim();
    const feedback = document.getElementById('supabase-test-feedback');

    feedback.innerText = 'Testing connection...';
    feedback.className = 'text-xs font-mono text-slate-400';

    const res = await apiPost('/api/supabase/test', { url, key });
    if (res && res.connected) {
        feedback.innerText = `✅ ${res.message}`;
        feedback.className = 'text-xs font-mono text-emerald-400';
        loadSupabaseStatus();
    } else {
        feedback.innerText = `⚠️ ${res ? res.message : 'Connection failed.'}`;
        feedback.className = 'text-xs font-mono text-amber-400';
    }
}

async function syncAllToSupabaseFromUI() {
    if (!confirm('Sync all clients, connected repositories, and blog posts to Supabase cloud?')) return;
    const feedback = document.getElementById('supabase-test-feedback');
    feedback.innerText = 'Syncing to cloud...';
    feedback.className = 'text-xs font-mono text-indigo-400';

    const res = await apiPost('/api/supabase/sync', {});
    if (res && res.success) {
        feedback.innerText = `✅ ${res.message}`;
        feedback.className = 'text-xs font-mono text-emerald-400';
        showToast('All content synced to Supabase!', 'success');
        loadSupabaseStatus();
    } else {
        feedback.innerText = `⚠️ ${res ? res.error : 'Sync failed.'}`;
        feedback.className = 'text-xs font-mono text-red-400';
        showToast(res ? res.error : 'Sync failed', 'error');
    }
}

// --- Activity Logs ---
async function loadLogs() {
    if (!can('audit.read')) return;
    const data = await apiGet('/api/logs?limit=40');
    if (!data || !data.logs) return;

    const container = document.getElementById('logs-container');
    container.innerHTML = '';

    data.logs.forEach(log => {
        const item = document.createElement('div');
        const levelColor = log.level === 'ERROR' ? 'text-red-400' : (log.level === 'WARN' ? 'text-yellow-400' : 'text-slate-400');
        item.innerHTML = `
            <span class="text-slate-500">[${log.created_at.replace('T', ' ').substring(0, 19)}]</span>
            <span class="${levelColor} font-bold">[${log.level}]</span>
            <span class="text-indigo-400">${log.project_name ? `[${escapeHtml(log.project_name)}]` : ''}</span>
            <span class="text-slate-300">${escapeHtml(log.message)}</span>
        `;
        container.appendChild(item);
    });
}

// --- Settings ---
async function loadSettings() {
    const settings = await apiGet('/api/settings');
    if (!settings) return;

    if (settings.github_token) document.getElementById('setting-github-token').value = settings.github_token;
    if (settings.ai_provider) document.getElementById('setting-ai-provider').value = settings.ai_provider;
    if (settings.gemini_api_key) document.getElementById('setting-gemini-key').value = settings.gemini_api_key;
    if (settings.openai_api_key) document.getElementById('setting-openai-key').value = settings.openai_api_key;
    if (settings.github_webhook_secret) document.getElementById('setting-webhook-secret').value = settings.github_webhook_secret;
    if (settings.supabase_url) document.getElementById('setting-supabase-url').value = settings.supabase_url;
    if (settings.supabase_key) document.getElementById('setting-supabase-key').value = settings.supabase_key;
}

async function saveSettings() {
    const payload = {
        github_token: document.getElementById('setting-github-token').value,
        ai_provider: document.getElementById('setting-ai-provider').value,
        gemini_api_key: document.getElementById('setting-gemini-key').value,
        openai_api_key: document.getElementById('setting-openai-key').value,
        github_webhook_secret: document.getElementById('setting-webhook-secret').value,
        supabase_url: document.getElementById('setting-supabase-url').value,
        supabase_key: document.getElementById('setting-supabase-key').value
    };

    const res = await apiPost('/api/settings', payload);
    if (res && res.message) {
        showToast('Settings saved successfully.', 'success');
        loadSupabaseStatus();
    }
}

// --- Toast & Helpers ---
function errorText(res, fallback) {
    if (!res) return fallback;
    if (res.error === 'forbidden') return res.required ? `Your role does not allow this (needs ${res.required}).` : 'Your role does not allow this.';
    if (res.error === 'already_member') return 'This person is already in the account.';
    if (res.error === 'duplicate_phone') return 'A contact with this phone number already exists in this account.';
    if (res.error === 'phone_number_in_use') return 'This WhatsApp number is already connected to another account.';
    if (res.error === 'keyword_required') return 'A keyword rule needs at least one keyword.';
    if (res.error === 'not_a_member') return 'That person is not in this account.';
    if (res.error === 'last_owner') return 'An account must keep at least one owner.';
    if (res.error === 'account_required') return 'Choose a client account first.';
    if (res.message && (res.error === 'server_error' || res.error === 'request_failed' || !res.error)) return res.message;
    if (res.error === 'invalid_phone') return 'Phone number must be 8 to 15 digits.';
    if (res.error === 'invalid_value') return 'Deal value must be 0 or more.';
    if (res.error === 'invalid_currency') return 'Currency must be a 3-letter code such as INR.';
    if (res.message) return res.message;
    return res.error || fallback;
}

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.innerText = message;
    toast.className = `toast ${type === 'error' ? 'border-red-500 text-red-200' : 'border-emerald-500 text-emerald-200'}`;
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4500);
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// Safe string for use inside an inline onclick="..." attribute.
function jsAttr(str) {
    return escapeHtml(JSON.stringify(String(str == null ? '' : str))).replace(/&#39;/g, "\\'");
}

// ====================================================================
// WhatsApp Automation & CRM Engine (ArnasDon/wacrm Frontend Controller)
// ====================================================================

let activeConversationId = null;
let currentConversationsList = [];

// --- 1. Shared Team Inbox ---

async function loadWhatsAppInbox(selectConvId = null) {
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    const af = document.getElementById('wa-assigned-filter');
    const url = '/api/whatsapp/conversations' + (af && af.value === 'me' ? '?assigned=me' : '');
    
    const data = await apiGet(url);
    if (!data || !data.conversations) return;
    
    const humanOnly = af && af.value === 'human';
    currentConversationsList = humanOnly ? data.conversations.filter(c => c.needs_human) : data.conversations;
    const threadListEl = document.getElementById('wa-threads-list');
    if (!threadListEl) return;
    
    threadListEl.innerHTML = '';
    
    if (currentConversationsList.length === 0) {
        threadListEl.innerHTML = `
            <div class="p-6 text-center text-slate-500 text-xs">
                ${humanOnly ? 'No chats are waiting for a person.' : "No conversations yet; start one from Contacts.<br>Chats also appear here when a customer messages this account's WhatsApp number."}
            </div>
        `;
        document.getElementById('wa-chat-empty-state').classList.remove('hidden');
        document.getElementById('wa-chat-active-state').classList.add('hidden');
        return;
    }
    
    currentConversationsList.forEach(conv => {
        const item = document.createElement('div');
        const isActive = (selectConvId && conv.id === selectConvId) || (!selectConvId && activeConversationId === conv.id) || (!selectConvId && !activeConversationId && currentConversationsList[0].id === conv.id);
        
        item.className = `chat-thread-item ${isActive ? 'active' : ''}`;
        item.onclick = () => selectConversation(conv.id);
        
        const initials = conv.contact_name ? conv.contact_name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() : 'WA';
        const timeStr = conv.last_message_at ? new Date(conv.last_message_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
        const unreadBadge = conv.unread_count > 0 ? `<span class="bg-indigo-500 text-white text-[10px] font-bold px-1.5 py-0.2 rounded-full">${conv.unread_count}</span>` : '';
        
        item.innerHTML = `
            <div class="w-9 h-9 rounded-full bg-gradient-to-tr from-indigo-500 to-cyan-500 flex items-center justify-center font-bold text-xs text-white flex-shrink-0">
                ${initials}
            </div>
            <div class="flex-1 min-w-0">
                <div class="flex justify-between items-center mb-0.5">
                    <span class="font-semibold text-xs text-slate-200 truncate">${escapeHtml(conv.contact_name)}</span>
                    <span class="text-[10px] text-slate-500">${timeStr}</span>
                </div>
                ${conv.assigned_user_id ? `<div class="text-[10px] text-indigo-300 truncate">${conv.assigned_user_id === (currentUser && currentUser.id) ? 'Assigned to you' : 'Assigned: ' + escapeHtml(conv.assigned_to || '')}</div>` : ''}
                ${conv.needs_human ? '<div class="text-[10px] font-semibold text-amber-300">⚠ Needs human</div>' : ''}
                <div class="flex justify-between items-center">
                    <p class="text-[11px] text-slate-400 truncate">${escapeHtml(conv.last_message_preview || 'No messages')}</p>
                    ${unreadBadge}
                </div>
            </div>
        `;
        threadListEl.appendChild(item);
    });
    
    const targetId = selectConvId || activeConversationId || currentConversationsList[0].id;
    selectConversation(targetId, true);
}

async function selectConversation(convId, force = false) {
    if (activeConversationId === convId && !force) return;
    activeConversationId = convId;
    
    // Highlight thread in sidebar
    document.querySelectorAll('.chat-thread-item').forEach(el => el.classList.remove('active'));
    const allThreads = document.querySelectorAll('.chat-thread-item');
    const idx = currentConversationsList.findIndex(c => c.id === convId);
    if (idx !== -1 && allThreads[idx]) allThreads[idx].classList.add('active');
    
    // Mark as read
    if (can('crm.write')) apiPost(`/api/whatsapp/conversations/${convId}/read`, {});
    
    const conv = currentConversationsList.find(c => c.id === convId);
    if (conv) {
        renderAssignSelect(conv);
        renderNeedsHuman(conv);
        document.getElementById('wa-chat-empty-state').classList.add('hidden');
        document.getElementById('wa-chat-active-state').classList.remove('hidden');
        
        document.getElementById('wa-chat-contact-name').innerText = conv.contact_name;
        document.getElementById('wa-chat-contact-phone').innerText = conv.contact_phone;
        
        // Tags
        const tagsContainer = document.getElementById('wa-chat-contact-tags');
        if (tagsContainer) {
            tagsContainer.innerHTML = '';
            (conv.contact_tags || ['Lead']).forEach(tag => {
                const span = document.createElement('span');
                span.className = "text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20";
                span.innerText = tag;
                tagsContainer.appendChild(span);
            });
        }
    }
    
    await loadConversationMessages(convId);
}

let accountMembersCache = { acct: null, users: [] };
async function renderAssignSelect(conv) {
    const sel = document.getElementById('wa-assign-select');
    if (!sel) return;
    const myId = currentUser && currentUser.id;
    let members = [];
    if (can('users.manage')) {
        const acct = getActiveAccountId();
        if (accountMembersCache.acct !== acct) {
            const d = await apiGet(`/api/accounts/${encodeURIComponent(acct)}/users`);
            accountMembersCache = { acct, users: (d && d.users) || [] };
        }
        members = accountMembersCache.users;
    }
    if (activeConversationId !== conv.id) return;
    sel.innerHTML = '';
    sel.add(new Option('Unassigned', ''));
    if (myId) sel.add(new Option('Me', String(myId)));
    members.filter(u => u.user_id !== myId).forEach(u => sel.add(new Option(u.username, String(u.user_id))));
    const cur = conv.assigned_user_id ? String(conv.assigned_user_id) : '';
    if (cur && ![...sel.options].some(o => o.value === cur)) sel.add(new Option(conv.assigned_to || 'Teammate', cur));
    sel.value = cur;
}

async function assignConversation(userId) {
    if (!activeConversationId) return;
    const res = await apiPut(`/api/whatsapp/conversations/${activeConversationId}/assign`, { user_id: userId ? parseInt(userId, 10) : null });
    if (res && res.success) {
        showToast(userId ? 'Conversation assigned.' : 'Conversation unassigned.', 'success');
        loadWhatsAppInbox(activeConversationId);
    } else {
        showToast(errorText(res, 'Could not assign this conversation'), 'error');
        const conv = currentConversationsList.find(c => c.id === activeConversationId);
        if (conv) renderAssignSelect(conv);
    }
}

async function loadConversationMessages(convId, silent = false) {
    const data = await apiGet(`/api/whatsapp/conversations/${convId}/messages?limit=100`);
    if (!data || !data.messages) return;
    
    const msgContainer = document.getElementById('wa-messages-container');
    if (!msgContainer) return;
    
    msgContainer.innerHTML = '';
    
    data.messages.forEach(msg => {
        const bubble = document.createElement('div');
        const isInbound = msg.direction === 'inbound';
        bubble.className = isInbound ? 'chat-bubble-inbound' : 'chat-bubble-outbound';
        
        const timeStr = msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
        let tick = '';
        if (!isInbound) {
            if (msg.status === 'mock') tick = '<span class="text-[10px] text-amber-300" title="Mock mode: not sent">mock</span>';
            else if (msg.status === 'queued') tick = '<span class="text-[10px] text-amber-300">queued</span>';
            else if (msg.status === 'failed') tick = '<span class="text-[10px] text-red-300 font-semibold">failed</span>';
            else if (msg.status === 'read') tick = '<span class="chat-status-tick text-cyan-300 font-bold" title="Read">✓✓</span>';
            else if (msg.status === 'delivered') tick = '<span class="chat-status-tick text-slate-300" title="Delivered">✓✓</span>';
            else tick = '<span class="chat-status-tick text-slate-400" title="Sent">✓</span>';
        }
        
        bubble.innerHTML = `
            <div>${escapeHtml(msg.body).replace(/\\n/g, '<br>')}</div>
            <div class="text-[9px] text-right mt-1 opacity-70 flex justify-end items-center">
                ${msg.sent_by === 'ai' ? '<span class="mr-auto font-semibold" title="Written by the AI">AI</span>' : ''}
                <span>${timeStr}</span>
                ${tick}
            </div>
        `;
        msgContainer.appendChild(bubble);
    });
    
    if (!silent) {
        msgContainer.scrollTop = msgContainer.scrollHeight;
    }
}

async function sendWhatsAppReply(e) {
    if (e) e.preventDefault();
    if (!activeConversationId) return;
    
    const input = document.getElementById('wa-message-input');
    const text = input.value.trim();
    if (!text) return;
    
    input.value = '';
    
    const res = await apiPost(`/api/whatsapp/conversations/${activeConversationId}/messages`, {
        body: text
    });
    
    if (res && res.success) {
        await loadConversationMessages(activeConversationId);
        loadStatus();
    } else {
        showToast(res ? res.error : 'Failed to send WhatsApp message', 'error');
    }
}

function insertCannedReply(text) {
    const input = document.getElementById('wa-message-input');
    if (input) {
        input.value = text;
        input.focus();
    }
}

// --- 2. Contacts CRM ---

async function loadWhatsAppContacts() {
    const search = document.getElementById('wa-contact-search') ? document.getElementById('wa-contact-search').value : '';
    const tag = document.getElementById('wa-contact-tag-filter') ? document.getElementById('wa-contact-tag-filter').value : '';
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    
    await loadContactFields();
    let url = `/api/whatsapp/contacts?search=${encodeURIComponent(search)}&tag=${encodeURIComponent(tag)}` + contactFieldQuery();
    
    const data = await apiGet(url);
    if (!data || !data.contacts) return;
    
    const tbody = document.getElementById('wa-contacts-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (data.contacts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7">${emptyStateHtml('No contacts yet', 'Add your first lead with "+ New Lead". Contacts appear here when customers message this account on WhatsApp.')}</td></tr>`;
        return;
    }
    shownContacts = data.contacts;
    data.contacts.forEach(c => {
        const tr = document.createElement('tr');
        tr.className = "hover:bg-slate-950/40 transition-colors";
        
        const initials = c.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
        const tagPills = (c.tags || ['Lead']).map(t => {
            const colorClass = t.toLowerCase() === 'vip' ? 'bg-amber-500/10 text-amber-300 border-amber-500/30' :
                               (t.toLowerCase() === 'customer' ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' :
                               'bg-indigo-500/10 text-indigo-300 border-indigo-500/30');
            return `<span class="text-[10px] px-2 py-0.5 rounded-full border ${colorClass}">${escapeHtml(t)}</span>`;
        }).join(' ');
        
        tr.innerHTML = `
            <td class="px-5 py-3">
                <div class="flex items-center space-x-3">
                    <div class="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-bold text-xs text-indigo-300">
                        ${initials}
                    </div>
                    <div>
                        <div class="font-medium text-white">${escapeHtml(c.name)}</div>
                        <div class="text-[11px] text-slate-400">${escapeHtml(c.email || 'No email')}</div>
                    </div>
                </div>
            </td>
            <td class="px-5 py-3 font-mono text-xs text-slate-300">
                <a href="https://wa.me/${c.phone.replace(/[^\\d]/g, '')}" target="_blank" class="hover:text-emerald-400 flex items-center gap-1">
                    <span>${escapeHtml(c.phone)}</span>
                    <span class="text-[10px]">↗</span>
                </a>
            </td>
            <td class="px-5 py-3">
                <div class="flex flex-wrap gap-1">${tagPills}</div>
            </td>
            <td class="px-5 py-3 text-xs text-slate-300">${leadSourceHtml(c)}</td>
            <td class="px-5 py-3">${consentHtml(c)}</td>
            <td class="px-5 py-3 text-xs text-slate-400 max-w-xs truncate">
                ${escapeHtml(c.notes || '-')}${customSummaryHtml(c)}
            </td>
            <td class="px-5 py-3 text-right">
                <div class="flex items-center justify-end gap-1.5">
                    ${contactFields.length && can('crm.write') ? `<button type="button" onclick="openContactFields(${Number(c.id)})" class="btn-secondary text-[11px] py-1 px-2.5">Fields</button>` : ''}
                    <button onclick="startChatWithContact(${c.id})" class="btn-secondary text-[11px] py-1 px-2.5 flex items-center gap-1 text-emerald-400 hover:text-emerald-300">
                        <span>💬 Chat</span>
                    </button>
                    ${can('crm.write') ? `<button onclick="openAddDealModal(${c.id}, ${jsAttr(c.name)})" class="btn-secondary text-[11px] py-1 px-2.5 text-indigo-400 hover:text-indigo-300">
                        <span>+ Deal</span>
                    </button>` : ''}
                    ${can('crm.delete') ? `<button aria-label="Delete contact" onclick="deleteContactFromUI(${c.id}, ${jsAttr(c.name)})" class="text-slate-500 hover:text-red-400 p-1">🗑️</button>` : ''}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function startChatWithContact(contactId) {
    const data = await apiGet('/api/whatsapp/conversations?contact_id=' + encodeURIComponent(contactId));
    if (!data || !data.conversations) return;
    const match = data.conversations.find(conv => conv.contact_id === contactId) || data.conversations[0];
    switchTab('wa-inbox');
    await loadWhatsAppInbox();
    if (match) {
        // An empty conversation is hidden from the default list: add it so it can be opened.
        if (!currentConversationsList.some(c => c.id === match.id)) currentConversationsList.unshift(match);
        selectConversation(match.id, true);
    }
}

async function deleteContactFromUI(id, name) {
    if (!confirm(`Are you sure you want to delete contact "${name}"?`)) return;
    const res = await apiDelete(`/api/whatsapp/contacts/${id}`);
    if (res && res.success) {
        showToast(`Contact "${name}" deleted.`, 'info');
        loadWhatsAppContacts();
        loadStatus();
    }
}

// --- 3. Sales Pipeline Kanban ---

async function loadWhatsAppDeals() {
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    const url = '/api/whatsapp/deals';
    
    const data = await apiGet(url);
    if (!data || !data.deals) return;
    
    const stages = ['lead', 'qualified', 'proposal', 'negotiation', 'won'];
    const grouped = { lead: [], qualified: [], proposal: [], negotiation: [], won: [] };
    
    data.deals.forEach(d => {
        const st = (d.stage || 'lead').toLowerCase();
        if (grouped[st]) grouped[st].push(d);
        else grouped.lead.push(d);
    });
    
    stages.forEach(stage => {
        const colEl = document.getElementById(`kanban-cards-${stage}`);
        const countEl = document.getElementById(`kanban-count-${stage}`);
        const totalEl = document.getElementById(`kanban-total-${stage}`);
        if (!colEl) return;
        
        colEl.innerHTML = '';
        const list = grouped[stage];
        const subtotal = list.reduce((sum, d) => sum + (parseFloat(d.value) || 0), 0);
        
        if (countEl) countEl.innerText = list.length;
        if (totalEl) totalEl.innerText = sumByCurrency(list);
        
        list.forEach(deal => {
            const card = document.createElement('div');
            card.className = "kanban-card";
            
            const stageIndex = stages.indexOf(stage);
            const prevStage = stageIndex > 0 ? stages[stageIndex - 1] : null;
            const nextStage = stageIndex < stages.length - 1 ? stages[stageIndex + 1] : null;
            
            const canMove = can('crm.write');
            const prevBtn = (canMove && prevStage) ? `<button onclick="updateDealStage(${deal.id}, '${prevStage}')" class="text-slate-500 hover:text-indigo-400 text-xs px-1" title="Move back to ${prevStage}">←</button>` : '';
            const nextBtn = (canMove && nextStage) ? `<button onclick="updateDealStage(${deal.id}, '${nextStage}')" class="text-slate-500 hover:text-emerald-400 text-xs px-1" title="Advance to ${nextStage}">→</button>` : '';
            
            card.innerHTML = `
                <div class="flex justify-between items-start mb-1.5">
                    <h4 class="font-semibold text-xs text-white leading-snug">${escapeHtml(deal.title)}</h4>
                    ${can('crm.delete') ? `<button aria-label="Delete deal" onclick="deleteDealFromUI(${deal.id})" class="text-slate-600 hover:text-red-400 text-xs ml-1">&times;</button>` : ''}
                </div>
                <div class="text-[11px] text-slate-400 mb-2">${escapeHtml(deal.contact_name || 'Unassigned Contact')}</div>
                <div class="flex justify-between items-center pt-2 border-t border-slate-900 text-xs">
                    <span class="font-bold text-emerald-400">${formatMoney(parseFloat(deal.value) || 0, deal.currency)}</span>
                    <div class="flex items-center gap-1 bg-slate-900 px-1 py-0.5 rounded border border-slate-800">
                        ${prevBtn}
                        <span class="text-[10px] text-slate-500 uppercase">${stage.substring(0, 3)}</span>
                        ${nextBtn}
                    </div>
                </div>
            `;
            colEl.appendChild(card);
        });
    });
}

async function updateDealStage(dealId, newStage) {
    const res = await apiPut(`/api/whatsapp/deals/${dealId}/stage`, { stage: newStage });
    if (res && res.success) {
        showToast(`Deal moved to ${newStage.toUpperCase()}`, 'success');
        loadWhatsAppDeals();
        loadStatus();
    }
}

async function deleteDealFromUI(dealId) {
    if (!confirm('Are you sure you want to delete this deal?')) return;
    const res = await apiDelete(`/api/whatsapp/deals/${dealId}`);
    if (res && res.success) {
        showToast('Deal removed.', 'info');
        loadWhatsAppDeals();
        loadStatus();
    }
}

// --- 4. Broadcast Campaigns ---

async function loadWhatsAppBroadcasts() {
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    const url = '/api/whatsapp/broadcasts';
    
    const data = await apiGet(url);
    if (!data || !data.broadcasts) return;
    
    const container = document.getElementById('wa-broadcasts-container');
    if (!container) return;
    container.innerHTML = '';
    if (data.broadcasts.length === 0) {
        container.innerHTML = emptyStateHtml('No broadcasts yet', 'Create a broadcast to message a tagged group of contacts in this account.');
        return;
    }
    window.lastBroadcasts = data.broadcasts;
    data.broadcasts.forEach(b => {
        const card = document.createElement('div');
        card.className = "bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3";
        
        const isDone = b.status === 'completed';
        const badgeColor = isDone ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-amber-500/10 text-amber-300 border-amber-500/30';
        
        card.innerHTML = `
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="font-bold text-sm text-white">${escapeHtml(b.name)}</h3>
                    <div class="flex items-center gap-2 mt-1">
                        <span class="text-[10px] px-2 py-0.5 rounded-full border ${badgeColor} uppercase tracking-wider font-semibold">${escapeHtml(b.status)}</span>
                        <span class="text-xs text-slate-400">Target: <strong class="text-indigo-300">${escapeHtml(b.target_tag.toUpperCase())}</strong></span>
                    </div>
                </div>
                ${can('broadcasts.run') && b.status !== 'queued' && b.status !== 'completed' ? `<button onclick="runBroadcastFromUI(${b.id})" class="btn-primary text-xs py-1.5 px-3 flex items-center gap-1.5">
                    <span>⚡ Run Broadcast</span>
                </button>` : ''}
            </div>
            
            <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs text-slate-300 font-mono">
                ${escapeHtml(b.template_body)}
            </div>
            
            <div class="grid grid-cols-4 gap-2 pt-2 border-t border-slate-800 text-center">
                <div class="p-2 rounded bg-slate-950/60">
                    <div class="text-[10px] text-slate-400 uppercase font-semibold">Total Leads</div>
                    <div class="text-base font-bold text-white mt-0.5">${b.total_recipients || 0}</div>
                </div>
                <div class="p-2 rounded bg-slate-950/60">
                    <div class="text-[10px] text-slate-400 uppercase font-semibold">Sent</div>
                    <div class="text-base font-bold text-indigo-400 mt-0.5">${b.sent_count || 0}</div>
                </div>
                <div class="p-2 rounded bg-slate-950/60">
                    <div class="text-[10px] text-slate-400 uppercase font-semibold">Delivered</div>
                    <div class="text-base font-bold text-cyan-400 mt-0.5">${b.delivered_count || 0}</div>
                </div>
                <div class="p-2 rounded bg-slate-950/60">
                    <div class="text-[10px] text-slate-400 uppercase font-semibold">Read</div>
                    <div class="text-base font-bold text-emerald-400 mt-0.5">${b.read_count || 0}</div>
                </div>
            </div>
            ${b.queued_count || b.failed_count ? `<p class="text-[11px] text-amber-300">Queued: ${Number(b.queued_count || 0)} · Failed: ${Number(b.failed_count || 0)}</p>` : ''}
            <details class="text-xs" ontoggle="if (this.open) loadRecipients(${Number(b.id)}, this)">
                <summary class="cursor-pointer text-cyan-400">Recipients</summary>
                <div class="mt-2 max-h-60 overflow-y-auto" aria-live="polite"></div>
            </details>
        `;
        container.appendChild(card);
    });
}

async function loadRecipients(id, details) {
    const box = details.querySelector('div');
    box.innerHTML = '<p class="text-slate-400">Loading...</p>';
    const data = await apiCall('GET', `/api/whatsapp/broadcasts/${id}/recipients`, undefined, { quiet: true });
    if (!data || !data.recipients) { box.innerHTML = '<p class="text-amber-300">Could not load recipients. Close and open to retry.</p>'; return; }
    box.innerHTML = data.recipients.length ? '<ul>' + data.recipients.map(r => `<li class="flex flex-wrap justify-between gap-2 border-t border-slate-800 py-1.5">
            <span class="text-slate-200">${escapeHtml(r.name || r.phone)} <span class="text-slate-500">${escapeHtml(r.phone)}</span></span>
            <span class="${r.status === 'failed' ? 'text-red-300' : 'text-slate-300'}">${escapeHtml(r.status)}${r.error_message ? `: ${escapeHtml(r.error_message)}` : ''}</span>
        </li>`).join('') + '</ul>' : '<p class="text-slate-400">No messages yet. Skipped contacts are not listed.</p>';
}

async function runBroadcastFromUI(broadcastId) {
    const bc = (window.lastBroadcasts || []).find(x => x.id === broadcastId);
    const cd = await apiGet('/api/whatsapp/contacts');
    broadcastContacts = (cd && cd.contacts) || [];
    if (bc && bc.template_name) await ensureTemplates();
    const split = bc ? broadcastSplit(bc.target_tag, bc.template_name) : null;
    if (split && split.send === 0) { showToast(`Nothing would be sent. ${split.text}`, 'error'); return; }
    if (!confirm(split ? `Send this broadcast now? ${split.text}` : 'Send this broadcast now to everyone in its audience?')) return;
    showToast('Queuing the broadcast...', 'info');
    const res = await apiPost(`/api/whatsapp/broadcasts/${broadcastId}/run`, {});
    if (res && res.success) {
        showToast(broadcastResult(res.stats), 'success');
        loadWhatsAppBroadcasts();
        loadStatus();
    } else {
        showToast('Broadcast execution failed', 'error');
    }
}

// --- 5. No-Code Automations Engine ---

async function loadWhatsAppAutomations() {
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    const url = '/api/whatsapp/automations';
    
    const data = await apiGet(url);
    if (!data || !data.automations) return;
    
    const container = document.getElementById('wa-automations-container');
    if (!container) return;
    container.innerHTML = '';
    if (data.automations.length === 0) {
        container.innerHTML = emptyStateHtml('No automations yet', 'Add a rule, for example a welcome reply or a keyword responder, for this account.');
        return;
    }
    data.automations.forEach(a => {
        const card = document.createElement('div');
        card.className = "bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3";
        
        let icon = '💬';
        let triggerLabel = `Keyword: <code>${escapeHtml(a.trigger_keyword)}</code>`;
        if (a.trigger_type === 'welcome') {
            icon = '👋';
            triggerLabel = 'First Inbound Message from New Contact';
        } else if (a.trigger_type === 'blog_publish') {
            icon = '📰';
            triggerLabel = 'Autonomous Blog Published to GitHub';
        }
        
        card.innerHTML = `
            <div class="flex justify-between items-start">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-xl">
                        ${icon}
                    </div>
                    <div>
                        <h3 class="font-bold text-sm text-white">${escapeHtml(a.name)}</h3>
                        <div class="text-xs text-slate-400 mt-0.5">Trigger: ${triggerLabel}</div>
                    </div>
                </div>
                
                <div class="flex items-center gap-3">
                    <span class="text-xs text-slate-500 font-mono">${a.executions_count || 0} runs</span>
                    <label class="switch">
                        <input type="checkbox" aria-label="Rule on or off" ${can('automations.manage') ? '' : 'disabled'} ${a.is_active ? 'checked' : ''} onchange="toggleAutomationRule(${a.id}, this.checked)">
                        <span class="slider"></span>
                    </label>
                    ${can('automations.manage') ? `<button aria-label="Delete automation" onclick="deleteAutomationRule(${a.id})" class="text-slate-600 hover:text-red-400 text-xs ml-1">🗑️</button>` : ''}
                </div>
            </div>
            
            <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs text-slate-300 font-mono">
                <span class="text-indigo-400 font-semibold block mb-1">Action: Send WhatsApp Reply Template</span>
                ${escapeHtml(a.message_template)}
            </div>
        `;
        container.appendChild(card);
    });
}

async function toggleAutomationRule(id, isChecked) {
    const res = await apiPut(`/api/whatsapp/automations/${id}/toggle`, { is_active: isChecked });
    if (res && res.success) {
        showToast(`Automation rule ${isChecked ? 'Activated' : 'Paused'}.`, 'success');
        loadStatus();
    }
}

async function deleteAutomationRule(id) {
    if (!confirm('Are you sure you want to delete this automation rule?')) return;
    const res = await apiDelete(`/api/whatsapp/automations/${id}`);
    if (res && res.success) {
        showToast('Automation rule deleted.', 'info');
        loadWhatsAppAutomations();
        loadStatus();
    }
}

// --- 6. WhatsApp Configuration & Simulator ---

async function loadWhatsAppConfig() {
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    const url = '/api/whatsapp/config';
    
    const cfg = await apiGet(url);
    if (!cfg) return;
    
    if (document.getElementById('wa-cfg-phone-id')) document.getElementById('wa-cfg-phone-id').value = cfg.phone_number_id || '';
    if (document.getElementById('wa-cfg-waba-id')) document.getElementById('wa-cfg-waba-id').value = cfg.waba_id || '';
    if (document.getElementById('wa-cfg-token')) {
        document.getElementById('wa-cfg-token').value = '';
        document.getElementById('wa-cfg-token').placeholder = (cfg.has_token || cfg.access_token) ? `Saved (${cfg.token_masked || 'hidden'}). Leave blank to keep it` : 'Paste the access token from Meta';
    }
    if (document.getElementById('wa-cfg-verify-token')) document.getElementById('wa-cfg-verify-token').value = cfg.verify_token || '';
    window.__mock = cfg.mock_mode === true;
    const mkb = document.getElementById('wa-mock-badge'); if (mkb) mkb.classList.toggle('hidden', !window.__mock);
    const mb = document.getElementById('wa-mode-badge');
    if (mb && typeof cfg.mock_mode === 'boolean') {
        mb.classList.remove('hidden');
        mb.className = 'text-xs px-2 py-0.5 rounded-full border flex items-center gap-1 font-normal ' + (cfg.mock_mode ? 'bg-amber-500/10 text-amber-300 border-amber-500/30' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30');
        mb.innerText = cfg.mock_mode ? 'Mock mode: messages are not sent' : 'Live';
    }
    const simCard = document.getElementById('wa-sim-card');
    if (simCard) simCard.classList.toggle('hidden', !(cfg.mock_mode === true && can('wa.config')));
    const hint = document.getElementById('wa-webhook-url-display');
    if (hint) {
        const path = cfg.webhook_url || cfg.webhook_path || '';
        hint.value = path ? (path.startsWith('http') ? path : window.location.origin + path) : window.location.origin + '/api/webhook/whatsapp';
    }
    const sec = document.getElementById('wa-cfg-app-secret');
    if (sec) { sec.value = ''; sec.placeholder = cfg.has_app_secret ? 'Saved. Leave blank to keep it' : 'Paste the Meta app secret'; }
    const st = document.getElementById('wa-cfg-status');
    if (st) st.innerText = !cfg.configured ? 'Not set up yet.' : (cfg.has_app_secret ? 'Connected. Webhook signatures are checked.' : 'Needs the app secret: Meta messages are rejected without it.');
    if (document.getElementById('wa-cfg-biz-name')) document.getElementById('wa-cfg-biz-name').value = cfg.business_name || '';
    if (can('wa.config')) initWaWizard();
}

async function saveWhatsAppConfig(e) {
    if (e) e.preventDefault();
    const payload = {
        phone_number_id: document.getElementById('wa-cfg-phone-id').value,
        waba_id: document.getElementById('wa-cfg-waba-id').value,
        access_token: document.getElementById('wa-cfg-token').value,
        app_secret: (document.getElementById('wa-cfg-app-secret') || {}).value || '',
        business_name: document.getElementById('wa-cfg-biz-name').value
    };
    
    const res = await apiPost('/api/whatsapp/config', payload);
    if (res && res.success) {
        showToast('WhatsApp credentials saved.', 'success');
        await loadWhatsAppConfig();
        if (res.verify_token) {
            const vt = document.getElementById('wa-cfg-verify-token');
            if (vt) vt.value = res.verify_token;
            const once = document.getElementById('wa-verify-once');
            if (once) once.classList.remove('hidden');
        }
        await refreshWaStatus();
        waGoStep(2);
    } else if (!res) {
        showToast('Could not save the WhatsApp settings.', 'error');
    }
}

async function simulateIncomingWhatsApp(e) {
    if (e) e.preventDefault();
    const name = document.getElementById('wa-sim-name').value;
    const phone = document.getElementById('wa-sim-phone').value;
    const msg = document.getElementById('wa-sim-message').value;
    
    showToast('Simulating incoming WhatsApp webhook event...', 'info');
    
    const res = await apiPost('/api/whatsapp/simulate-incoming', {
        name,
        phone,
        message: msg
    });
    
    if (res && res.success) {
        showToast('Inbound message delivered and auto-responders executed!', 'success');
        switchTab('wa-inbox');
        loadWhatsAppInbox();
        loadStatus();
    } else {
        showToast('Simulation failed.', 'error');
    }
}

// --- 7. Modals Controllers for WhatsApp CRM ---

function openAddContactModal() {
    loadContactFields().then(() => renderCustomInputs('new-contact-custom', {}));
    document.getElementById('modal-add-contact').classList.remove('hidden');
}
function closeAddContactModal() {
    document.getElementById('modal-add-contact').classList.add('hidden');
}
async function submitAddContact(e) {
    e.preventDefault();
    const name = document.getElementById('new-contact-name').value;
    const phone = document.getElementById('new-contact-phone').value;
    const email = document.getElementById('new-contact-email').value;
    const tags = document.getElementById('new-contact-tags').value.split(',').map(t => t.trim()).filter(Boolean);
    const notes = document.getElementById('new-contact-notes').value;
    
    const res = await apiPost('/api/whatsapp/contacts', { name, phone, email, tags, notes, ...(contactFields.length ? { custom: readCustom('new-contact-custom', true) } : {}) });
    if (res && res.success) {
        showToast(`Contact "${name}" added.`, 'success');
        closeAddContactModal();
        loadWhatsAppContacts();
        loadStatus();
    } else {
        showToast(res ? res.error : 'Failed to add contact', 'error');
    }
}

function openAddDealModal(contactId = null, contactName = '') {
    if (contactId) {
        document.getElementById('new-deal-contact-id').value = contactId;
        document.getElementById('new-deal-title').value = `${contactName} - Blog & CRM Setup`;
    }
    document.getElementById('modal-add-deal').classList.remove('hidden');
}
function closeAddDealModal() {
    document.getElementById('modal-add-deal').classList.add('hidden');
}
async function submitAddDeal(e) {
    e.preventDefault();
    const title = document.getElementById('new-deal-title').value;
    const value = parseFloat(document.getElementById('new-deal-value').value) || 0;
    const stage = document.getElementById('new-deal-stage').value;
    const contact_id = document.getElementById('new-deal-contact-id').value || null;
    const expected_close = document.getElementById('new-deal-close').value;
    const notes = document.getElementById('new-deal-notes').value;
    
    const currency = document.getElementById('new-deal-currency').value || 'INR';
    const res = await apiPost('/api/whatsapp/deals', { title, value, currency, stage, contact_id, expected_close, notes });
    if (res && res.success) {
        showToast(`Deal "${title}" added to pipeline!`, 'success');
        closeAddDealModal();
        loadWhatsAppDeals();
        loadStatus();
    } else {
        showToast(res ? res.error : 'Failed to create deal', 'error');
    }
}

let broadcastContacts = [];
async function openAddBroadcastModal() {
    document.getElementById('modal-add-broadcast').classList.remove('hidden');
    const d = await apiGet('/api/whatsapp/contacts');
    broadcastContacts = (d && d.contacts) || [];
    const sel = document.getElementById('new-broadcast-tag');
    const prev = sel.value;
    sel.innerHTML = '';
    sel.add(new Option('All contacts', 'all'));
    const tags = [...new Set(broadcastContacts.flatMap(c => c.tags || []))].sort((a, b) => a.localeCompare(b));
    tags.forEach(t => sel.add(new Option(t, t)));
    if ([...sel.options].some(o => o.value === prev)) sel.value = prev;
    updateBroadcastAudience();
    fillTemplatePicker('bc');
}
function broadcastAudienceCount(tag) {
    if (!tag || tag === 'all') return broadcastContacts.length;
    return broadcastContacts.filter(c => (c.tags || []).some(t => String(t).toLowerCase() === tag.toLowerCase())).length;
}
function broadcastSplit(tag, templateName) {
    const audience = !tag || tag === 'all' ? broadcastContacts
        : broadcastContacts.filter(c => (c.tags || []).some(t => String(t).toLowerCase() === tag.toLowerCase()));
    const t = approvedTemplates.find(x => x.name === templateName);
    const marketing = !!t && String(t.category).toUpperCase() === 'MARKETING';
    const optedOut = audience.filter(c => c.consent_status === 'opted_out').length;
    const notOptedIn = marketing ? audience.filter(c => c.consent_status !== 'opted_in' && c.consent_status !== 'opted_out').length : 0;
    const send = audience.length - optedOut - notOptedIn;
    const why = [optedOut ? `${optedOut} opted out` : '', notOptedIn ? `${notOptedIn} not opted in` : ''].filter(Boolean).join(', ');
    return { send, skipped: optedOut + notOptedIn, text: `Will send to ${send}, skip ${optedOut + notOptedIn}${why ? ` (${why})` : ''}.` };
}
function updateBroadcastAudience() {
    const el = document.getElementById('new-broadcast-count');
    const sel = document.getElementById('new-broadcast-tag');
    if (!el || !sel) return;
    const t = pickedTemplate('bc');
    el.innerText = broadcastSplit(sel.value, t && t.name).text;
}
function closeAddBroadcastModal() {
    document.getElementById('modal-add-broadcast').classList.add('hidden');
}
async function submitAddBroadcast(e) {
    e.preventDefault();
    const name = document.getElementById('new-broadcast-name').value;
    const target_tag = document.getElementById('new-broadcast-tag').value;
    const choice = templateChoice('bc');
    if (!choice) return;
    const auto_send = document.getElementById('new-broadcast-send-now').checked;
    if (auto_send) {
        const split = broadcastSplit(target_tag, choice.template_name);
        if (split.send === 0) { showToast(`Nothing would be sent. ${split.text}`, 'error'); return; }
        if (!confirm(`Send this now? ${split.text}`)) return;
    }
    const res = await apiPost('/api/whatsapp/broadcasts', { name, target_tag, auto_send, ...choice });
    if (res && res.success) {
        showToast(res.stats ? broadcastResult(res.stats) : `Broadcast "${name}" created.`, res.stats && res.stats.success === false ? 'error' : 'success');
        closeAddBroadcastModal();
        loadWhatsAppBroadcasts();
        loadStatus();
    } else {
        showToast(errorText(res, 'Failed to create broadcast'), 'error');
    }
}

function openAddAutomationModal() {
    document.getElementById('modal-add-automation').classList.remove('hidden');
    updateAutomationFields();
}
function closeAddAutomationModal() {
    document.getElementById('modal-add-automation').classList.add('hidden');
}
async function submitAddAutomation(e) {
    e.preventDefault();
    const name = document.getElementById('new-auto-name').value;
    const trigger_type = document.getElementById('new-auto-trigger').value;
    const trigger_keyword = document.getElementById('new-auto-keyword').value;
    const message_template = document.getElementById('new-auto-template').value;
    
    let choice = {};
    if (trigger_type === 'blog_publish') { choice = templateChoice('au'); if (!choice) return; }
    const res = await apiPost('/api/whatsapp/automations', { name, trigger_type, trigger_keyword, message_template, ...choice });
    if (res && res.success) {
        showToast(`Automation rule "${name}" created!`, 'success');
        closeAddAutomationModal();
        loadWhatsAppAutomations();
        loadStatus();
    } else {
        showToast(errorText(res, 'Failed to create automation'), 'error');
    }
}



// ====================================================================
// Roles, permissions and Users & Roles screen
// Server is the authority; this only hides actions the user cannot use.
// ====================================================================

// Fallback map used until /api/auth/me returns a `permissions` list.
const ROLE_PERMISSIONS = {
    owner:  ['content.write', 'ai.manage', 'crm.read', 'crm.write', 'crm.delete', 'wa.config', 'automations.manage', 'broadcasts.run', 'content.read', 'content.publish', 'users.manage', 'audit.read', 'account.manage'],
    admin:  ['content.write', 'ai.manage', 'crm.read', 'crm.write', 'crm.delete', 'wa.config', 'automations.manage', 'broadcasts.run', 'content.read', 'content.publish', 'users.manage', 'audit.read'],
    agent:  ['content.write', 'crm.read', 'crm.write', 'content.read'],
    viewer: ['crm.read', 'content.read']
};
const ROLE_HELP = {
    owner: 'Full control, including users and billing.',
    admin: 'Manage CRM, WhatsApp setup, publishing and users.',
    agent: 'Work with contacts, chats and deals. No setup or user changes.',
    viewer: 'Read only.'
};

function can(permission) {
    if (!currentUser) return false;
    const list = Array.isArray(window.__perms) ? window.__perms : (ROLE_PERMISSIONS[currentUser.role] || []);
    return list.includes(permission);
}

function isPlatformAdmin() { return !!window.__platformAdmin; }

function applyRolePermissions() {
    // Create-account, Settings and Supabase belong to the platform admin only.
    document.querySelectorAll('[data-platform-admin]').forEach(el => el.classList.toggle('hidden', !isPlatformAdmin()));
    ['settings', 'supabase'].forEach(t => {
        const n = document.querySelector(`.sidebar-nav-item[onclick*="switchTab('${t}')"]`);
        if (n) n.classList.toggle('hidden', !isPlatformAdmin());
    });
    document.querySelectorAll('[data-requires]').forEach(el => {
        if (el.id === 'wa-sim-card') return;
        el.classList.toggle('hidden', !can(el.getAttribute('data-requires')));
    });
    document.querySelectorAll('[data-perm-disable]').forEach(el => { el.disabled = !can(el.getAttribute('data-perm-disable')); });
    const nav = document.getElementById('nav-users');
    if (nav) nav.classList.toggle('hidden', !can('users.manage'));
    if (!getActiveAccountId()) {
        // No account chosen: CRM screens have nothing to show and every call would be rejected.
        document.querySelectorAll('.sidebar-nav-item[onclick*="switchTab(\'wa-"], #nav-users, #nav-blog-plan').forEach(n => n.classList.add('hidden'));
        document.querySelectorAll('header [onclick^="openAddContactModal"], header [onclick^="openAddDealModal"], header [onclick^="openAddBroadcastModal"]').forEach(n => n.classList.add('hidden'));
    }
    const cfgNav = document.querySelector("[onclick*=\"switchTab('wa-config')\"]");
    if (cfgNav) cfgNav.classList.toggle('hidden', !can('wa.config'));
    const navGate = { logs: 'audit.read', zeroredeploy: 'content.publish' };
    Object.keys(navGate).forEach(t => {
        const n = document.querySelector(`.sidebar-nav-item[onclick*="switchTab('${t}')"]`);
        if (n) n.classList.toggle('hidden', !can(navGate[t]));
    });
    const ps = document.getElementById('nav-platform-section');
    if (ps) ps.classList.toggle('hidden', ![...ps.querySelectorAll('.sidebar-nav-item')].some(n => !n.classList.contains('hidden')));
    document.querySelectorAll('header [onclick^="openAddProjectModal"]').forEach(b => b.classList.toggle('hidden', !can('content.publish')));
    document.querySelectorAll('header [onclick^="openAddBroadcastModal"]').forEach(b => b.classList.toggle('hidden', !can('broadcasts.run')));
    const bcNote = document.getElementById('wa-bc-viewonly'); if (bcNote) bcNote.classList.toggle('hidden', can('broadcasts.run'));
    const auNote = document.getElementById('wa-auto-viewonly'); if (auNote) auNote.classList.toggle('hidden', can('automations.manage'));
    const write = can('crm.write');
    ['openAddContactModal', 'openAddDealModal'].forEach(fn => {
        document.querySelectorAll(`header [onclick^="${fn}"]`).forEach(b => b.classList.toggle('hidden', !write));
    });
    const anyAction = [...document.querySelectorAll('#top-actions > *')].some(b => !b.classList.contains('hidden'));
    const nb = document.getElementById('new-menu-btn');
    if (nb) nb.style.visibility = anyAction ? '' : 'hidden';
    const roleEl = document.querySelector('.sidebar-footer .text-slate-400');
    if (roleEl && currentUser) roleEl.innerText = isPlatformAdmin() ? 'Platform admin' : (currentUser.role ? currentUser.role.charAt(0).toUpperCase() + currentUser.role.slice(1) : '');
}

function navKey(ev, el) {
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); el.click(); }
}

async function loadUsersAndRoles() {
    const acct = getActiveAccountId();
    const body = document.getElementById('users-table-body');
    const empty = document.getElementById('users-empty');
    if (can('account.manage')) loadAccountSettings();
    const an = document.getElementById('acct-name');
    if (an) { const sl = document.getElementById('client-select-filter'); an.value = sl && sl.selectedOptions[0] ? sl.selectedOptions[0].text : ''; }
    const nameEl = document.getElementById('users-account-name');
    if (nameEl) {
        const sel = document.getElementById('client-select-filter');
        nameEl.innerText = sel && sel.selectedOptions[0] && acct ? sel.selectedOptions[0].text : 'this account';
    }
    if (!body) return;
    body.innerHTML = '';
    if (!acct) {
        empty.innerHTML = emptyStateHtml('Choose a client account', 'Pick an account in the sidebar to see and manage its users.');
        return;
    }
    const roles = can('account.manage') ? ['viewer', 'agent', 'admin', 'owner'] : ['viewer', 'agent', 'admin'];
    const sel = document.getElementById('invite-role');
    if (sel && !sel.options.length) {
        roles.forEach(r => sel.add(new Option(r.charAt(0).toUpperCase() + r.slice(1), r)));
        sel.onchange = () => { document.getElementById('invite-role-help').innerText = ROLE_HELP[sel.value] || ''; };
        sel.onchange();
    }
    const data = await apiGet(`/api/accounts/${encodeURIComponent(acct)}/users`);
    if (!data || !Array.isArray(data.users)) {
        empty.innerHTML = emptyStateHtml('User management is not available yet', 'The server did not return a user list for this account.');
        return;
    }
    empty.innerHTML = data.users.length ? '' : emptyStateHtml('No users in this account yet', 'Invite the first person with the form.');
    const manage = can('users.manage');
    data.users.forEach(u => {
        const tr = document.createElement('tr');
        const uid = u.user_id != null ? u.user_id : u.id;
        const isSelf = currentUser && Number(uid) === Number(currentUser.id);
        const locked = isSelf || (u.role === 'owner' && !can('account.manage'));
        const opts = ['owner', 'admin', 'agent', 'viewer'].filter(r => r !== 'owner' || can('account.manage') || u.role === 'owner').map(r => `<option value="${r}" ${u.role === r ? 'selected' : ''}>${r}</option>`).join('');
        tr.innerHTML = `
            <td class="px-3 sm:px-5 py-3 text-white break-all">${escapeHtml(u.username || u.email || '')}${u.email && u.username ? `<div class="text-[11px] text-slate-400">${escapeHtml(u.email)}</div>` : ''}${u.is_active === false ? '<span class="ml-2 text-[10px] text-amber-300">inactive</span>' : ''}</td>
            <td class="px-5 py-3">${manage && !locked
                ? `<select aria-label="Role for ${escapeHtml(u.username)}" class="input-text text-xs min-w-[6.5rem]" onchange="changeUserRole(${Number(uid)}, this.value)">${opts}</select>`
                : `<span class="text-xs text-slate-300">${escapeHtml(u.role)}</span>`}</td>
            <td class="px-5 py-3 text-right">${manage && !locked
                ? `<button class="btn-secondary text-[11px] py-1 px-2.5 mr-1" onclick="resetUserPassword(${Number(uid)}, ${jsAttr(u.username)})">Reset password</button><button class="btn-secondary text-[11px] py-1 px-2.5 text-red-400" onclick="revokeUser(${Number(uid)}, ${jsAttr(u.username)})">Revoke access</button>` : ''}</td>`;
        body.appendChild(tr);
    });
}

async function submitInviteUser(e) {
    e.preventDefault();
    const acct = getActiveAccountId();
    if (!acct) { showToast('Choose a client account first.', 'error'); return; }
    const username = document.getElementById('invite-username').value.trim();
    const role = document.getElementById('invite-role').value;
    const res = await apiPost(`/api/accounts/${encodeURIComponent(acct)}/users`, { username, role });
    if (res && !res.error) {
        const note = document.getElementById('invite-result');
        if (note) note.innerHTML = res.temporary_password
            ? `Account created. Temporary password, shown once: <code class="text-emerald-300">${escapeHtml(res.temporary_password)}</code>. Share it privately and ask them to change it.`
            : 'Existing user added to this account.';
        showToast(res.temporary_password ? 'User created. Copy the temporary password now.' : 'User added.', 'success');
        document.getElementById('invite-username').value = '';
        loadUsersAndRoles();
    } else {
        showToast(errorText(res, 'Could not invite this user.'), 'error');
    }
}

async function changeUserRole(uid, role) {
    const acct = getActiveAccountId();
    const res = await apiPut(`/api/accounts/${encodeURIComponent(acct)}/users/${uid}`, { role });
    showToast(res && !res.error ? 'Role updated.' : errorText(res, 'Could not change role.'), res && !res.error ? 'success' : 'error');
    loadUsersAndRoles();
}

async function revokeUser(uid, name) {
    if (!confirm(`Remove ${name} from this account? They will lose access immediately.`)) return;
    const acct = getActiveAccountId();
    const res = await apiDelete(`/api/accounts/${encodeURIComponent(acct)}/users/${uid}`);
    showToast(res && !res.error ? 'Access revoked.' : errorText(res, 'Could not revoke access.'), res && !res.error ? 'success' : 'error');
    loadUsersAndRoles();
}

function toggleSidebar(force) {
    const sb = document.getElementById('sidebar');
    const bd = document.getElementById('sidebar-backdrop');
    const btn = document.querySelector('.menu-toggle');
    if (!sb) return;
    const open = typeof force === 'boolean' ? force : !sb.classList.contains('open');
    sb.classList.toggle('open', open);
    if (bd) bd.classList.toggle('open', open);
    if (btn) btn.setAttribute('aria-expanded', String(open));
    if (open) { const first = sb.querySelector('select, a, button'); if (first) first.focus(); }
    else if (btn && document.activeElement && sb.contains(document.activeElement)) btn.focus();
}
document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') {
        toggleSidebar(false);
        document.querySelectorAll('.modal-backdrop:not(.hidden)').forEach(m => m.classList.add('hidden'));
    }
});

async function rotateVerifyToken() {
    if (!confirm('Create a new webhook verify token? Update it in Meta, or Meta will stop sending messages.')) return;
    const res = await apiPost('/api/whatsapp/config/verify-token', {});
    if (res && res.verify_token) {
        const el = document.getElementById('wa-cfg-verify-token');
        if (el) el.value = res.verify_token;
        showToast('New verify token created. Copy it now; it is shown once.', 'success');
    } else showToast(errorText(res, 'Could not create a new token.'), 'error');
}

async function renameAccount(e) {
    e.preventDefault();
    const acct = getActiveAccountId();
    const name = document.getElementById('acct-name').value.trim();
    const res = await apiPatch(`/api/accounts/${encodeURIComponent(acct)}`, { name });
    if (res && !res.error) { showToast('Account renamed.', 'success'); await loadClients(); updateAccountBanner(); loadUsersAndRoles(); }
    else showToast(errorText(res, 'Could not rename the account.'), 'error');
}

async function deleteAccount() {
    const acct = getActiveAccountId();
    const sel = document.getElementById('client-select-filter');
    const current = sel && sel.selectedOptions[0] ? sel.selectedOptions[0].text : '';
    const typed = prompt(`This hides "${current}" and all its data from everyone.\nType the account name to confirm:`);
    if (typed === null) return;
    const res = await apiDelete(`/api/accounts/${encodeURIComponent(acct)}`, { confirm_name: typed.trim() });
    if (res && !res.error) {
        showToast('Account deleted.', 'success');
        try { localStorage.removeItem('gitpulse_account'); } catch (e) {}
        if (sel) sel.innerHTML = '';
        await loadClients();
        await onClientFilterChange();
    } else showToast(errorText(res, 'Could not delete the account.'), 'error');
}

async function apiPatch(endpoint, data = {}) {
    try {
        const res = await fetch(endpoint, { method: 'PATCH', headers: getAuthHeaders({ 'Content-Type': 'application/json' }), credentials: 'same-origin', body: JSON.stringify(data) });
        if (res.status === 401) { window.location.href = '/login'; return null; }
        return await res.json();
    } catch (err) { showToast(`Request failed: ${err.message}`, 'error'); return null; }
}


// ====================================================================
// Full-page states: no access, first-login password, "New" menu, modal focus
// ====================================================================
function needsPasswordChange() {
    try { if (localStorage.getItem('gitpulse_must_change') === '1') return true; } catch (e) {}
    return !!(currentUser && currentUser.must_change_password);
}

function showPasswordChange() {
    const o = document.getElementById('overlay-change-password');
    if (o && o.classList.contains('hidden')) { o.classList.remove('hidden'); const f = document.getElementById('chpw-current'); if (f) f.focus(); }
}

async function submitFirstLoginPassword(e) {
    e.preventDefault();
    const msg = document.getElementById('chpw-msg');
    msg.innerText = '';
    if (document.getElementById('chpw-new').value !== document.getElementById('chpw-confirm').value) { msg.innerText = 'The two new passwords do not match.'; return; }
    const res = await apiPost('/api/auth/change-password', {
        current_password: document.getElementById('chpw-current').value,
        new_password: document.getElementById('chpw-new').value
    });
    if (res && !res.error) {
        try { localStorage.removeItem('gitpulse_must_change'); localStorage.removeItem('gitpulse_token'); } catch (err) {}
        document.cookie = 'session_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax';
        window.location.href = '/login';
    } else {
        msg.innerText = (res && (res.error || res.message)) || 'Could not change the password.';
    }
}

function showNoAccess(canCreate) {
    const o = document.getElementById('overlay-no-access');
    if (!o) return;
    const txt = document.getElementById('noaccess-text');
    if (canCreate) {
        document.getElementById('noaccess-h').innerText = 'No client accounts yet';
        txt.innerText = 'Create the first client account to start.';
        o.classList.add('hidden');
        const banner = document.getElementById('account-banner-name');
        if (banner) banner.innerText = 'No account yet. Use "+ New account" in the sidebar.';
        return;
    }
    document.getElementById('noaccess-h').innerText = 'You no longer have access';
    txt.innerText = 'Your access to this client account was removed, or it has not been set up yet. Ask an account owner to add you.';
    o.classList.remove('hidden');
}

function toggleNewMenu(force) {
    const panel = document.getElementById('top-actions');
    const btn = document.getElementById('new-menu-btn');
    if (!panel || !btn) return;
    const open = typeof force === 'boolean' ? force : !panel.classList.contains('open');
    panel.classList.toggle('open', open);
    btn.setAttribute('aria-expanded', String(open));
}

// Focus handling for modals: focus the first field on open, keep Tab inside, restore focus on close.
(function setupModalFocus() {
    const opener = new WeakMap();
    const obs = new MutationObserver(muts => {
        muts.forEach(m => {
            const el = m.target;
            if (!el.id || !el.id.startsWith('modal-')) return;
            if (!el.classList.contains('hidden')) {
                opener.set(el, document.activeElement);
                const f = el.querySelector('input:not([type=hidden]), select, textarea') || el.querySelector('button');
                if (f) setTimeout(() => f.focus(), 30);
            } else {
                const prev = opener.get(el);
                if (prev && prev.focus) prev.focus();
            }
        });
    });
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.modal-backdrop').forEach(m => {
            m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true');
            obs.observe(m, { attributes: true, attributeFilter: ['class'] });
        });
    });
    document.addEventListener('keydown', ev => {
        if (ev.key !== 'Tab') return;
        let m = document.querySelector('.modal-backdrop:not(.hidden)');
        const pw = document.getElementById('overlay-change-password');
        if (pw && !pw.classList.contains('hidden')) m = pw;
        if (!m) return;
        const f = [...m.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select, textarea')].filter(x => x.offsetParent !== null);
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
        else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    });
})();

async function resetUserPassword(uid, name) {
    if (!confirm(`Create a new temporary password for ${name}? Their current sessions end immediately.`)) return;
    const acct = getActiveAccountId();
    const res = await apiPost(`/api/accounts/${encodeURIComponent(acct)}/users/${uid}/reset-password`, {});
    const note = document.getElementById('invite-result');
    if (res && res.temporary_password) {
        if (note) {
            note.innerHTML = `New temporary password for <strong>${escapeHtml(name)}</strong>, shown once: <code id="tmp-pw" class="text-emerald-300">${escapeHtml(res.temporary_password)}</code> <button type="button" class="btn-secondary text-[11px] py-0.5 px-2" onclick="copyTempPassword()">Copy</button>`;
        }
        showToast('Password reset. Copy it now.', 'success');
    } else {
        showToast(errorText(res, 'Could not reset the password.'), 'error');
    }
}

function copyTempPassword() {
    const el = document.getElementById('tmp-pw');
    if (!el) return;
    navigator.clipboard.writeText(el.innerText).then(() => {
        showToast('Copied. It will not be shown again.', 'success');
        const note = document.getElementById('invite-result');
        if (note) note.innerText = 'Password copied. It is no longer shown.';
    });
}


async function loadAccountSettings() {
    const cfg = await apiGet('/api/account/settings');
    if (!cfg || cfg.error) return;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    if (cfg.ai_provider) set('set-ai-provider', cfg.ai_provider);
    const key = document.getElementById('set-ai-key');
    if (key) { key.value = ''; key.placeholder = cfg.has_ai_api_key ? `Saved (${cfg.ai_api_key_masked || 'hidden'})` : 'Paste a key'; }
    const gh = document.getElementById('set-gh-token');
    if (gh) { gh.value = ''; gh.placeholder = cfg.has_github_token ? `Saved (${cfg.github_token_masked || 'hidden'})` : 'Paste a token'; }
    const src = document.getElementById('set-ai-source');
    if (src) src.innerText = cfg.ai_key_source === 'account' ? 'Using this account\'s own key.' : 'Using the platform key until you add one.';
    const acct = (window.__accounts || []).find(a => String(a.id) === String(getActiveAccountId()));
    if (window.__acctCurrency) { set('set-currency', window.__acctCurrency); set('new-deal-currency', window.__acctCurrency); }
}

async function saveAccountSettings(e) {
    e.preventDefault();
    const val = id => (document.getElementById(id) || {}).value || '';
    const body = { ai_provider: val('set-ai-provider') };
    if (val('set-ai-key')) body.ai_api_key = val('set-ai-key');
    if (val('set-gh-token')) body.github_token = val('set-gh-token');
    if ((document.getElementById('set-ai-clear') || {}).checked) body.clear_ai_key = true;
    if ((document.getElementById('set-gh-clear') || {}).checked) body.clear_github_token = true;
    const res = await apiPost('/api/account/settings', body);
    const cur = await apiPatch(`/api/accounts/${encodeURIComponent(getActiveAccountId())}`, { default_currency: val('set-currency') });
    if (res && !res.error && cur && !cur.error) {
        showToast('Settings saved.', 'success');
        ['set-ai-clear', 'set-gh-clear'].forEach(i => { const c = document.getElementById(i); if (c) c.checked = false; });
        await loadClients();
        await refreshMe();
        loadAccountSettings();
    } else showToast(errorText(res && res.error ? res : cur, 'Could not save settings.'), 'error');
}



// --- WhatsApp setup wizard (4 steps) ---
let waStep = 1, waStatus = null, waPoll = null, waWizardAccount = null;
const WA_STEP_NAMES = ['Credentials', 'Webhook', 'Test', 'Done'];

function waDone(n) {
    const st = waStatus; if (!st) return false;
    const c = st.credentials || {};
    if (n === 1) return !!(c.phone_number_id && c.access_token && c.app_secret);
    if (n === 2) return !!st.last_webhook_at;
    if (n === 3) return !!(st.last_test && st.last_test.ok);
    return !!st.ready;
}

function renderWaStepper() {
    const ol = document.getElementById('wa-stepper'); if (!ol) return;
    ol.innerHTML = WA_STEP_NAMES.map((name, i) => {
        const n = i + 1, active = n === waStep, done = waDone(n);
        const cls = active ? 'border-indigo-400 text-white bg-indigo-500/10' : (done ? 'border-emerald-500/40 text-emerald-300' : 'border-slate-700 text-slate-400');
        return `<li><button type="button" onclick="waGoStep(${n})" ${active ? 'aria-current="step"' : ''} class="w-full text-left border rounded-lg px-2 py-2 min-h-[44px] ${cls}"><span class="font-semibold">${done && !active ? '&#10003;' : n}</span> <span class="block truncate">${name}</span></button></li>`;
    }).join('');
}

function renderWaStatus() {
    renderWaStepper();
    const st = waStatus;
    const hook = st && st.last_webhook_at
        ? `Meta has reached us (last message ${new Date(st.last_webhook_at).toLocaleString()}).`
        : 'Waiting for Meta. Send a WhatsApp message to your business number once the webhook is saved.';
    ['wa-hook-state', 'wa-hook-state-3'].forEach(id => { const e = document.getElementById(id); if (e) e.innerText = st ? hook : ''; });
    const tr = document.getElementById('wa-test-result');
    if (tr && st && st.last_test) {
        tr.innerText = (st.last_test.ok ? 'Passed: ' : 'Failed: ') + (st.last_test.message || '');
        tr.className = 'text-xs ' + (st.last_test.ok ? 'text-emerald-300' : 'text-red-300');
    }
    const box = document.getElementById('wa-done-box');
    if (box && st) {
        if (st.ready) {
            box.className = 'rounded-lg border p-4 text-sm bg-emerald-500/10 border-emerald-500/40 text-emerald-200';
            box.innerText = 'Connected. Meta is delivering messages to this account' + (st.mock_mode ? ' (mock mode: nothing is sent to real customers).' : '.');
        } else {
            const miss = [];
            const c = st.credentials || {};
            if (!(c.phone_number_id && c.access_token)) miss.push('save the Phone Number ID and access token (step 1)');
            if (!c.app_secret) miss.push('save the Meta app secret (step 1)');
            if (!st.last_webhook_at) miss.push('connect the webhook in Meta and send one message to your number (step 2)');
            box.className = 'rounded-lg border p-4 text-sm bg-amber-500/10 border-amber-500/40 text-amber-200';
            box.innerText = 'Not connected yet. Still to do: ' + (miss.join('; ') || 'wait a moment and check again') + '.';
        }
    }
    if (st && st.ready) stopWaPoll();
}

async function refreshWaStatus() {
    const s = await apiCall('GET', '/api/whatsapp/connection-status', undefined, { quiet: true });
    if (s && !s.error) { waStatus = s; renderWaStatus(); }
    return s;
}

function stopWaPoll() { if (waPoll) { clearInterval(waPoll); waPoll = null; } }
function startWaPoll() {
    if (waPoll) return;
    waPoll = setInterval(() => {
        const tab = document.getElementById('tab-wa-config');
        if (!tab || tab.classList.contains('hidden')) return;
        refreshWaStatus();
    }, 5000);
}

function waGoStep(n) {
    waStep = n;
    document.querySelectorAll('#tab-wa-config .wa-step').forEach(el => el.classList.toggle('hidden', el.dataset.step !== String(n)));
    if (n >= 2) startWaPoll(); else stopWaPoll();
    renderWaStatus();
}

async function initWaWizard() {
    const acct = getActiveAccountId();
    const first = waWizardAccount !== acct;
    waWizardAccount = acct;
    const s = await refreshWaStatus();
    if (!first) return;
    waStatus = (s && !s.error) ? s : null;
    const skip = document.getElementById('wa-skip-1');
    if (skip) skip.classList.toggle('hidden', !waDone(1));
    waGoStep(waDone(4) ? 4 : (waDone(1) ? 2 : 1));
}

async function waRunTest() {
    const btn = document.getElementById('wa-test-btn');
    const out = document.getElementById('wa-test-result');
    if (btn) btn.disabled = true;
    if (out) { out.className = 'text-xs text-slate-300'; out.innerText = 'Testing...'; }
    const res = await apiPost('/api/whatsapp/config/test', {});
    if (btn) btn.disabled = false;
    if (res && !res.error) {
        if (out) { out.className = 'text-xs ' + (res.ok ? 'text-emerald-300' : 'text-red-300'); out.innerText = (res.ok ? 'Passed: ' : 'Failed: ') + (res.message || ''); }
    } else if (out) { out.className = 'text-xs text-red-300'; out.innerText = 'Test could not run.'; }
    await refreshWaStatus();
}

// --- Phase 1: AI assistant, handoff, alerts, templates, consent, lead source ---
const LEAD_SOURCES = { website: 'Website', ad: 'Ad (click to WhatsApp)', direct: 'Direct', manual: 'Added by team' };
const CONSENT_LABELS = { unknown: 'Not recorded', opted_in: 'Opted in', opted_out: 'Opted out' };
const fmtWhen = v => v ? new Date(v).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
const cardClass = 'bg-slate-900 border border-slate-800 rounded-xl p-4';
const lines = id => document.getElementById(id).value.split('\n').map(x => x.trim()).filter(Boolean);
const joined = v => Array.isArray(v) ? v.join('\n') : (v || '');

function leadSourceHtml(c) {
    const label = LEAD_SOURCES[c.source] || c.source || '-';
    let detail = c.source_detail || '';
    if (detail.startsWith('{')) {
        try { const d = JSON.parse(detail); detail = d.headline || (d.source_id ? `Ad ${d.source_id}` : ''); } catch (e) { detail = ''; }
    }
    return escapeHtml(label) + (detail ? `<div class="text-[10px] text-slate-500">${escapeHtml(detail)}</div>` : '');
}

function consentHtml(c) {
    const v = CONSENT_LABELS[c.consent_status] ? c.consent_status : 'unknown';
    const meta = [c.consent_source, fmtWhen(c.consent_at)].filter(Boolean).join(' · ');
    const when = meta ? `<div class="text-[10px] text-slate-500">${escapeHtml(meta)}</div>` : '';
    const role = currentUser && currentUser.role;
    if (!(role === 'owner' || role === 'admin' || isPlatformAdmin()) || !can('automations.manage')) return `<span class="text-xs ${v === 'opted_out' ? 'text-red-300 font-semibold' : 'text-slate-300'}">${CONSENT_LABELS[v]}</span>${when}`;
    const options = Object.keys(CONSENT_LABELS).map(k => `<option value="${k}" ${k === v ? 'selected' : ''}>${CONSENT_LABELS[k]}</option>`).join('');
    return `<select aria-label="Consent for ${escapeHtml(c.name)}" class="input-select text-xs py-1 min-w-[9rem] ${v === 'opted_out' ? 'text-red-300' : ''}" onchange="setConsent(${Number(c.id)}, this.value, '${v}', this)">${options}</select>${when}`;
}

async function setConsent(id, value, previous, select) {
    let source = '';
    if (value === 'opted_in') {
        source = (prompt('How did this person agree to receive messages? (for example: website form, 25 Nov)') || '').trim();
        if (!source) { select.value = previous; return; }
    }
    const res = await apiPut(`/api/whatsapp/contacts/${id}/consent`, { status: value, source: source || 'set by team' });
    if (res && res.success) { showToast('Consent saved.', 'success'); loadWhatsAppContacts(); }
    else select.value = previous;
}

let conversationAiOn = true;
function renderNeedsHuman(conv) {
    const box = document.getElementById('wa-needs-human');
    if (!box) return;
    box.classList.toggle('hidden', !conv.id);
    conversationAiOn = conv.ai_mode !== 'off' && !conv.needs_human;
    renderWindow(conv);
    document.getElementById('wa-needs-human-text').innerText = conv.needs_human
        ? `Needs a person${conv.handoff_reason ? ': ' + conv.handoff_reason : ''}`
        : conversationAiOn ? 'AI is answering this chat.' : 'AI is off for this chat.';
    document.getElementById('wa-ai-btn').innerText = conversationAiOn ? 'Take over' : 'Resume AI';
}

async function toggleConversationAi() {
    const id = activeConversationId;
    if (!id) return;
    const mode = conversationAiOn ? 'off' : 'on';
    const res = await apiPost(`/api/whatsapp/conversations/${id}/ai`, { mode });
    if (res && !res.error) { showToast(mode === 'on' ? 'AI resumed.' : 'You have taken over. The AI will stay silent.', 'success'); loadWhatsAppInbox(id); }
}

function addFaqRow(item = {}) {
    const row = document.createElement('div');
    row.className = 'kb-faq-row border border-slate-800 rounded-lg p-3 space-y-2';
    row.innerHTML = `<input class="input-text text-sm w-full" data-f="question" aria-label="Question" placeholder="Question">
        <textarea class="input-text text-sm w-full" data-f="answer" rows="2" aria-label="Answer" placeholder="Answer"></textarea>
        <button type="button" class="btn-secondary text-xs" onclick="this.parentElement.remove()">Remove</button>`;
    row.querySelector('[data-f=question]').value = item.question || '';
    row.querySelector('[data-f=answer]').value = item.answer || '';
    document.getElementById('kb-faq').appendChild(row);
}

function addPriceRow(item = {}) {
    const row = document.createElement('div');
    row.className = 'kb-price-row flex flex-wrap items-center gap-2';
    row.innerHTML = `<input class="input-text text-sm flex-1 min-w-[10rem]" data-f="text" aria-label="Price item" placeholder="Item and price">
        <label class="flex items-center gap-1 text-xs text-slate-300"><input type="checkbox" data-f="quote" class="w-4 h-4"> AI may quote</label>
        <button type="button" class="btn-secondary text-xs" onclick="this.parentElement.remove()">Remove</button>`;
    row.querySelector('[data-f=text]').value = item.text || '';
    row.querySelector('[data-f=quote]').checked = !!item.ai_may_quote;
    document.getElementById('kb-prices').appendChild(row);
}

function fillKnowledge(k) {
    document.getElementById('kb-ai-enabled').checked = !!k.ai_enabled;
    document.getElementById('kb-facts').value = joined(k.business_facts);
    document.getElementById('kb-locations').value = joined(k.locations);
    document.getElementById('kb-tone').value = k.tone || '';
    document.getElementById('kb-languages').value = joined(k.languages);
    document.getElementById('kb-banned').value = joined(k.banned_claims);
    document.getElementById('kb-handoff').value = k.handoff_message || '';
    document.getElementById('kb-faq').innerHTML = '';
    (k.faqs || []).forEach(addFaqRow);
    document.getElementById('kb-prices').innerHTML = '';
    (k.price_items || []).forEach(addPriceRow);
}

async function loadKnowledge() {
    if (!getActiveAccountId()) return;
    const fields = document.getElementById('kb-fields');
    const status = document.getElementById('kb-status');
    fields.disabled = true;
    document.getElementById('ai-viewonly').classList.toggle('hidden', can('ai.manage'));
    const acct = getActiveAccountId();
    const data = await apiGet('/api/ai/knowledge');
    if (acct !== getActiveAccountId()) return;
    // Saving over a failed load would wipe the stored knowledge, so the form stays locked.
    if (!data || data.error) { fillKnowledge({}); status.innerText = 'Could not load the AI settings. Nothing can be saved until they load.'; return; }
    const k = data.knowledge || data;
    fillKnowledge(k);
    fields.disabled = !can('ai.manage');
    status.innerText = k.ai_enabled ? 'On. Chats the AI cannot answer are marked "Needs human".' : 'Off. Your team answers every message.';
}

async function saveKnowledge(e) {
    e.preventDefault();
    const val = id => document.getElementById(id).value.trim();
    const body = {
        ai_enabled: document.getElementById('kb-ai-enabled').checked,
        business_facts: val('kb-facts'), locations: val('kb-locations'), tone: val('kb-tone'),
        languages: lines('kb-languages'), banned_claims: lines('kb-banned'), handoff_message: val('kb-handoff'),
        faqs: [...document.querySelectorAll('.kb-faq-row')].map(r => ({ question: r.querySelector('[data-f=question]').value.trim(), answer: r.querySelector('[data-f=answer]').value.trim() })).filter(x => x.question && x.answer),
        price_items: [...document.querySelectorAll('.kb-price-row')].map(r => ({ text: r.querySelector('[data-f=text]').value.trim(), ai_may_quote: r.querySelector('[data-f=quote]').checked })).filter(x => x.text)
    };
    const res = await apiPut('/api/ai/knowledge', body);
    if (res && !res.error) { showToast('AI settings saved.', 'success'); loadKnowledge(); }
}

async function testQuestion(e) {
    e.preventDefault();
    const out = document.getElementById('kb-test-result');
    const btn = document.getElementById('kb-test-btn');
    btn.disabled = true;
    out.innerText = 'Asking...';
    const res = await apiPost('/api/ai/test', { question: document.getElementById('kb-test-q').value.trim() });
    btn.disabled = false;
    if (!res || res.error) { out.innerText = 'The test did not run.'; return; }
    out.innerText = (res.handoff ? 'Would hand off to a person.\n' : 'Would reply:\n') + (res.reply || '');
}

async function loadTemplates() {
    if (!getActiveAccountId()) return;
    const data = await apiGet('/api/whatsapp/templates');
    const list = document.getElementById('tpl-list');
    if (!data || !data.templates) { list.innerHTML = emptyStateHtml('Could not load templates', 'Try again in a moment.'); return; }
    list.innerHTML = data.templates.length ? data.templates.map(t => {
        const st = String(t.status || '').toLowerCase();
        const colour = st === 'approved' ? 'text-emerald-300' : st === 'rejected' ? 'text-red-300' : 'text-amber-300';
        return `<article class="${cardClass}">
            <h3 class="text-sm font-semibold text-white font-mono break-all">${escapeHtml(t.name)}</h3>
            <div class="text-[11px] text-slate-400"><span class="font-semibold ${colour}">${escapeHtml(st || 'unknown')}</span> · ${escapeHtml([t.language, t.category].filter(Boolean).join(' · '))}</div>
            ${t.body ? `<p class="text-xs text-slate-300 mt-2 whitespace-pre-wrap break-words">${escapeHtml(t.body)}</p>` : ''}
        </article>`;
    }).join('') : emptyStateHtml('No templates yet', 'Press "Sync from Meta" after creating templates in WhatsApp Manager.');
}

async function syncTemplates(btn) {
    btn.disabled = true;
    const res = await apiPost('/api/whatsapp/templates/sync', {});
    btn.disabled = false;
    if (res && res.ok) { showToast(`${Number(res.count)} templates synced.`, 'success'); loadTemplates(); }
}

function updateAlertsVisibility(tab) {
    const panel = document.getElementById('alerts-panel');
    if (panel) panel.classList.toggle('hidden', tab !== 'repos' || !getActiveAccountId());
    const admin = document.getElementById('admin-alert-counts');
    if (admin && tab !== 'repos') admin.classList.add('hidden');
}

async function loadAlerts() {
    loadAdminAlertCounts();
    const onHome = !document.getElementById('tab-repos').classList.contains('hidden');
    updateAlertsVisibility(onHome ? 'repos' : '');
    const acct = getActiveAccountId();
    if (!acct) return;
    const data = await apiCall('GET', '/api/alerts', undefined, { quiet: true });
    if (acct !== getActiveAccountId()) return;
    const list = document.getElementById('alerts-list');
    const badge = document.getElementById('alerts-count');
    if (!data || !data.alerts) { badge.classList.add('hidden'); list.innerHTML = '<p class="text-xs text-amber-300">Alerts could not be loaded, so problems may be hidden.</p>'; return; }
    const open = data.alerts.filter(a => !a.resolved_at);
    const problems = open.filter(a => a.severity !== 'info').length;
    badge.innerText = problems;
    badge.classList.toggle('hidden', !problems);
    list.innerHTML = open.length ? '<ul class="space-y-2">' + open.map(a => {
        // Only same-app links: '#...' or '/...'.
        const link = /^(#|\/(?!\/))/.test(a.link || '') ? `<a class="btn-secondary text-xs" href="${escapeHtml(a.link)}">Open</a>` : '';
        const post = /^blog:(\d+)$/.exec(a.link || '');
        const target = /^(conversation|project):(\d+)$/.exec(a.link || '');
        const btn = (call, text) => `<button type="button" class="btn-secondary text-xs" onclick="${call}">${text}</button>`;
        const opener = post ? btn(`openPlanFromAlert(${Number(post[1])})`, 'Open post')
            : target ? btn(`open${target[1] === 'project' ? 'Project' : 'Chat'}FromAlert(${Number(target[2])})`, target[1] === 'project' ? 'Open project' : 'Open chat')
            : a.link === 'messages' ? btn("switchTab('wa-inbox')", 'Open inbox') : link;
        return `<li class="flex flex-wrap justify-between items-center gap-2 border-t border-slate-800 pt-2">
            <div class="min-w-0 flex-1"><div class="text-xs ${a.severity === 'info' ? 'text-slate-300' : a.severity === 'warning' ? 'text-amber-300' : 'text-red-300'} break-words">${escapeHtml(a.message)}${a.count > 1 ? ` (${Number(a.count)} times)` : ''}</div>
            <div class="text-[10px] text-slate-500">${escapeHtml([String(a.type || '').replace(/_/g, ' '), fmtWhen(a.last_seen || a.first_seen)].filter(Boolean).join(' · '))}</div></div>
            ${opener}${a.id && a.severity !== 'info' && can('crm.write') ? `<button type="button" class="btn-secondary text-xs" onclick="resolveAlert(${Number(a.id)})">Resolve</button>` : ''}
        </li>`;
    }).join('') + '</ul>' : '<p class="text-xs text-slate-400">No problems.</p>';
}
setInterval(() => { if (typeof currentUser !== 'undefined' && currentUser && !document.hidden) loadAlerts(); }, 30000);

async function openChatFromAlert(id) {
    switchTab('wa-inbox');
    await loadWhatsAppInbox();
    await selectConversation(id, true);
    const input = document.getElementById('wa-message-input');
    if (input && !input.disabled) input.focus();
}

async function openProjectFromAlert(id) {
    switchTab('repos');
    await loadProjects();
    const card = document.getElementById(`project-card-${id}`);
    if (!card) { showToast('That project no longer exists.', 'error'); return; }
    card.scrollIntoView({ block: 'center' });
    card.focus();
}

async function resolveAlert(id) {
    const res = await apiPost(`/api/alerts/${id}/resolve`, {});
    if (res && !res.error) loadAlerts();
}

async function loadAdminAlertCounts() {
    const box = document.getElementById('admin-alert-counts');
    if (!box) return;
    const home = () => !document.getElementById('tab-repos').classList.contains('hidden');
    if (!isPlatformAdmin() || !home()) { box.classList.add('hidden'); return; }
    const data = await apiCall('GET', '/api/admin/alert-counts', undefined, { quiet: true });
    const counts = (data && data.counts) || {};
    const rows = (window.__accounts || []).filter(a => counts[a.id]);
    box.classList.toggle('hidden', !rows.length || !home());
    box.querySelector('ul').innerHTML = rows.map(a => `<li><button type="button" class="btn-secondary text-xs" data-account="${escapeHtml(String(a.id))}">${escapeHtml(a.name)}: ${Number(counts[a.id])}</button></li>`).join('');
    box.querySelectorAll('button').forEach(b => b.onclick = () => {
        document.getElementById('client-select-filter').value = b.dataset.account;
        onClientFilterChange().then(loadAlerts);
    });
}

function reloadPhase1() {
    contactFields = []; cfAccount = null;
    planItems = []; closePlanForm(); document.getElementById('plan-list').innerHTML = '';
    if (!document.getElementById('tab-blog-plan').classList.contains('hidden')) loadPlan();
    approvedTemplates = [];
    fillKnowledge({});
    document.getElementById('kb-test-result').innerText = '';
    document.getElementById('tpl-list').innerHTML = '';
    document.getElementById('alerts-list').innerHTML = '';
    renderNeedsHuman({});
    loadAlerts();
    if (!document.getElementById('tab-wa-knowledge').classList.contains('hidden')) loadKnowledge();
    if (!document.getElementById('tab-wa-templates').classList.contains('hidden')) loadTemplates();
    document.getElementById('entry-list').innerHTML = '';
    document.getElementById('entry-counts').innerHTML = '';
    if (!document.getElementById('tab-wa-entry').classList.contains('hidden')) loadEntryLinks();
}

// Approved templates: used by broadcasts, blog alerts, and chats outside the 24-hour window.
let approvedTemplates = [];
async function fillTemplatePicker(prefix) {
    const sel = document.getElementById(`${prefix}-tpl`);
    const data = await apiGet('/api/whatsapp/templates');
    approvedTemplates = ((data && data.templates) || []).filter(t => String(t.status).toUpperCase() === 'APPROVED');
    const prev = sel.value;
    sel.innerHTML = '';
    sel.add(new Option(approvedTemplates.length ? 'Choose a template' : 'No approved templates. Sync them under Message Templates.', ''));
    approvedTemplates.forEach((t, i) => sel.add(new Option(`${t.name} (${t.language})`, `${t.name}|${t.language}`)));
    if ([...sel.options].some(o => o.value === prev)) sel.value = prev;
    showTemplateFields(prefix);
}
function pickedTemplate(prefix) {
    const [name, language] = document.getElementById(`${prefix}-tpl`).value.split('|');
    return approvedTemplates.find(t => t.name === name && t.language === language);
}
async function ensureTemplates() {
    if (approvedTemplates.length) return;
    const data = await apiCall('GET', '/api/whatsapp/templates', undefined, { quiet: true });
    approvedTemplates = ((data && data.templates) || []).filter(t => String(t.status).toUpperCase() === 'APPROVED');
}
function showTemplateFields(prefix) {
    if (prefix === 'bc') updateBroadcastAudience();
    const t = pickedTemplate(prefix);
    const box = document.getElementById(`${prefix}-tpl-vars`);
    box.innerHTML = '';
    for (let i = 1; t && i <= t.variables; i++) {
        const input = document.createElement('input');
        input.className = 'input-text text-xs w-full';
        input.placeholder = `Value for {{${i}}}` + (prefix === 'chat' ? '' : ' (you can use {{name}})');
        input.setAttribute('aria-label', `Value for variable ${i}`);
        input.oninput = () => previewTemplate(prefix);
        box.appendChild(input);
    }
    previewTemplate(prefix);
}
function previewTemplate(prefix) {
    const t = pickedTemplate(prefix);
    const values = [...document.querySelectorAll(`#${prefix}-tpl-vars input`)].map(i => i.value);
    document.getElementById(`${prefix}-tpl-preview`).innerText = t ? String(t.body || '').replace(/\{\{(\d+)\}\}/g, (m, n) => values[n - 1] || m) : '';
}
function templateChoice(prefix) {
    const t = pickedTemplate(prefix);
    if (!t) { showToast('Choose an approved template.', 'error'); return null; }
    const params = [...document.querySelectorAll(`#${prefix}-tpl-vars input`)].map(i => i.value.trim());
    if (params.some(v => !v)) { showToast('Fill in every template value.', 'error'); return null; }
    return { template_name: t.name, template_language: t.language, template_params: params };
}
function updateAutomationFields() {
    const blog = document.getElementById('new-auto-trigger').value === 'blog_publish';
    document.getElementById('au-tpl-wrap').classList.toggle('hidden', !blog);
    document.getElementById('au-text-wrap').classList.toggle('hidden', blog);
    document.getElementById('new-auto-template').required = !blog;
    if (blog) fillTemplatePicker('au');
}
function broadcastResult(st) {
    if (st.success === false) return st.error || 'The broadcast was not sent.';
    return `Queued for ${Number(st.queued_count || 0)}, skipped ${Number(st.skipped_count || 0)}.`;
}

let windowConversationId = null;
function renderWindow(conv) {
    const box = document.getElementById('wa-window-closed');
    const note = document.getElementById('wa-window-note');
    const closed = !!conv.id && conv.window_open === false;
    note.innerText = conv.id && conv.window_open && conv.window_expires_at ? `Free-text replies open until ${fmtWhen(conv.window_expires_at)}.` : '';
    box.classList.toggle('hidden', !closed || !can('crm.write'));
    const input = document.getElementById('wa-message-input');
    input.disabled = closed;
    if (closed && windowConversationId !== conv.id) fillTemplatePicker('chat');
    windowConversationId = closed ? conv.id : null;
}
async function sendChatTemplate(e) {
    e.preventDefault();
    const id = activeConversationId;
    const c = templateChoice('chat');
    if (!id || !c) return;
    const res = await apiPost(`/api/whatsapp/conversations/${id}/template`, { name: c.template_name, language: c.template_language, params: c.template_params });
    if (res && res.success) { showToast('Template sent.', 'success'); loadConversationMessages(id); }
}

// Entry links (E-3): wa.me click-to-chat links; the code in the prefilled text records the lead source.
let entryLinks = [];
async function loadEntryLinks() {
    const acct = getActiveAccountId();
    if (!acct) return;
    const data = await apiGet('/api/entry-links');
    if (acct !== getActiveAccountId()) return;
    const list = document.getElementById('entry-list');
    if (!data || !data.links) { list.innerHTML = emptyStateHtml('Could not load entry links', 'Try again in a moment.'); return; }
    entryLinks = data.links;
    const counts = Object.entries(data.enquiries_by_source || {});
    document.getElementById('entry-counts').innerHTML = counts.length
        ? counts.map(([k, n]) => `<span class="text-xs px-2 py-1 rounded-full border border-slate-700 text-slate-200">${escapeHtml(LEAD_SOURCES[k] || k)}: <strong>${Number(n)}</strong></span>`).join('')
        : '<p class="text-xs text-slate-400">No enquiries recorded yet.</p>';
    list.innerHTML = entryLinks.length ? entryLinks.map(l => `<article class="${cardClass}">
        <h3 class="text-sm font-semibold text-white break-words">${escapeHtml(l.label)}</h3>
        <div class="text-[11px] text-slate-400">${l.source ? escapeHtml(l.source) + ' · ' : ''}Code ${escapeHtml(l.code)}${l.campaign ? ' · Campaign ' + escapeHtml(l.campaign) : ''}</div>
        <p class="text-xs text-slate-300 mt-2 break-words">${escapeHtml(l.prefill)}</p>
        ${l.url ? `<p class="text-xs font-mono text-indigo-300 mt-2 break-all">${escapeHtml(l.url)}</p>` : '<p class="text-xs text-amber-300 mt-2">Add the business phone number under WhatsApp API Setup to get the link.</p>'}
        <div class="flex flex-wrap gap-2 mt-3">
            ${l.url ? `<button type="button" class="btn-secondary text-xs" onclick="copyEntry(${Number(l.id)}, false)">Copy link</button>
            <button type="button" class="btn-secondary text-xs" onclick="copyEntry(${Number(l.id)}, true)">Copy website button</button>
            <button type="button" class="btn-secondary text-xs" aria-expanded="false" onclick="toggleQr(${Number(l.id)}, this)">QR code</button>` : ''}
            ${can('automations.manage') ? `<button type="button" class="btn-secondary text-xs text-red-300" onclick="deleteEntryLink(${Number(l.id)})">Delete</button>` : ''}
        </div>
        <div id="qr-${Number(l.id)}" class="hidden mt-3"></div>
    </article>`).join('') : emptyStateHtml('No entry links yet', 'Create one for your website button and one for each ad.');
}
async function copyEntry(id, asButton) {
    const l = entryLinks.find(x => x.id === id);
    if (!l) return;
    const text = asButton ? `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">Chat with us on WhatsApp</a>` : l.url;
    try { await navigator.clipboard.writeText(text); showToast('Copied.', 'success'); }
    catch (e) { prompt('Copy this text:', text); }
}
async function saveEntryLink(e) {
    e.preventDefault();
    const val = i => document.getElementById(i).value.trim();
    const form = e.target;
    const res = await apiPost('/api/entry-links', { source: val('entry-source'), label: val('entry-label'), code: val('entry-code'), campaign: val('entry-campaign'), message: val('entry-message') });
    if (res && res.success) { showToast('Entry link created.', 'success'); form.reset(); loadEntryLinks(); }
}
async function deleteEntryLink(id) {
    if (!confirm('Delete this link? Links already shared still open WhatsApp, but their enquiries are no longer labelled.')) return;
    const res = await apiDelete(`/api/entry-links/${id}`);
    if (res && res.success) loadEntryLinks();
}

// Blog schedule (BS-6). The server enforces every status change; buttons only reflect it.
const PLAN_STATUS = { draft: ['Draft', 'text-slate-300'], needs_approval: ['Needs approval', 'text-amber-300'], approved: ['Approved', 'text-emerald-300'], published: ['Published', 'text-cyan-300'], failed: ['Failed', 'text-red-300'] };
let planItems = [], planProjects = [], planView = 'list', planEditing = null, planMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);

async function loadPlan() {
    const acct = getActiveAccountId();
    const list = document.getElementById('plan-list');
    if (!acct) { list.innerHTML = emptyStateHtml('Choose an account', 'The schedule belongs to one account.'); return; }
    const [data, projects] = await Promise.all([apiGet('/api/blog/plan'), apiGet('/api/projects')]);
    if (acct !== getActiveAccountId()) return;
    planProjects = (projects && projects.projects) || [];
    const items = data && (data.items || data.plan || data.posts);
    if (!items) { list.innerHTML = emptyStateHtml('Could not load the schedule', 'Try again in a moment.'); return; }
    planItems = items;
    const filter = document.getElementById('plan-filter-assignee');
    const prev = filter.value;
    const people = new Map(planItems.filter(i => i.assignee_id).map(i => [String(i.assignee_id), i.assignee_name || `User ${i.assignee_id}`]));
    filter.innerHTML = '';
    filter.add(new Option('Anyone', ''));
    people.forEach((name, id) => filter.add(new Option(name, id)));
    if ([...filter.options].some(o => o.value === prev)) filter.value = prev;
    renderPlan();
}
function setPlanView(view) {
    planView = view;
    ['list', 'month'].forEach(v => document.getElementById(`plan-view-${v}`).setAttribute('aria-pressed', String(v === view)));
    renderPlan();
}
function shiftPlanMonth(n) { planMonth = new Date(planMonth.getFullYear(), planMonth.getMonth() + n, 1); renderPlan(); }
function planButton(i, compact) {
    const [label, colour] = PLAN_STATUS[i.status] || [i.status, 'text-slate-300'];
    if (compact) return `<button type="button" class="block w-full text-left text-[11px] truncate ${colour}" title="${escapeHtml(i.title)} (${escapeHtml(label)})" onclick="editPlan(${Number(i.id)})">${escapeHtml(i.title)}</button>`;
    return `<article class="${cardClass}">
        <div class="flex flex-wrap justify-between items-start gap-2">
            <div class="min-w-0 flex-1">
                <h3 class="text-sm font-semibold text-white break-words">${escapeHtml(i.title)}</h3>
                <div class="text-[11px] text-slate-400">${escapeHtml([fmtWhen(i.publish_at) || 'No date yet', i.keyword, i.assignee_name].filter(Boolean).join(' · '))}</div>
                <div class="text-xs font-semibold ${colour}">${escapeHtml(label)}${i.error ? ': ' + escapeHtml(i.error) : ''}</div>
                ${/^https?:\/\//.test(i.post_url || '') ? `<a class="text-xs text-indigo-300 underline break-all" href="${escapeHtml(i.post_url)}" target="_blank" rel="noopener">View published post</a>` : ''}
            </div>
            <button type="button" class="btn-secondary text-xs" onclick="editPlan(${Number(i.id)})">Open</button>
        </div></article>`;
}
function renderPlan() {
    const status = document.getElementById('plan-filter-status').value;
    const who = document.getElementById('plan-filter-assignee').value;
    const items = planItems.filter(i => (!status || i.status === status) && (!who || String(i.assignee_id) === who))
        .sort((a, b) => String(a.publish_at).localeCompare(String(b.publish_at)));
    const list = document.getElementById('plan-list');
    document.getElementById('plan-month-nav').classList.toggle('hidden', planView !== 'month');
    if (planView === 'list') {
        list.className = 'space-y-2';
        list.innerHTML = items.length ? items.map(i => planButton(i)).join('') : emptyStateHtml('No planned posts', 'Plan a post, write or draft it, then get it approved.');
        return;
    }
    document.getElementById('plan-month-title').innerText = planMonth.toLocaleDateString([], { month: 'long', year: 'numeric' });
    const days = new Date(planMonth.getFullYear(), planMonth.getMonth() + 1, 0).getDate();
    const lead = (planMonth.getDay() + 6) % 7;
    let cells = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => `<div class="text-[10px] text-slate-500 text-center">${d}</div>`).join('') + '<div></div>'.repeat(lead);
    for (let d = 1; d <= days; d++) {
        const day = new Date(planMonth.getFullYear(), planMonth.getMonth(), d).toDateString();
        cells += `<div class="border border-slate-800 rounded p-1 min-h-[3.5rem] min-w-0"><div class="text-[10px] text-slate-400">${d}</div>${items.filter(i => i.publish_at && new Date(i.publish_at).toDateString() === day).map(i => planButton(i, true)).join('')}</div>`;
    }
    list.className = 'grid grid-cols-7 gap-1';
    list.innerHTML = cells;
}
function localInput(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function previewPlan() { document.getElementById('plan-preview').innerText = document.getElementById('plan-body').value || 'Nothing written yet.'; }
async function editPlan(id) {
    let item = id ? planItems.find(x => x.id === id) : null;
    if (id && !item) return;
    planEditing = item;
    const form = document.getElementById('plan-form');
    form.reset();
    const projects = document.getElementById('plan-project');
    projects.innerHTML = '';
    projects.add(new Option(planProjects.length ? 'Choose a project' : 'No blog project yet. Connect one first.', ''));
    planProjects.forEach(p => projects.add(new Option(p.name || p.repo_name || `Project ${p.id}`, String(p.id))));
    const people = document.getElementById('plan-assignee');
    people.innerHTML = '';
    people.add(new Option('Nobody', ''));
    if (currentUser) people.add(new Option('Me', String(currentUser.id)));
    if (can('users.manage')) {
        const d = await apiGet(`/api/accounts/${encodeURIComponent(getActiveAccountId())}/users`);
        ((d && d.users) || []).filter(u => u.user_id !== currentUser.id).forEach(u => people.add(new Option(u.username, String(u.user_id))));
    }
    if (item) {
        if (item.assignee_id && ![...people.options].some(o => o.value === String(item.assignee_id))) people.add(new Option(item.assignee_name || 'Teammate', String(item.assignee_id)));
        const set = (k, v) => { document.getElementById(k).value = v == null ? '' : v; };
        set('plan-title', item.title); set('plan-topic', item.topic); set('plan-keyword', item.keyword);
        set('plan-when', localInput(item.publish_at)); set('plan-project', item.project_id); set('plan-assignee', item.assignee_id); set('plan-body', item.body);
    }
    const st = item ? item.status : null;
    const published = st === 'published';
    const write = can('content.write') && !published;
    document.getElementById('plan-form-h').innerText = item ? 'Planned post' : 'Plan a post';
    document.getElementById('plan-form-note').innerText = st === 'approved' ? 'Approved. Saving a change sends it back for approval.' : published ? 'Published. It can no longer be edited.' : '';
    document.getElementById('plan-fields').disabled = !write;
    const show = (k, on) => document.getElementById(k).classList.toggle('hidden', !on);
    show('plan-save', write);
    show('plan-draft', write && !!item);
    show('plan-submit', write && !!item && (st === 'draft' || st === 'failed'));
    show('plan-approve', !!item && st === 'needs_approval' && can('content.publish'));
    show('plan-delete', write && !!item);
    previewPlan();
    form.classList.remove('hidden');
    form.scrollIntoView({ block: 'nearest' });
    (write ? document.getElementById('plan-title') : form.querySelector('button:not(.hidden)')).focus();
}
function closePlanForm() { planEditing = null; document.getElementById('plan-form').classList.add('hidden'); }
function planBody() {
    const val = k => document.getElementById(k).value.trim();
    return { title: val('plan-title'), topic: val('plan-topic'), keyword: val('plan-keyword'), publish_at: new Date(val('plan-when')).toISOString(),
             project_id: Number(val('plan-project')) || val('plan-project'), assignee_id: val('plan-assignee') ? Number(val('plan-assignee')) : null, body: document.getElementById('plan-body').value };
}
function planDirty() {
    if (!planEditing) return false;
    const b = planBody();
    return ['title', 'topic', 'keyword', 'body'].some(k => (planEditing[k] || '') !== b[k]) || localInput(planEditing.publish_at) !== document.getElementById('plan-when').value
        || String(planEditing.project_id || '') !== String(b.project_id || '') || String(planEditing.assignee_id || '') !== String(b.assignee_id || '');
}
async function savePlan(e) {
    e.preventDefault();
    const res = planEditing ? await apiCall('PATCH', `/api/blog/plan/${planEditing.id}`, planBody()) : await apiPost('/api/blog/plan', planBody());
    if (res && !res.error) { showToast('Saved.', 'success'); closePlanForm(); loadPlan(); }
}
async function planAction(action) {
    const item = planEditing;
    if (!item) return;
    // Never submit or approve text other than what is on screen.
    if (planDirty()) { showToast('Save your changes first.', 'error'); return; }
    if (action === 'draft' && item.body && !confirm('Replace the article text with a new AI draft?')) return;
    const btn = document.getElementById(`plan-${action}`);
    btn.disabled = true;
    const res = await apiPost(`/api/blog/plan/${item.id}/${action}`, {});
    btn.disabled = false;
    if (!res || res.error) return;
    if (res.item && res.item.error) showToast(res.item.error, 'error');
    else showToast({ draft: 'Draft ready. Read it before submitting.', submit: 'Sent for approval.', approve: 'Approved. It will publish on its date.' }[action], 'success');
    await loadPlan();
    if (planEditing && planEditing.id === item.id) editPlan(item.id);
}
async function deletePlan() {
    if (!planEditing || !confirm('Delete this planned post?')) return;
    const res = await apiDelete(`/api/blog/plan/${planEditing.id}`);
    if (res && !res.error) { closePlanForm(); loadPlan(); }
}

// QR code for an entry link, drawn in the browser by the vendored qrcode-generator (static/js/qrcode.js).
function toggleQr(id, btn) {
    const l = entryLinks.find(x => x.id === id);
    const box = document.getElementById(`qr-${id}`);
    const open = box.classList.toggle('hidden') === false;
    btn.setAttribute('aria-expanded', String(open));
    if (!open || !l || box.firstChild) return;
    qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8'];
    const qr = qrcode(0, 'M');
    qr.addData(l.url);
    qr.make();
    const cell = 8, margin = 4, n = qr.getModuleCount();
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = (n + margin * 2) * cell;
    const g = canvas.getContext('2d');
    g.fillStyle = '#fff'; g.fillRect(0, 0, canvas.width, canvas.height);
    g.fillStyle = '#000';
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) g.fillRect((c + margin) * cell, (r + margin) * cell, cell, cell);
    const img = new Image();
    img.src = canvas.toDataURL('image/png');
    img.alt = `QR code that opens WhatsApp: ${l.label}`;
    img.className = 'w-48 h-48';
    const a = document.createElement('a');
    a.href = img.src; a.download = `whatsapp-${l.code}.png`;
    a.className = 'btn-secondary text-xs inline-block mt-2';
    a.innerText = 'Download PNG';
    box.append(img, a);
}

// Custom contact fields (CF-4)
let contactFields = [], cfAccount = null, shownContacts = [], editingContactId = null;
async function loadContactFields(force = false) {
    const acct = getActiveAccountId();
    if (!acct || (!force && cfAccount === acct)) return;
    const data = await apiCall('GET', '/api/contact-fields', undefined, { quiet: true });
    if (acct !== getActiveAccountId()) return;
    contactFields = ((data && data.fields) || []).filter(f => !f.archived);
    cfAccount = data && data.fields ? acct : null;
    document.getElementById('cf-list').innerHTML = contactFields.length ? contactFields.map(f => `<div class="flex flex-wrap justify-between items-center gap-2 text-xs text-slate-300 border-t border-slate-800 pt-2">
        <span class="break-words min-w-0">${escapeHtml(f.name)} <span class="text-slate-500">(${escapeHtml(f.type)}${f.options && f.options.length ? ': ' + escapeHtml(f.options.join(', ')) : ''})</span></span>
        <button type="button" class="btn-secondary text-xs text-red-300" onclick="deleteContactField(${Number(f.id)})">Remove</button></div>`).join('') : '<p class="text-xs text-slate-400">No custom fields yet.</p>';
    renderContactFilters();
}
function fieldControl(f, id, value) {
    let el;
    if (f.type === 'select') {
        el = document.createElement('select');
        el.add(new Option('-', ''));
        (f.options || []).forEach(o => el.add(new Option(o, o)));
        el.className = 'input-select text-sm w-full';
    } else {
        el = document.createElement('input');
        el.type = f.type === 'number' || f.type === 'date' ? f.type : 'text';
        if (f.type === 'number') el.step = 'any';
        el.className = 'input-text text-sm w-full';
    }
    el.id = id;
    el.value = value == null ? '' : value;
    return el;
}
function labelled(text, el) {
    const wrap = document.createElement('div');
    const label = document.createElement('label');
    label.htmlFor = el.id; label.innerText = text; label.className = 'block text-xs text-slate-400 mb-1';
    wrap.append(label, el);
    return wrap;
}
function renderCustomInputs(boxId, values) {
    const box = document.getElementById(boxId);
    box.innerHTML = '';
    contactFields.forEach(f => {
        const el = fieldControl(f, `${boxId}-${f.id}`, values[f.id]);
        el.dataset.field = f.id;
        box.appendChild(labelled(f.name, el));
    });
}
function readCustom(boxId, skipEmpty) {
    const out = {};
    document.querySelectorAll(`#${boxId} [data-field]`).forEach(el => { if (!skipEmpty || el.value !== '') out[el.dataset.field] = el.value; });
    return out;
}
function renderContactFilters() {
    const bar = document.getElementById('cf-filters');
    bar.innerHTML = '';
    bar.classList.toggle('hidden', !contactFields.length);
    contactFields.forEach(f => {
        const ranged = f.type === 'number' || f.type === 'date';
        (ranged ? [['_min', ' from'], ['_max', ' to']] : [['', '']]).forEach(([suffix, word]) => {
            const el = fieldControl(f, `cf-q-${f.id}${suffix}`, '');
            el.dataset.query = `cf_${f.id}${suffix}`;
            el.onchange = () => loadWhatsAppContacts();
            const w = labelled(f.name + word, el);
            w.className = 'w-36';
            bar.appendChild(w);
        });
    });
}
function contactFieldQuery() {
    return [...document.querySelectorAll('#cf-filters [data-query]')].filter(el => el.value !== '')
        .map(el => `&${el.dataset.query}=${encodeURIComponent(el.value)}`).join('');
}
function customSummaryHtml(c) {
    return contactFields.filter(f => c.custom && c.custom[f.id] != null && c.custom[f.id] !== '')
        .map(f => `<div class="text-[11px] text-slate-300 truncate">${escapeHtml(f.name)}: ${escapeHtml(String(c.custom[f.id]))}</div>`).join('');
}
function openContactFields(id) {
    const c = shownContacts.find(x => x.id === id);
    if (!c) return;
    editingContactId = id;
    document.getElementById('modal-contact-fields-h').innerText = `Fields: ${c.name}`;
    renderCustomInputs('edit-contact-custom', c.custom || {});
    document.getElementById('modal-contact-fields').classList.remove('hidden');
}
async function saveContactValues(e) {
    e.preventDefault();
    const res = await apiPut(`/api/whatsapp/contacts/${editingContactId}`, { custom: readCustom('edit-contact-custom', false) });
    if (res && res.success) { showToast('Saved.', 'success'); document.getElementById('modal-contact-fields').classList.add('hidden'); loadWhatsAppContacts(); }
}
async function saveContactField(e) {
    e.preventDefault();
    const form = e.target;
    const type = document.getElementById('cf-type').value;
    const options = type === 'select' ? document.getElementById('cf-options').value.split(',').map(x => x.trim()).filter(Boolean) : [];
    if (type === 'select' && !options.length) { showToast('Add at least one choice.', 'error'); return; }
    const res = await apiPost('/api/contact-fields', { name: document.getElementById('cf-name').value.trim(), type, options });
    if (res && !res.error) { form.reset(); document.getElementById('cf-options-wrap').classList.add('hidden'); await loadContactFields(true); loadWhatsAppContacts(); }
}
async function deleteContactField(id) {
    if (!confirm('Remove this field? It is hidden everywhere; saved values are kept.')) return;
    const res = await apiDelete(`/api/contact-fields/${id}`);
    if (res && !res.error) { await loadContactFields(true); loadWhatsAppContacts(); }
}

async function openPlanFromAlert(id) {
    switchTab('blog-plan');
    await loadPlan();
    editPlan(id);
}

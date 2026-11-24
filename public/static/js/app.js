// GitPulse CMS - Frontend Application Controller

let globalPresets = {};
let currentUser = null;
let currentStagingPost = null;
let generated2FASecret = "";

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    // 1. Verify user session
    const authData = await apiGet('/api/auth/me');
    if (!authData || !authData.user) {
        window.location.href = '/login';
        return;
    }
    currentUser = authData.user;
    const userEl = document.getElementById('header-username');
    if (userEl) userEl.innerText = currentUser.username;

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

    // 2. Load Dashboard Components
    await fetchPresets();
    await loadClients();
    await loadStatus();
    await loadProjects();
    await loadStagingPosts();
    await loadPosts();
    await loadWhatsAppInbox();
    await loadWhatsAppContacts();
    await loadWhatsAppDeals();
    await loadWhatsAppBroadcasts();
    await loadWhatsAppAutomations();
    await loadWhatsAppConfig();
    await loadLogs();
    await loadSettings();
    await loadSupabaseStatus();

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
function switchTab(tabName) {
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
        'wa-inbox': { title: 'Shared Team Inbox', sub: 'Two-way live WhatsApp messaging with delivery status ticks and quick replies' },
        'wa-contacts': { title: 'Contacts & Audience CRM', sub: 'Manage customer profiles, lead tags, and WhatsApp communication history' },
        'wa-deals': { title: 'Sales Pipeline (Kanban)', sub: 'Track and advance deals across qualification, proposals, and closed won' },
        'wa-broadcasts': { title: 'Broadcast Campaigns', sub: 'Mass WhatsApp messaging campaigns segmented by audience tags' },
        'wa-automations': { title: 'No-Code Automations Engine', sub: 'Automated welcome bots, keyword responders, and blog publication alerts' },
        'wa-config': { title: 'WhatsApp API & Webhook Setup', sub: 'Official Meta Cloud API credentials, webhook verification, and simulator' },
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
    if (tabName === 'supabase') loadSupabaseStatus();
    if (tabName === 'logs') loadLogs();
    if (tabName === 'settings') loadSettings();
}

// --- Authentication & Session Actions ---
async function handleLogout() {
    if (!confirm('Are you sure you want to sign out?')) return;
    try {
        await apiPost('/api/auth/logout', {});
    } finally {
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
async function apiGet(endpoint) {
    try {
        const res = await fetch(endpoint);
        if (res.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return await res.json();
    } catch (err) {
        showToast(`Network error: ${err.message}`, 'error');
        return null;
    }
}

async function apiPost(endpoint, data = {}) {
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (res.status === 401 && endpoint !== '/api/auth/login') {
            window.location.href = '/login';
            return null;
        }
        return await res.json();
    } catch (err) {
        showToast(`Request failed: ${err.message}`, 'error');
        return null;
    }
}

async function apiPut(endpoint, data = {}) {
    try {
        const res = await fetch(endpoint, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (res.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return await res.json();
    } catch (err) {
        showToast(`Request failed: ${err.message}`, 'error');
        return null;
    }
}

async function apiDelete(endpoint) {
    try {
        const res = await fetch(endpoint, { method: 'DELETE' });
        if (res.status === 401) {
            window.location.href = '/login';
            return null;
        }
        return await res.json();
    } catch (err) {
        showToast(`Delete failed: ${err.message}`, 'error');
        return null;
    }
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
        const cidParam = clientFilter ? `?client_id=${clientFilter}` : '';

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
            const totalVal = dealData.deals.reduce((sum, d) => sum + (parseFloat(d.value) || 0), 0);
            const el = document.getElementById('stat-pipeline-value');
            if (el) el.innerText = `$${totalVal.toLocaleString()}`;
            const badge = document.getElementById('sidebar-badge-deals');
            if (badge) badge.innerText = `$${Math.round(totalVal/1000)}k`;
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
    const url = clientFilter ? `/api/projects?client_id=${clientFilter}` : '/api/projects';
    const data = await apiGet(url);
    if (!data || !data.projects) return;

    const grid = document.getElementById('projects-grid');
    grid.innerHTML = '';

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
                        ⏰ ${p.publish_time} UTC
                    </span>
                </div>
                <h3 class="font-bold text-white text-base">${escapeHtml(p.name)}</h3>
                <a href="https://github.com/${escapeHtml(p.github_repo)}" target="_blank" class="text-xs text-cyan-400 hover:underline flex items-center gap-1 mt-0.5">
                    github.com/${escapeHtml(p.github_repo)} ↗
                </a>
                <p class="text-xs text-slate-400 mt-2 line-clamp-2"><strong>Niche:</strong> ${escapeHtml(p.topic)}</p>
                
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
    });
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
    const data = await apiGet('/api/clients');
    if (!data || !data.clients) return;

    // Header client filter
    const headerFilter = document.getElementById('client-select-filter');
    if (headerFilter) {
        const curVal = headerFilter.value;
        headerFilter.innerHTML = '<option value="">All Clients</option>';
        data.clients.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.innerText = c.name;
            headerFilter.appendChild(opt);
        });
        headerFilter.value = curVal;
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

function onClientFilterChange() {
    loadProjects();
}

function openAddClientModal() {
    document.getElementById('modal-add-client').classList.remove('hidden');
}

function closeAddClientModal() {
    document.getElementById('modal-add-client').classList.add('hidden');
}

async function submitAddClient(e) {
    e.preventDefault();
    const name = document.getElementById('new-client-name').value;
    const email = document.getElementById('new-client-email').value;

    const res = await apiPost('/api/clients', { name, contact_email: email });
    if (res && res.id) {
        showToast('Client created successfully!', 'success');
        closeAddClientModal();
        document.getElementById('new-client-name').value = '';
        document.getElementById('new-client-email').value = '';
        await loadClients();
        const wizardClient = document.getElementById('wizard-client-id');
        if (wizardClient) wizardClient.value = res.id;
    } else {
        showToast(res ? res.error : 'Failed to create client', 'error');
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
        client_id: document.getElementById('wizard-client-id').value || null,
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
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ====================================================================
// WhatsApp Automation & CRM Engine (ArnasDon/wacrm Frontend Controller)
// ====================================================================

let activeConversationId = null;
let currentConversationsList = [];

// --- 1. Shared Team Inbox ---

async function loadWhatsAppInbox(selectConvId = null) {
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    const url = clientFilter ? `/api/whatsapp/conversations?client_id=${clientFilter}` : '/api/whatsapp/conversations';
    
    const data = await apiGet(url);
    if (!data || !data.conversations) return;
    
    currentConversationsList = data.conversations;
    const threadListEl = document.getElementById('wa-threads-list');
    if (!threadListEl) return;
    
    threadListEl.innerHTML = '';
    
    if (currentConversationsList.length === 0) {
        threadListEl.innerHTML = `
            <div class="p-6 text-center text-slate-500 text-xs">
                No active conversations yet.<br>Click "Test Inbound Message" or wait for incoming WhatsApp messages.
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
    apiPost(`/api/whatsapp/conversations/${convId}/read`, {});
    
    const conv = currentConversationsList.find(c => c.id === convId);
    if (conv) {
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
            if (msg.status === 'read') tick = '<span class="chat-status-tick text-cyan-300 font-bold" title="Read">✓✓</span>';
            else if (msg.status === 'delivered') tick = '<span class="chat-status-tick text-slate-300" title="Delivered">✓✓</span>';
            else tick = '<span class="chat-status-tick text-slate-400" title="Sent">✓</span>';
        }
        
        bubble.innerHTML = `
            <div>${escapeHtml(msg.body).replace(/\\n/g, '<br>')}</div>
            <div class="text-[9px] text-right mt-1 opacity-70 flex justify-end items-center">
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
    
    let url = `/api/whatsapp/contacts?search=${encodeURIComponent(search)}&tag=${encodeURIComponent(tag)}`;
    if (clientFilter) url += `&client_id=${clientFilter}`;
    
    const data = await apiGet(url);
    if (!data || !data.contacts) return;
    
    const tbody = document.getElementById('wa-contacts-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
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
            <td class="px-5 py-3 text-xs text-slate-400 max-w-xs truncate">
                ${escapeHtml(c.notes || '-')}
            </td>
            <td class="px-5 py-3 text-right">
                <div class="flex items-center justify-end gap-1.5">
                    <button onclick="startChatWithContact(${c.id})" class="btn-secondary text-[11px] py-1 px-2.5 flex items-center gap-1 text-emerald-400 hover:text-emerald-300">
                        <span>💬 Chat</span>
                    </button>
                    <button onclick="openAddDealModal(${c.id}, '${escapeHtml(c.name)}')" class="btn-secondary text-[11px] py-1 px-2.5 text-indigo-400 hover:text-indigo-300">
                        <span>+ Deal</span>
                    </button>
                    <button onclick="deleteContactFromUI(${c.id}, '${escapeHtml(c.name)}')" class="text-slate-500 hover:text-red-400 p-1">
                        🗑️
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function startChatWithContact(contactId) {
    const data = await apiGet('/api/whatsapp/conversations');
    if (!data || !data.conversations) return;
    const match = data.conversations.find(conv => conv.contact_id === contactId);
    switchTab('wa-inbox');
    if (match) {
        selectConversation(match.id, true);
    } else {
        loadWhatsAppInbox();
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
    const url = clientFilter ? `/api/whatsapp/deals?client_id=${clientFilter}` : '/api/whatsapp/deals';
    
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
        if (totalEl) totalEl.innerText = `$${subtotal.toLocaleString()}`;
        
        list.forEach(deal => {
            const card = document.createElement('div');
            card.className = "kanban-card";
            
            const stageIndex = stages.indexOf(stage);
            const prevStage = stageIndex > 0 ? stages[stageIndex - 1] : null;
            const nextStage = stageIndex < stages.length - 1 ? stages[stageIndex + 1] : null;
            
            const prevBtn = prevStage ? `<button onclick="updateDealStage(${deal.id}, '${prevStage}')" class="text-slate-500 hover:text-indigo-400 text-xs px-1" title="Move back to ${prevStage}">←</button>` : '';
            const nextBtn = nextStage ? `<button onclick="updateDealStage(${deal.id}, '${nextStage}')" class="text-slate-500 hover:text-emerald-400 text-xs px-1" title="Advance to ${nextStage}">→</button>` : '';
            
            card.innerHTML = `
                <div class="flex justify-between items-start mb-1.5">
                    <h4 class="font-semibold text-xs text-white leading-snug">${escapeHtml(deal.title)}</h4>
                    <button onclick="deleteDealFromUI(${deal.id})" class="text-slate-600 hover:text-red-400 text-xs ml-1">&times;</button>
                </div>
                <div class="text-[11px] text-slate-400 mb-2">${escapeHtml(deal.contact_name || 'Unassigned Contact')}</div>
                <div class="flex justify-between items-center pt-2 border-t border-slate-900 text-xs">
                    <span class="font-bold text-emerald-400">$${(parseFloat(deal.value) || 0).toLocaleString()}</span>
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
    const url = clientFilter ? `/api/whatsapp/broadcasts?client_id=${clientFilter}` : '/api/whatsapp/broadcasts';
    
    const data = await apiGet(url);
    if (!data || !data.broadcasts) return;
    
    const container = document.getElementById('wa-broadcasts-container');
    if (!container) return;
    container.innerHTML = '';
    
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
                <button onclick="runBroadcastFromUI(${b.id})" class="btn-primary text-xs py-1.5 px-3 flex items-center gap-1.5">
                    <span>⚡ Run Broadcast</span>
                </button>
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
        `;
        container.appendChild(card);
    });
}

async function runBroadcastFromUI(broadcastId) {
    showToast('Executing WhatsApp broadcast campaign...', 'info');
    const res = await apiPost(`/api/whatsapp/broadcasts/${broadcastId}/run`, {});
    if (res && res.success) {
        showToast(`Broadcast completed: ${res.stats.sent_count} messages sent!`, 'success');
        loadWhatsAppBroadcasts();
        loadStatus();
    } else {
        showToast('Broadcast execution failed', 'error');
    }
}

// --- 5. No-Code Automations Engine ---

async function loadWhatsAppAutomations() {
    const clientFilter = document.getElementById('client-select-filter') ? document.getElementById('client-select-filter').value : '';
    const url = clientFilter ? `/api/whatsapp/automations?client_id=${clientFilter}` : '/api/whatsapp/automations';
    
    const data = await apiGet(url);
    if (!data || !data.automations) return;
    
    const container = document.getElementById('wa-automations-container');
    if (!container) return;
    container.innerHTML = '';
    
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
                        <input type="checkbox" ${a.is_active ? 'checked' : ''} onchange="toggleAutomationRule(${a.id}, this.checked)">
                        <span class="slider"></span>
                    </label>
                    <button onclick="deleteAutomationRule(${a.id})" class="text-slate-600 hover:text-red-400 text-xs ml-1">🗑️</button>
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
    const url = clientFilter ? `/api/whatsapp/config?client_id=${clientFilter}` : '/api/whatsapp/config';
    
    const cfg = await apiGet(url);
    if (!cfg) return;
    
    if (document.getElementById('wa-cfg-phone-id')) document.getElementById('wa-cfg-phone-id').value = cfg.phone_number_id || '';
    if (document.getElementById('wa-cfg-waba-id')) document.getElementById('wa-cfg-waba-id').value = cfg.waba_id || '';
    if (document.getElementById('wa-cfg-token')) document.getElementById('wa-cfg-token').value = cfg.access_token || '';
    if (document.getElementById('wa-cfg-verify-token')) document.getElementById('wa-cfg-verify-token').value = cfg.verify_token || 'gitpulse_webhook_verify';
    if (document.getElementById('wa-cfg-biz-name')) document.getElementById('wa-cfg-biz-name').value = cfg.business_name || '';
}

async function saveWhatsAppConfig(e) {
    if (e) e.preventDefault();
    const payload = {
        phone_number_id: document.getElementById('wa-cfg-phone-id').value,
        waba_id: document.getElementById('wa-cfg-waba-id').value,
        access_token: document.getElementById('wa-cfg-token').value,
        verify_token: document.getElementById('wa-cfg-verify-token').value,
        business_name: document.getElementById('wa-cfg-biz-name').value
    };
    
    const res = await apiPost('/api/whatsapp/config', payload);
    if (res && res.success) {
        showToast('WhatsApp Business Cloud API configuration saved.', 'success');
    } else {
        showToast('Failed to save WhatsApp config.', 'error');
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
    
    const res = await apiPost('/api/whatsapp/contacts', { name, phone, email, tags, notes });
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
    
    const res = await apiPost('/api/whatsapp/deals', { title, value, stage, contact_id, expected_close, notes });
    if (res && res.success) {
        showToast(`Deal "${title}" added to pipeline!`, 'success');
        closeAddDealModal();
        loadWhatsAppDeals();
        loadStatus();
    } else {
        showToast(res ? res.error : 'Failed to create deal', 'error');
    }
}

function openAddBroadcastModal() {
    document.getElementById('modal-add-broadcast').classList.remove('hidden');
}
function closeAddBroadcastModal() {
    document.getElementById('modal-add-broadcast').classList.add('hidden');
}
async function submitAddBroadcast(e) {
    e.preventDefault();
    const name = document.getElementById('new-broadcast-name').value;
    const target_tag = document.getElementById('new-broadcast-tag').value;
    const template_body = document.getElementById('new-broadcast-template').value;
    const auto_send = document.getElementById('new-broadcast-send-now').checked;
    
    const res = await apiPost('/api/whatsapp/broadcasts', { name, target_tag, template_body, auto_send });
    if (res && res.success) {
        showToast(`Broadcast "${name}" created${auto_send ? ' & sent!' : '.'}`, 'success');
        closeAddBroadcastModal();
        loadWhatsAppBroadcasts();
        loadStatus();
    } else {
        showToast(res ? res.error : 'Failed to create broadcast', 'error');
    }
}

function openAddAutomationModal() {
    document.getElementById('modal-add-automation').classList.remove('hidden');
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
    
    const res = await apiPost('/api/whatsapp/automations', { name, trigger_type, trigger_keyword, message_template });
    if (res && res.success) {
        showToast(`Automation rule "${name}" created!`, 'success');
        closeAddAutomationModal();
        loadWhatsAppAutomations();
        loadStatus();
    } else {
        showToast(res ? res.error : 'Failed to create automation', 'error');
    }
}


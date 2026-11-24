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
    await loadLogs();
    await loadSettings();
    await loadSupabaseStatus();

    // Auto-refresh metrics, staging queue, and logs every 15 seconds
    setInterval(() => {
        loadStatus();
        loadStagingPosts();
        loadLogs();
    }, 15000);
}

// --- Tabs Navigation ---
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));

    const targetTab = document.getElementById(`tab-${tabName}`);
    if (targetTab) targetTab.classList.remove('hidden');

    const clickedBtn = Array.from(document.querySelectorAll('.nav-tab')).find(btn => 
        btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(tabName)
    );
    if (clickedBtn) clickedBtn.classList.add('active');

    if (tabName === 'staging') loadStagingPosts();
    if (tabName === 'posts') loadPosts();
    if (tabName === 'logs') loadLogs();
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

    document.getElementById('stat-repos-count').innerText = status.projects_count || 0;
    document.getElementById('stat-posts-count').innerText = status.total_posts || 0;
    document.getElementById('stat-published-count').innerText = status.published_posts || 0;
    
    const schedEl = document.getElementById('stat-scheduler-status');
    if (status.scheduler_active) {
        schedEl.innerText = "Running";
        schedEl.className = "text-2xl font-bold mt-1 text-emerald-400";
    } else {
        schedEl.innerText = "Idle";
        schedEl.className = "text-2xl font-bold mt-1 text-yellow-400";
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

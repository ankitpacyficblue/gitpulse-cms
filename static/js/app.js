// GitPulse CMS - Frontend Application Controller

let globalPresets = {};
let currentUser = null;

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    // 1. Verify user session
    const authData = await apiGet('/api/auth/me');
    if (!authData || !authData.user) {
        // If unauthenticated, redirect to login page
        window.location.href = '/login';
        return;
    }
    currentUser = authData.user;
    const userEl = document.getElementById('header-username');
    if (userEl) userEl.innerText = currentUser.username;

    // 2. Load Dashboard Components
    await fetchPresets();
    await loadStatus();
    await loadProjects();
    await loadPosts();
    await loadLogs();
    await loadSettings();

    // Auto-refresh metrics and logs every 15 seconds
    setInterval(() => {
        loadStatus();
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
    btn.innerText = 'Update Admin Password';

    if (res && res.message) {
        showToast('Password updated! Please log in again.', 'success');
        setTimeout(() => {
            window.location.href = '/login';
        }, 1500);
    } else {
        showToast(res ? res.error : 'Failed to update password', 'error');
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
    const data = await apiGet('/api/projects');
    if (!data || !data.projects) return;

    const grid = document.getElementById('projects-grid');
    grid.innerHTML = '';

    const filterSelect = document.getElementById('post-filter-project');
    filterSelect.innerHTML = '<option value="">All Repositories</option>';

    data.projects.forEach(p => {
        // Populate filter
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.innerText = p.name;
        filterSelect.appendChild(opt);

        // Render card
        const card = document.createElement('div');
        card.className = 'project-card';
        card.innerHTML = `
            <div>
                <div class="flex justify-between items-start mb-2">
                    <span class="text-xs px-2 py-0.5 rounded uppercase font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                        ${p.target_framework}
                    </span>
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

            <div class="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between">
                <div class="flex space-x-1.5">
                    <button onclick="triggerProjectRun(${p.id}, this)" class="btn-primary text-xs py-1 px-2.5">
                        ⚡ Publish Now
                    </button>
                    <button onclick="testGitHubConnection(${p.id}, this)" class="btn-secondary text-xs py-1 px-2">
                        Verify Repo
                    </button>
                </div>
                <button onclick="deleteProject(${p.id})" class="btn-danger">
                    Delete
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

// --- Posts & Articles ---
async function loadPosts() {
    const projectId = document.getElementById('post-filter-project').value;
    const url = projectId ? `/api/posts?project_id=${projectId}` : '/api/posts';
    const data = await apiGet(url);
    if (!data || !data.posts) return;

    const tbody = document.getElementById('posts-table-body');
    tbody.innerHTML = '';

    if (data.posts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="px-5 py-6 text-center text-slate-500">No blog posts generated yet. Click "Publish Now" on any project to create your first article!</td></tr>`;
        return;
    }

    data.posts.forEach(post => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-800/40 transition-colors';

        let statusBadge = '<span class="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-400">Draft</span>';
        if (post.status === 'published') {
            statusBadge = '<span class="px-2 py-0.5 rounded text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">Published</span>';
        } else if (post.status === 'failed') {
            statusBadge = '<span class="px-2 py-0.5 rounded text-xs bg-red-500/10 text-red-400 border border-red-500/30">Failed</span>';
        } else if (post.status === 'publishing') {
            statusBadge = '<span class="px-2 py-0.5 rounded text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30">Publishing</span>';
        }

        let githubDelivery = '<span class="text-slate-500 text-xs">Pending commit</span>';
        if (post.github_pr_url) {
            githubDelivery = `<a href="${post.github_pr_url}" target="_blank" class="text-cyan-400 hover:underline text-xs flex items-center gap-1">PR #${post.github_pr_number || 'Link'} ↗</a>`;
        } else if (post.github_commit_sha) {
            githubDelivery = `<span class="text-slate-400 font-mono text-xs">Commit: ${post.github_commit_sha.substring(0, 7)}</span>`;
        }

        tr.innerHTML = `
            <td class="px-5 py-3">
                <div class="font-semibold text-white">${escapeHtml(post.title)}</div>
                <div class="text-xs text-slate-400 font-mono mt-0.5">${escapeHtml(post.target_path)}</div>
            </td>
            <td class="px-5 py-3 text-xs text-slate-300">
                ${escapeHtml(post.project_name || 'Repo')}
            </td>
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

// --- Modals & Add Project ---
function openAddProjectModal() {
    document.getElementById('modal-add-project').classList.remove('hidden');
    onFrameworkSelect();
}

function closeAddProjectModal() {
    document.getElementById('modal-add-project').classList.add('hidden');
}

function onFrameworkSelect() {
    const framework = document.getElementById('add-framework').value;
    const preset = globalPresets[framework];
    if (preset) {
        document.getElementById('add-content-dir').value = preset.content_dir;
    }
}

async function submitAddProject(e) {
    e.preventDefault();
    const payload = {
        name: document.getElementById('add-name').value,
        github_repo: document.getElementById('add-repo').value,
        github_branch: document.getElementById('add-branch').value,
        target_framework: document.getElementById('add-framework').value,
        content_dir: document.getElementById('add-content-dir').value,
        publishing_mode: document.getElementById('add-publishing-mode').value,
        publish_time: document.getElementById('add-publish-time').value,
        topic: document.getElementById('add-topic').value,
        target_audience: document.getElementById('add-audience').value,
        tone: document.getElementById('add-tone').value,
        keywords: document.getElementById('add-keywords').value
    };

    const res = await apiPost('/api/projects', payload);
    if (res && res.id) {
        showToast('Repository successfully connected and activated!', 'success');
        closeAddProjectModal();
        document.getElementById('form-add-project').reset();
        loadProjects();
        loadStatus();
    } else {
        showToast(res ? res.error : 'Failed to register project', 'error');
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
}

async function saveSettings() {
    const payload = {
        github_token: document.getElementById('setting-github-token').value,
        ai_provider: document.getElementById('setting-ai-provider').value,
        gemini_api_key: document.getElementById('setting-gemini-key').value,
        openai_api_key: document.getElementById('setting-openai-key').value
    };

    const res = await apiPost('/api/settings', payload);
    if (res && res.message) {
        showToast('Settings saved successfully.', 'success');
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

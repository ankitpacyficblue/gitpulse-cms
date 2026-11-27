// Dashboard and the single Posts screen. Shapes: docs/UI-REDESIGN.md. Uses helpers in app.js and phase1b.js.
// The view and its filters live in the address (#posts?tab=draft&q=...), so back, reload and links keep them.

const STATE_LABELS = { draft: 'Draft', rejected: 'Rejected', in_review: 'In review', scheduled: 'Scheduled', published: 'Published', failed: 'Failed' };
const EDITOR_STATUS = { draft: 'draft', rejected: 'draft', in_review: 'needs_approval', scheduled: 'approved', published: 'published', failed: 'failed' };
const POST_TABS = [['all', 'All'], ['draft', 'Draft'], ['in_review', 'In review'], ['scheduled', 'Scheduled'], ['published', 'Published'], ['failed', 'Failed']];
const POST_PARAMS = ['account', 'tab', 'project_id', 'writer_id', 'assignee_id', 'from', 'to', 'q', 'sort', 'dir', 'page'];
const SORTS = [['publish_at', 'Scheduled'], ['published_at', 'Published'], ['updated_at', 'Updated'], ['title', 'Title']];
const NEWEST_FIRST = ['published_at', 'updated_at'];
let viewOptions = null, viewSeq = 0, postRows = [], lastQuery = {}, searchTimer, drawerOpener = null;

function readHash() {
    const [view, query] = location.hash.replace(/^#/, '').split('?');
    return { view: view === 'posts' ? 'posts' : view === 'dashboard' || !view ? 'dashboard' : view, params: new URLSearchParams(query || '') };
}
const query = obj => { const s = new URLSearchParams(Object.entries(obj).filter(([, v]) => v)).toString(); return s ? `?${s}` : ''; };
// A change of filter goes back to the first page.
function setView(view, params, replace) {
    const hash = `#${view}${query(params)}`;
    if (replace) history.replaceState(null, '', hash); else history.pushState(null, '', hash);
    renderView();
}
function patchParams(changes, replace) {
    const { view, params } = readHash();
    const next = Object.fromEntries(params);
    if (!('page' in changes)) delete next.page;
    setView(view, { ...next, ...changes }, replace);
}
function routeFromHash() {
    const { view } = readHash();
    switchTab(document.getElementById(`tab-${view}`) ? view : 'dashboard');
}
window.addEventListener('popstate', () => { if (currentUser) routeFromHash(); });

// Called by switchTab: keeps the address in step with the screen.
function enterView(tabName) {
    const { view, params } = readHash();
    const listed = tabName === 'dashboard' || tabName === 'posts';
    el('account-switch').classList.toggle('hidden', listed);
    document.querySelectorAll('[data-tabs]').forEach(b => { b.style.display = b.dataset.tabs.split(' ').includes(tabName) ? '' : 'none'; });
    if (view !== tabName) history.replaceState(null, '', `#${tabName}${listed && params.get('account') ? query({ account: params.get('account') }) : ''}`);
    if (listed) renderView();
}

async function renderView() {
    const { view, params } = readHash();
    if ((view !== 'dashboard' && view !== 'posts') || !currentUser) return;
    const seq = ++viewSeq, account = params.get('account') || 'all';
    el(`tab-${view}`).setAttribute('aria-busy', 'true');
    viewOptions = await apiCall('GET', `/api/content/options${query({ account: 'all' })}`, undefined, { quiet: true });
    if (seq !== viewSeq) return;
    fillAccountSwitch(view, account);
    await (view === 'dashboard' ? renderDashboard(account, seq) : renderPosts(params, account, seq));
    if (seq === viewSeq) el(`tab-${view}`).removeAttribute('aria-busy');
}
const optionList = (key, account) => ((viewOptions && viewOptions[key]) || []).filter(o => account === 'all' || !account || String(o.account_id) === String(account));
function fillSelect(sel, first, options, value) {
    sel.innerHTML = '';
    sel.add(new Option(first[1], first[0]));
    options.forEach(([v, label]) => sel.add(new Option(label, v)));
    sel.value = value;
    if (sel.selectedIndex < 0) sel.selectedIndex = 0;
}
function fillAccountSwitch(view, account) {
    fillSelect(el(`${view}-account`), ['all', 'All accounts'], ((viewOptions && viewOptions.accounts) || []).map(a => [String(a.id), a.name]), account);
    const writable = ((viewOptions && viewOptions.accounts) || []).some(a => a.can_write && (account === 'all' || String(a.id) === account));
    el(`${view}-new`).classList.toggle('hidden', !writable);
}
const loadError = (box, what) => {
    box.innerHTML = `<div class="rd-empty" role="alert">Could not load ${what}. <button type="button" class="btn-secondary text-xs" onclick="renderView()">Try again</button></div>`;
};

// --- Shared pieces ---
const badge = s => `<span class="rd-badge rd-${escapeHtml(s)}">${escapeHtml(STATE_LABELS[s] || s)}</span>`;
const webLink = url => /^https?:\/\//.test(url || '') ? `<a class="rd-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">View on website</a>` : '';
const titleButton = p => `<button type="button" class="rd-title" data-open="${Number(p.id)}" data-account="${escapeHtml(p.account_id)}">${escapeHtml(p.title || 'Untitled')}</button>`;
const who = p => p.writer || p.assignee_name || '';
const postWhen = p => p.state === 'published' ? fmtIst(p.published_at) : fmtIst(p.publish_at);
const meta = parts => parts.filter(Boolean).map(escapeHtml).join(' · ');
const MISSING = { body: 'article text', cover: 'cover image', website: 'website', publish_date: 'publish date' };
const missingText = p => (p.missing || []).length && p.state !== 'published' ? `Missing: ${p.missing.map(m => MISSING[m] || m).join(', ')}` : '';
function actionButtons(p) {
    const b = (act, text, cls) => `<button type="button" class="${cls} text-xs" data-act="${act}" data-id="${Number(p.id)}" data-account="${escapeHtml(p.account_id)}" data-title="${escapeHtml(p.title || '')}">${text}</button>`;
    return [p.can && p.can.approve ? b('approve', 'Approve', 'btn-primary') : '', p.can && p.can.publish_now ? b('publish-now', 'Publish now', 'btn-secondary') : ''].join('');
}
function wirePostControls(box) {
    box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openPost(Number(b.dataset.open), b.dataset.account));
    box.querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
        if (b.dataset.act === 'publish-now' && !confirmPublishNow(b.dataset.title)) return;
        const row = box.querySelectorAll(`[data-act][data-id="${b.dataset.id}"]`);
        row.forEach(x => { x.disabled = true; });
        const res = await apiCall('POST', `/api/blog/plan/${b.dataset.id}/${b.dataset.act}`, {}, { account: b.dataset.account });
        if (res && !res.error) {
            if (res.item && res.item.error) showToast(res.item.error, 'error');
            else showToast(b.dataset.act === 'approve' ? 'Approved. It publishes within 3 hours of the scheduled time.' : 'Published.', 'success');
        }
        renderView();
    });
}

// --- Dashboard ---
async function renderDashboard(account, seq) {
    const data = await apiCall('GET', `/api/dashboard${query({ account })}`, undefined, { quiet: true });
    if (seq !== viewSeq) return;
    const box = el('dashboard-body');
    if (!data || !data.counts) { loadError(box, 'the dashboard'); return; }
    const week = new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 19) + 'Z';
    const month = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 19) + 'Z';
    const now = new Date().toISOString().slice(0, 19) + 'Z';
    const card = (label, n, params, tone) => `<a class="rd-card ${n && tone ? tone : ''}" href="#posts${escapeHtml(query({ account: account === 'all' ? '' : account, ...params }))}" data-nav><span class="rd-card-label">${label}</span><strong>${Number(n || 0)}</strong></a>`;
    const c = data.counts;
    const name = p => account === 'all' ? p.account_name : p.project_name;
    const list = (rows, empty, row) => rows && rows.length ? `<ul class="rd-list">${rows.map(row).join('')}</ul>` : `<p class="rd-empty">${empty}</p>`;
    const panel = (id, title, html) => `<section class="rd-panel" aria-labelledby="${id}"><h2 id="${id}">${title}</h2>${html}</section>`;
    const queue = list(data.approval_queue, 'Nothing is waiting for approval.', p => `<li>
        ${p.cover ? thumbHtml({ ...p.cover, mime: 'image/' }, 'rd-thumb') : '<div class="rd-thumb rd-meta flex items-center justify-center text-center">No cover</div>'}
        <div class="rd-grow">${titleButton(p)}<p class="rd-meta">${meta([name(p), postWhen(p) || 'No date yet', who(p)])}</p>${missingText(p) ? `<p class="rd-warn">${escapeHtml(missingText(p))}</p>` : ''}</div>
        <div class="rd-actions">${actionButtons(p)}<button type="button" class="btn-secondary text-xs" data-open="${Number(p.id)}" data-account="${escapeHtml(p.account_id)}">Review</button></div></li>`);
    const upcoming = list(data.upcoming, 'Nothing is scheduled.', p => `<li class="rd-time"><time datetime="${escapeHtml(p.publish_at || '')}">${escapeHtml(fmtIst(p.publish_at))}</time>
        <div class="rd-grow">${titleButton(p)}<p class="rd-meta">${meta([name(p)])}</p></div></li>`);
    const recent = list(data.recent, 'Nothing published yet.', p => `<li><div class="rd-grow">${titleButton(p)}<p class="rd-meta">${meta([name(p), fmtIst(p.published_at)])}</p></div>${webLink(p.url)}</li>`);
    const alerts = list(data.alerts, 'No problems.', a => `<li><div class="rd-grow"><p class="rd-alert-${a.severity === 'error' ? 'error' : 'warn'}">${escapeHtml(a.message)}${a.count > 1 ? ` (${Number(a.count)} times)` : ''}</p><p class="rd-meta">${meta([a.account_name, fmtIst(a.last_seen)])}</p></div>
        <div class="rd-actions">${/^(blog|conversation|project):\d+$|^messages$/.test(a.link || '') ? `<button type="button" class="btn-secondary text-xs" data-link="${escapeHtml(a.link)}" data-account="${escapeHtml(a.account_id || '')}">Open</button>` : ''}
        ${a.id ? `<button type="button" class="btn-secondary text-xs" data-dismiss="${Number(a.id)}" data-account="${escapeHtml(a.account_id || '')}">Dismiss</button>` : ''}</div></li>`);
    box.innerHTML = `<div class="rd-cards">
        ${card('In review', c.in_review, { tab: 'in_review' }, 'rd-tone-warn')}
        ${card('Scheduled, next 7 days', c.scheduled_7d, { tab: 'scheduled', from: now, to: week })}
        ${card('Published, last 30 days', c.published_30d, { tab: 'published', from: month })}
        ${card('Failed', c.failed, { tab: 'failed' }, 'rd-tone-error')}</div>
        ${(data.alerts || []).length ? panel('dash-alerts', 'Alerts', alerts) : ''}
        <div class="rd-columns">${panel('dash-queue', 'Needs your approval', queue)}${panel('dash-upcoming', 'Going live next', upcoming)}</div>
        ${panel('dash-recent', 'Recently published', recent)}
        ${(data.alerts || []).length ? '' : panel('dash-alerts', 'Alerts', alerts)}`;
    wirePostControls(box);
    box.querySelectorAll('[data-nav]').forEach(a => a.onclick = e => { e.preventDefault(); history.pushState(null, '', a.getAttribute('href')); routeFromHash(); });
    box.querySelectorAll('[data-link]').forEach(b => b.onclick = () => openAlert(b.dataset.link, b.dataset.account));
    box.querySelectorAll('[data-dismiss]').forEach(b => b.onclick = async () => {
        b.disabled = true;
        await apiCall('POST', `/api/alerts/${b.dataset.dismiss}/resolve`, {}, { account: b.dataset.account });
        renderView();
    });
}
async function useAccount(id) {
    const sel = el('client-select-filter');
    if (!id || sel.value === String(id) || ![...sel.options].some(o => o.value === String(id))) return;
    sel.value = String(id);
    await onClientFilterChange();
}
async function openAlert(link, account) {
    const [kind, id] = link.split(':');
    if (kind === 'blog') return openPost(Number(id), account);
    await useAccount(account);
    if (kind === 'conversation') return openChatFromAlert(Number(id));
    if (kind === 'project') return openProjectFromAlert(Number(id));
    switchTab('wa-inbox');
}

// --- Posts ---
const dayStart = (day, add) => day ? new Date(Date.parse(`${day}T00:00:00+05:30`) + add * 864e5).toISOString().slice(0, 19) + 'Z' : '';
function postsFilterChanged() {
    const [kind, id] = el('posts-author').value.split(':');
    patchParams({ project_id: el('posts-project').value, writer_id: kind === 'w' ? id : '', assignee_id: kind === 'm' ? id : '',
        from: dayStart(el('posts-from').value, 0), to: dayStart(el('posts-to').value, 1) });
}
function postsSearch() { clearTimeout(searchTimer); searchTimer = setTimeout(() => { if (readHash().view === 'posts') patchParams({ q: el('posts-q').value.trim() }, true); }, 300); }
function postsAccountChanged() { patchParams({ account: el('posts-account').value === 'all' ? '' : el('posts-account').value, project_id: '', writer_id: '', assignee_id: '' }); }
function dashboardAccountChanged() { patchParams({ account: el('dashboard-account').value === 'all' ? '' : el('dashboard-account').value }); }
function sortBy(key) {
    const dir = lastQuery.sort === key ? (lastQuery.dir === 'asc' ? 'desc' : 'asc') : NEWEST_FIRST.includes(key) ? 'desc' : 'asc';
    patchParams({ sort: key, dir });
}
function sortSelected() { const [sort, dir] = el('posts-sort').value.split(':'); patchParams({ sort, dir }); }
function clearPostFilters() { const { params } = readHash(); setView('posts', { account: params.get('account'), tab: params.get('tab') }); }

async function renderPosts(params, account, seq) {
    const value = k => params.get(k) || '';
    fillSelect(el('posts-project'), ['', 'All websites'], optionList('projects', account).map(p => [String(p.id), p.name]), value('project_id'));
    const authors = el('posts-author');
    authors.innerHTML = '';
    authors.add(new Option('Anyone', ''));
    [['AI writers', 'writers', 'w'], ['Team', 'members', 'm']].forEach(([label, key, kind]) => {
        const group = document.createElement('optgroup');
        group.label = label;
        const seen = new Set();
        optionList(key, account).forEach(o => { if (!seen.has(o.id)) { seen.add(o.id); group.append(new Option(o.name, `${kind}:${o.id}`)); } });
        if (group.children.length) authors.append(group);
    });
    authors.value = value('writer_id') ? `w:${value('writer_id')}` : value('assignee_id') ? `m:${value('assignee_id')}` : '';
    el('posts-from').value = value('from') ? istDay(value('from')) : '';
    el('posts-to').value = value('to') ? istDay(new Date(Date.parse(value('to')) - 1).toISOString()) : '';
    if (document.activeElement !== el('posts-q')) el('posts-q').value = value('q');
    el('posts-clear').classList.toggle('hidden', !['project_id', 'writer_id', 'assignee_id', 'from', 'to', 'q'].some(value));

    const asked = Object.fromEntries(POST_PARAMS.map(k => [k, value(k)]));
    const data = await apiCall('GET', `/api/content/posts${query(asked)}`, undefined, { quiet: true });
    if (seq !== viewSeq) return;
    const body = el('posts-rows');
    if (!data || !data.items) { el('posts-pages').innerHTML = ''; loadError(el('posts-state'), 'the posts'); body.innerHTML = ''; el('posts-table').classList.add('hidden'); return; }
    const tab = value('tab') || 'all';
    lastQuery = { sort: data.sort, dir: data.dir };
    postRows = data.items;
    el('posts-tabs').innerHTML = POST_TABS.map(([k, label]) => `<button type="button" aria-pressed="${k === tab}" data-tab="${k}">${label} <span>${Number((data.counts || {})[k] || 0)}</span></button>`).join('');
    el('posts-tabs').querySelectorAll('button').forEach(b => b.onclick = async () => {
        // The default sort differs by tab, so a tab change drops the chosen sort.
        patchParams({ tab: b.dataset.tab === 'all' ? '' : b.dataset.tab, sort: '', dir: '' });
        el('posts-tabs').querySelector(`[data-tab="${b.dataset.tab}"]`).focus();
    });
    document.querySelectorAll('#posts-table th[data-sort]').forEach(th => {
        const active = th.dataset.sort === data.sort;
        if (active) th.setAttribute('aria-sort', data.dir === 'asc' ? 'ascending' : 'descending'); else th.removeAttribute('aria-sort');
        th.querySelector('span').textContent = active ? (data.dir === 'asc' ? '▲' : '▼') : '';
    });
    el('posts-sort').value = `${data.sort}:${data.dir}`;
    const cell = (label, html, cls) => `<td data-label="${label}" class="${cls || ''}">${html || '<span class="rd-meta">-</span>'}</td>`;
    body.innerHTML = data.items.map(p => `<tr>
        ${cell('Title', `${titleButton(p)}${p.error ? `<p class="rd-alert-error">${escapeHtml(p.error)}</p>` : ''}${missingText(p) ? `<p class="rd-warn">${escapeHtml(missingText(p))}</p>` : ''}`, 'rd-cell-title')}
        ${cell('Status', badge(p.state))}
        ${cell('Website', `${escapeHtml(p.project_name || '')}<p class="rd-meta">${escapeHtml(p.account_name || '')}</p>`)}
        ${cell('Author', escapeHtml(who(p)))}
        ${cell('Scheduled', escapeHtml(fmtIst(p.publish_at)))}
        ${cell('Published', `${escapeHtml(fmtIst(p.published_at))}${p.url ? `<p>${webLink(p.url)}</p>` : ''}`)}
        ${cell('Updated', escapeHtml(fmtIst(p.updated_at)))}
        ${cell('Actions', actionButtons(p) ? `<div class="rd-actions">${actionButtons(p)}</div>` : '', 'rd-cell-actions')}</tr>`).join('');
    el('posts-table').classList.toggle('hidden', !data.items.length);
    el('posts-state').innerHTML = data.items.length ? '' : '<p class="rd-empty">No posts match these filters.</p>';
    wirePostControls(body);
    const pages = Math.max(1, Math.ceil(data.total / data.page_size));
    el('posts-pages').innerHTML = `<span role="status">${Number(data.total)} post${data.total === 1 ? '' : 's'}</span>${pages > 1 ? `<div>
        <button type="button" class="btn-secondary text-xs" ${data.page <= 1 ? 'disabled' : ''} onclick="patchParams({ page: ${data.page - 1} })">Previous</button>
        <span>Page ${Number(data.page)} of ${pages}</span>
        <button type="button" class="btn-secondary text-xs" ${data.page >= pages ? 'disabled' : ''} onclick="patchParams({ page: ${data.page + 1} })">Next</button></div>` : ''}`;
}

// --- Post editor drawer (the form and its actions live in app.js) ---
async function fetchPost(id, account) {
    const data = await apiCall('GET', `/api/content/posts/${id}`, undefined, { account });
    const p = data && data.item;
    return p ? { ...p, status: EDITOR_STATUS[p.state] || p.state, writer_token_id: p.writer_id, post_url: p.url } : null;
}
async function openPost(id, account) {
    const opener = document.activeElement;
    // Editing happens in the post's own account.
    await useAccount(account || el('client-select-filter').value);
    const item = id ? await fetchPost(id, account) : null;
    if (id && !item) return;
    const projects = await apiGet('/api/projects');
    planProjects = (projects && projects.projects) || [];
    planItems = item ? [item] : [];
    drawerOpener = opener;
    el('modal-post').classList.remove('hidden');
    await editPlan(item ? item.id : null);
}
function newPost(view) {
    const account = el(`${view}-account`).value;
    openPost(null, account === 'all' ? el('client-select-filter').value : account);
}
// After a change: read the post and the screen again.
async function refreshAfterEdit() {
    if (planEditing) {
        const item = await fetchPost(planEditing.id);
        planItems = item ? [item] : [];
    }
    renderView();
}
function closePlanForm() {
    planEditing = null;
    if (el('modal-post').classList.contains('hidden')) return;
    el('modal-post').classList.add('hidden');
    if (drawerOpener && drawerOpener.isConnected) drawerOpener.focus(); else el(`tab-${currentTab}`).querySelector('select, button')?.focus();
}
function askClosePost() { if (!planDirty() || confirm('Close without saving your changes?')) closePlanForm(); }
document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !el('modal-post').classList.contains('hidden') && el('modal-media').classList.contains('hidden')) askClosePost();
});

// Section permissions, the CRM dashboard and the role editor. Shapes: docs/CRM-DASHBOARD-PERMISSIONS.md.
// The server enforces access; this only hides what a person cannot use.

const LEVELS = ['none', 'view', 'manage', 'full'];
function has(section, level = 'view') {
    if (isPlatformAdmin() && !getActiveAccountId()) return true;
    if (section === 'database') return isPlatformAdmin();
    return LEVELS.indexOf((window.__access || {})[section] || 'none') >= LEVELS.indexOf(level);
}
const hasAny = (...sections) => sections.some(s => has(s));
const canDismiss = a => a.type === 'blog_failed' ? has('posts', 'manage') : ['inbox', 'contacts', 'pipeline'].some(s => has(s, 'manage'));

// Screen -> section, in the order of the menu. The first allowed one is where a person lands.
const TAB_SECTION = {
    'dashboard': 'blog_dashboard', 'posts': 'posts', 'repos': 'websites', 'media': 'media',
    'wa-dashboard': 'crm_dashboard', 'wa-inbox': 'inbox', 'wa-contacts': 'contacts', 'wa-deals': 'pipeline',
    'wa-broadcasts': 'broadcasts', 'wa-automations': 'automations', 'wa-knowledge': 'ai_assistant',
    'wa-templates': 'templates', 'wa-entry': 'entry_links', 'wa-config': 'wa_setup', 'users': 'users', 'logs': 'logs'
};
function canTab(tab) {
    if (tab === 'settings' || tab === 'supabase') return isPlatformAdmin();
    const section = TAB_SECTION[tab];
    return !section || has(section, section === 'users' ? 'manage' : 'view');
}
const firstTab = () => Object.keys(TAB_SECTION).find(canTab) || 'none';

// Hides menu entries, then menu groups left with nothing in them.
function applySectionMenu() {
    document.querySelectorAll('.sidebar-nav-item').forEach(n => {
        const m = (n.getAttribute('onclick') || '').match(/switchTab\('([\w-]+)'\)/);
        if (m) n.classList.toggle('hidden', !canTab(m[1]));
    });
    document.querySelectorAll('.sidebar-section').forEach(s => s.classList.toggle('hidden', ![...s.querySelectorAll('.sidebar-nav-item')].some(n => !n.classList.contains('hidden'))));
    // WhatsApp setup can be read-only.
    document.querySelectorAll('#tab-wa-config form input, #tab-wa-config form button[type="submit"], #tab-wa-config [onclick^="rotateVerifyToken"], #tab-wa-config [onclick^="testWa"]').forEach(n => { n.disabled = !has('wa_setup', 'manage'); });
}

// --- CRM dashboard ---
const DEAL_STAGES = { lead: 'Lead', qualified: 'Qualified', proposal: 'Proposal', negotiation: 'Negotiation', won: 'Won', lost: 'Lost' };
const money = values => (values || []).map(v => formatMoney(v.value, v.currency)).join(' · ');

function wmAccountChanged() { const v = el('wa-dashboard-account').value; patchParams({ account: v === 'all' ? '' : v }); }

async function renderCrmDashboard(account, seq) {
    fillSelect(el('wa-dashboard-account'), ['all', 'All accounts'], (window.__accounts || []).map(a => [String(a.id), a.name]), account);
    const box = el('wa-dashboard-body');
    const d = await apiCall('GET', `/api/crm/dashboard${query({ account })}`, undefined, { quiet: true });
    if (seq !== viewSeq) return;
    if (d && d.error === 'forbidden') { box.innerHTML = '<p class="rd-empty" role="status">You cannot see the CRM dashboard for this account.</p>'; return; }
    if (!d || !d.cards) { loadError(box, 'the CRM dashboard'); return; }

    const one = account === 'all' ? '' : account;
    const open = (tab, text, cls, acct) => tab && canTab(tab) ? `<button type="button" class="${cls}" data-go="${tab}" data-account="${escapeHtml(String(acct || one))}">${text}</button>` : '';
    const card = (label, value, sub, tab, tone) => {
        if (value === null || value === undefined) return '';
        const inner = `<span class="rd-card-label">${label}</span><strong>${Number(value)}</strong>${sub ? `<span class="rd-meta">${escapeHtml(sub)}</span>` : ''}`;
        const cls = `rd-card ${value && tone ? tone : ''}`;
        return canTab(tab) ? `<button type="button" class="${cls}" data-go="${tab}" data-account="${escapeHtml(one)}">${inner}</button>` : `<div class="${cls}">${inner}</div>`;
    };
    const panel = (id, title, tab, body) => `<section class="rd-panel" aria-labelledby="${id}"><div class="rd-panel-head"><h2 id="${id}">${title}</h2>${open(tab, `Open<span class="sr-only"> ${title}</span>`, 'rd-link')}</div>${body}</section>`;
    const list = (rows, empty, row) => rows.length ? `<ul class="rd-list">${rows.map(row).join('')}</ul>` : `<p class="rd-empty">${empty}</p>`;
    const name = r => account === 'all' ? r.account_name : '';

    const c = d.cards;
    const cards = [
        card('Unread chats', c.unread_conversations, '', 'wa-inbox', 'rd-tone-warn'),
        card('New contacts, last 7 days', c.new_contacts_7d, c.new_contacts_30d == null ? '' : `${c.new_contacts_30d} in 30 days`, 'wa-contacts'),
        c.open_deals ? card('Open deals', c.open_deals.count, money(c.open_deals.values), 'wa-deals') : '',
        c.won_this_month ? card('Won this month', c.won_this_month.count, money(c.won_this_month.values), 'wa-deals') : ''
    ].join('');

    const alerts = (d.alerts || []).length ? panel('crm-alerts', 'Alerts', '', list(d.alerts, '', a => `<li><div class="rd-grow"><p class="rd-alert-${a.severity === 'error' ? 'error' : 'warn'}">${escapeHtml(a.message)}${a.count > 1 ? ` (${Number(a.count)} times)` : ''}</p><p class="rd-meta">${escapeHtml(a.account_name || '')}</p></div>
        <div class="rd-actions">${a.link ? `<button type="button" class="btn-secondary text-xs" data-alert="${escapeHtml(a.link)}" data-account="${escapeHtml(a.account_id || '')}">Open</button>` : ''}${a.id && canDismiss(a) ? `<button type="button" class="btn-secondary text-xs" data-dismiss="${Number(a.id)}" data-account="${escapeHtml(a.account_id || '')}">Dismiss</button>` : ''}</div></li>`)) : '';

    const top = Math.max(1, ...(d.pipeline || []).map(s => s.count));
    const pipeline = d.pipeline ? panel('crm-pipeline', 'Pipeline', 'wa-deals', `<ul class="rd-list">${d.pipeline.map(s => `<li class="rd-stage"><span>${DEAL_STAGES[s.stage] || escapeHtml(s.stage)}</span><span class="rd-bar" aria-hidden="true"><span style="width:${Math.round(100 * s.count / top)}%"></span></span><strong>${Number(s.count)}</strong><span class="rd-meta">${escapeHtml(money(s.values))}</span></li>`).join('')}</ul>`) : '';

    const waiting = d.needs_reply ? panel('crm-reply', 'Waiting for a reply', 'wa-inbox', list(d.needs_reply, 'Nobody is waiting.', r => `<li><div class="rd-grow">
        <button type="button" class="rd-title" data-chat="${Number(r.conversation_id)}" data-account="${escapeHtml(r.account_id)}">${escapeHtml(r.contact_name || 'Unknown')}</button>
        <p class="rd-meta rd-clip">${escapeHtml(r.preview || '')}</p><p class="rd-meta">${meta([name(r), r.waiting_since && `Waiting since ${fmtIst(r.waiting_since)}`])}</p></div>
        ${r.needs_human ? '<span class="rd-badge rd-in_review">Needs a person</span>' : ''}${r.unread ? `<span class="rd-badge">${Number(r.unread)} unread</span>` : ''}</li>`)) : '';

    const broadcasts = d.broadcasts ? panel('crm-bc', 'Recent broadcasts', 'wa-broadcasts', list(d.broadcasts, 'No broadcasts yet.', b => `<li><div class="rd-grow">${open('wa-broadcasts', escapeHtml(b.name), 'rd-title', b.account_id) || `<p class="rd-title">${escapeHtml(b.name)}</p>`}
        <p class="rd-meta">${meta([name(b), fmtIst(b.created_at), b.status])}</p>
        <p class="rd-meta">${Number(b.recipients)} recipients · ${Number(b.sent)} sent · ${Number(b.delivered)} delivered · ${Number(b.read)} read${b.failed ? ` · <span class="rd-alert-error">${Number(b.failed)} failed</span>` : ''}</p></div></li>`)) : '';

    const au = d.automations;
    const automations = au ? panel('crm-auto', 'Automations', 'wa-automations', `<p class="rd-stat"><strong>${Number(au.active)}</strong> of ${Number(au.total)} on</p><p class="rd-meta">Last 7 days: ${Number(au.runs_7d)} runs, <span class="${au.failures_7d ? 'rd-alert-error' : ''}">${Number(au.failures_7d)} failed</span></p>${au.counted_since ? `<p class="rd-meta">Runs counted since ${escapeHtml(fmtIst(au.counted_since))}</p>` : ''}`) : '';

    const t = d.templates;
    const templates = t ? panel('crm-tpl', 'Templates', 'wa-templates', `<p class="rd-stat"><strong>${Number(t.APPROVED || 0)}</strong> approved</p><p class="rd-meta">${Number(t.PENDING || 0)} pending · ${Number(t.REJECTED || 0)} rejected</p>`) : '';

    const entries = d.entry_links ? panel('crm-entry', 'Leads from entry links', 'wa-entry', `<p class="rd-meta">New contacts in the last 30 days who arrived with each link's code.</p>${list(d.entry_links, 'No entry links yet.', l => `<li><div class="rd-grow"><p class="rd-title">${escapeHtml(l.label)}</p><p class="rd-meta">${meta([l.code, name(l)])}</p></div><p class="rd-stat"><strong>${Number(l.leads_30d)}</strong> ${l.leads_30d === 1 ? 'lead' : 'leads'}</p></li>`)}`) : '';

    box.innerHTML = `${cards ? `<div class="rd-cards">${cards}</div>` : ''}${alerts}
        <div class="rd-columns"><div>${waiting}${broadcasts}</div><div>${pipeline}${entries}${automations}${templates}</div></div>`;

    box.querySelectorAll('[data-go]').forEach(b => b.onclick = async () => { await useAccount(b.dataset.account); switchTab(b.dataset.go); });
    box.querySelectorAll('[data-chat]').forEach(b => b.onclick = async () => {
        if (!canTab('wa-inbox')) return showToast('You cannot open the inbox.', 'error');
        await useAccount(b.dataset.account);
        openChatFromAlert(Number(b.dataset.chat));
    });
    box.querySelectorAll('[data-alert]').forEach(b => b.onclick = async () => {
        const link = b.dataset.alert;
        if (link.includes(':')) return openAlert(link, b.dataset.account);
        await useAccount(b.dataset.account);
        const tab = TAB_SECTION[link] ? link : TAB_SECTION[`wa-${link}`] ? `wa-${link}` : 'wa-inbox';
        switchTab(tab);
    });
    box.querySelectorAll('[data-dismiss]').forEach(b => b.onclick = async () => {
        b.disabled = true;
        await apiCall('POST', `/api/alerts/${b.dataset.dismiss}/resolve`, {}, { account: b.dataset.account });
        renderView();
    });
}

// --- Users & Roles ---
const ROLE_HELP = {
    owner: 'Everything, including managing owners and what each role can do.',
    admin: 'Everything except account settings.',
    content_editor: 'Blog only: posts (including publishing), websites and media.',
    crm_agent: 'CRM only: dashboard, inbox, contacts and pipeline.',
    viewer: 'Can look, cannot change anything.'
};
const LEVEL_NAMES = { none: 'No access', view: 'View', manage: 'Manage', full: 'Full' };
const levelName = (s, l) => l === 'full' && s.full_name ? `Manage + ${s.full_name.toLowerCase()}` : LEVEL_NAMES[l] || l;
let roleData = null, peopleSeq = 0;

const levelSelect = (s, value, attrs, first) => `<select class="input-select text-xs" ${attrs}>${first ? `<option value="">${escapeHtml(first)}</option>` : ''}${s.levels.map(l => `<option value="${l}" ${l === value ? 'selected' : ''}>${escapeHtml(levelName(s, l))}</option>`).join('')}</select>`;
const assignableRoles = current => (roleData ? roleData.roles : []).filter(r => r.key !== 'owner' || can('account.manage') || current === 'owner');

async function loadUsersAndRoles() {
    const acct = getActiveAccountId(), seq = ++peopleSeq;
    const body = el('users-table-body'), empty = el('users-empty');
    if (can('account.manage')) loadAccountSettings();
    const sel = el('client-select-filter');
    const accountName = sel && sel.selectedOptions[0] ? sel.selectedOptions[0].text : '';
    if (el('acct-name')) el('acct-name').value = accountName;
    el('users-account-name').innerText = acct && accountName ? accountName : 'this account';
    body.innerHTML = '';
    el('roles-card').classList.add('hidden');
    if (!acct) { empty.innerHTML = emptyStateHtml('Choose a client account', 'Pick an account in the sidebar to see and manage its users.'); return; }
    if (!has('users', 'manage')) return;
    const base = `/api/accounts/${encodeURIComponent(acct)}`;
    const [roles, data] = await Promise.all([apiGet(`${base}/roles`), apiGet(`${base}/users`)]);
    if (seq !== peopleSeq || acct !== getActiveAccountId()) return;
    if (!roles || !roles.roles || !data || !Array.isArray(data.users)) { empty.innerHTML = emptyStateHtml('Could not load people and roles', 'Reload the page to try again.'); return; }
    roleData = roles;
    renderRoleGrid();

    const invite = el('invite-role'), chosen = invite.value;
    invite.innerHTML = '';
    assignableRoles().forEach(r => invite.add(new Option(r.name, r.key)));
    invite.value = chosen || 'viewer';
    invite.onchange = () => { el('invite-role-help').innerText = ROLE_HELP[invite.value] || ''; };
    invite.onchange();

    empty.innerHTML = data.users.length ? '' : emptyStateHtml('No users in this account yet', 'Invite the first person with the form.');
    data.users.forEach(u => {
        const uid = Number(u.user_id != null ? u.user_id : u.id);
        const key = u.role_key || u.role;
        const roleName = (roleData.roles.find(r => r.key === key) || {}).name || key;
        const locked = (currentUser && uid === Number(currentUser.id)) || (key === 'owner' && !can('account.manage'));
        const custom = Object.keys(u.overrides || {}).length;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="px-3 sm:px-5 py-3 text-white break-all">${escapeHtml(u.username || u.email || '')}${u.email && u.username ? `<div class="text-[11px] text-slate-400">${escapeHtml(u.email)}</div>` : ''}${u.is_active === false ? '<span class="ml-2 text-[10px] text-amber-300">inactive</span>' : ''}</td>
            <td class="px-3 sm:px-5 py-3">${locked ? `<span class="text-xs text-slate-300">${escapeHtml(roleName)}</span>`
                : `<select aria-label="Role for ${escapeHtml(u.username)}" class="input-select text-xs min-w-[8rem]">${assignableRoles(key).map(r => `<option value="${r.key}" ${r.key === key ? 'selected' : ''}>${escapeHtml(r.name)}</option>`).join('')}</select>`}
                ${custom ? `<div class="text-[11px] text-amber-300">${custom} custom ${custom === 1 ? 'permission' : 'permissions'}</div>` : ''}</td>
            <td class="px-3 sm:px-5 py-3"><div class="rd-actions justify-end">${locked ? '' : `${key === 'owner' ? '' : '<button type="button" class="btn-secondary text-xs" data-u="access">Access</button>'}
                <button type="button" class="btn-secondary text-xs" data-u="reset">Reset password</button><button type="button" class="btn-secondary text-xs text-red-300" data-u="revoke">Revoke access</button>`}</div></td>`;
        const roleSel = tr.querySelector('select');
        if (roleSel) roleSel.onchange = () => {
            if (custom && !confirm(`Changing the role removes ${u.username}'s custom permissions. Continue?`)) { roleSel.value = key; return; }
            changeUserRole(uid, roleSel.value);
        };
        tr.querySelectorAll('[data-u]').forEach(b => b.onclick = () => {
            if (b.dataset.u === 'access') openAccess(u, uid);
            else if (b.dataset.u === 'reset') resetUserPassword(uid, u.username);
            else revokeUser(uid, u.username);
        });
        body.appendChild(tr);
    });
}

// Roles down the top, sections down the side. Only an owner can change it.
function renderRoleGrid() {
    const { sections, roles, can_edit_roles: edit, my_access: mine } = roleData;
    el('roles-card').classList.remove('hidden');
    el('roles-note').innerText = edit ? 'Change a level, then save that role. Changes apply to everyone with the role.' : 'Only an owner can change these.';
    const cell = (s, r) => {
        const value = r.access[s.key] || 'none';
        return edit && r.editable ? levelSelect(s, value, `data-role="${r.key}" data-section="${s.key}" aria-label="${escapeHtml(`${s.name} for ${r.name}`)}"`) : `<span class="text-xs ${value === 'none' ? 'text-slate-500' : 'text-slate-200'}">${escapeHtml(levelName(s, value))}</span>`;
    };
    el('roles-grid').innerHTML = `<caption class="sr-only">What each role can do in each section</caption>
        <thead><tr><th scope="col">Section</th>${roles.map(r => `<th scope="col">${escapeHtml(r.name)}${r.changed ? ' <span class="rd-warn">(changed)</span>' : ''}</th>`).join('')}</tr></thead>
        <tbody>${sections.map(s => `<tr><th scope="row">${escapeHtml(s.name)}</th>${roles.map(r => `<td>${cell(s, r)}</td>`).join('')}</tr>`).join('')}</tbody>
        ${edit ? `<tfoot><tr><th scope="row"><span class="sr-only">Save or reset</span></th>${roles.map(r => `<td>${r.editable ? `<div class="rd-actions"><button type="button" class="btn-primary text-xs" data-save="${r.key}" disabled>Save<span class="sr-only"> ${escapeHtml(r.name)}</span></button>${r.changed ? `<button type="button" class="btn-secondary text-xs" data-reset="${r.key}">Reset<span class="sr-only"> ${escapeHtml(r.name)}</span></button>` : ''}</div>` : ''}</td>`).join('')}</tr></tfoot>` : ''}`;
    const grid = el('roles-grid');
    grid.querySelectorAll('select[data-role]').forEach(s => s.onchange = () => { grid.querySelector(`[data-save="${s.dataset.role}"]`).disabled = false; });
    grid.querySelectorAll('[data-save]').forEach(b => b.onclick = () => {
        const access = {};
        grid.querySelectorAll(`select[data-role="${b.dataset.save}"]`).forEach(s => { access[s.dataset.section] = s.value; });
        saveRole(b, b.dataset.save, access);
    });
    grid.querySelectorAll('[data-reset]').forEach(b => b.onclick = () => { if (confirm('Put this role back to the default access?')) saveRole(b, b.dataset.reset, null); });
}
async function saveRole(button, key, access) {
    button.disabled = true;
    const url = `/api/accounts/${encodeURIComponent(getActiveAccountId())}/roles/${encodeURIComponent(key)}`;
    const res = access ? await apiPut(url, { access }) : await apiDelete(url);
    if (!res || res.error) { button.disabled = false; return; } // apiCall has shown the reason
    showToast(access ? 'Role saved.' : 'Role reset to default.', 'success');
    await loadUsersAndRoles();
    el('roles-card').focus();
}

// Per-person exceptions to the role.
function openAccess(user, uid) {
    const role = roleData.roles.find(r => r.key === (user.role_key || user.role)) || { access: {}, name: '' };
    const dialog = el('modal-access');
    el('access-h').innerText = `Access for ${user.username}`;
    el('access-note').innerText = `Role: ${role.name}. Choose a level only where this person should differ.`;
    el('access-rows').innerHTML = roleData.sections.map(s => `<label class="rd-access-row"><span>${escapeHtml(s.name)}</span>${levelSelect(s, (user.overrides || {})[s.key], `data-section="${s.key}"`, `Role default (${levelName(s, role.access[s.key] || 'none')})`)}</label>`).join('');
    el('access-form').onsubmit = async e => {
        e.preventDefault();
        const overrides = {};
        el('access-rows').querySelectorAll('select').forEach(s => { if (s.value) overrides[s.dataset.section] = s.value; });
        const res = await apiPut(`/api/accounts/${encodeURIComponent(getActiveAccountId())}/users/${uid}/overrides`, { overrides });
        if (!res || res.error) return;
        dialog.close();
        showToast('Access saved.', 'success');
        loadUsersAndRoles();
    };
    dialog.showModal();
}

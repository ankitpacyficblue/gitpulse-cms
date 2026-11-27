// Phase 1b screens: media library and picker, blog images and review, blog status, writer tokens.
// Shapes: PHASE1-SPEC 9.5. Uses the helpers in app.js.

const MEDIA_LIMITS = { 'image/jpeg': 5, 'image/png': 5, 'image/webp': 5, 'application/pdf': 20, 'video/mp4': 16 }; // MB
const el = id => document.getElementById(id);
const isImage = m => String(m.mime || '').startsWith('image/');
const safeUrl = u => (/^(https?:\/\/|\/(?!\/))/.test(u || '') ? u : '');
const fileSize = n => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;

function thumbHtml(m, cls) {
    const url = safeUrl(m.preview_url || m.url);
    if (url && isImage(m)) return `<img src="${escapeHtml(url)}" alt="" loading="lazy" decoding="async" class="${cls} object-cover rounded bg-slate-950">`;
    const kind = m.mime === 'application/pdf' ? 'PDF' : String(m.mime || '').startsWith('video/') ? 'Video' : 'Image';
    return `<div class="${cls} flex items-center justify-center rounded bg-slate-950 text-xs text-slate-400">${kind}</div>`;
}

// --- Untrusted text: rendered Markdown keeps only plain formatting tags and web links ---
const SAFE_TAGS = new Set('A B BLOCKQUOTE BR CODE DEL EM H1 H2 H3 H4 H5 H6 HR I IMG LI OL P PRE STRONG TABLE TBODY TD TH THEAD TR UL'.split(' '));
const SAFE_ATTRS = { A: ['href', 'title'], IMG: ['src', 'alt', 'title'] };
function sanitizeHtml(html) {
    const tpl = document.createElement('template'); // inert: nothing loads or runs while we clean it
    tpl.innerHTML = html;
    tpl.content.querySelectorAll('*').forEach(node => {
        const tag = node.tagName;
        if (!SAFE_TAGS.has(tag)) {
            if (['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'SVG', 'MATH', 'TEMPLATE'].includes(tag.toUpperCase())) node.remove();
            else node.replaceWith(...node.childNodes);
            return;
        }
        [...node.attributes].forEach(a => {
            const ok = (SAFE_ATTRS[tag] || []).includes(a.name) && (a.name !== 'href' && a.name !== 'src' || /^(https?:|mailto:|#|\/(?!\/))/i.test(a.value.trim()));
            if (!ok) node.removeAttribute(a.name);
        });
        if (tag === 'A') { node.target = '_blank'; node.rel = 'noopener noreferrer'; }
    });
    return tpl.content;
}

// --- Blog times are shown and entered in India time ---
const IST_OFFSET_MS = 5.5 * 3600 * 1000;
const fmtIst = v => v ? `${new Date(v).toLocaleString([], { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} IST` : '';
const istInput = v => v ? new Date(new Date(v).getTime() + IST_OFFSET_MS).toISOString().slice(0, 16) : '';
const istToIso = v => v ? new Date(`${v}:00+05:30`).toISOString() : null;
const istDay = v => new Date(new Date(v).getTime() + IST_OFFSET_MS).toISOString().slice(0, 10);
// Late: approved, and more than one scheduler run (3 hours) past its time.
const isLate = i => i.status === 'approved' && !!i.publish_at && Date.now() - new Date(i.publish_at).getTime() > 3 * 3600 * 1000;

// --- Upload: ask for a signed URL, PUT the file there, then confirm ---
async function uploadMedia(file, onProgress) {
    const limit = MEDIA_LIMITS[file.type];
    if (!limit) { showToast('Only JPEG, PNG, WebP, PDF and MP4 files can be uploaded.', 'error'); return null; }
    if (file.size > limit * 1048576) { showToast(`That file is too large. The limit for this type is ${limit} MB.`, 'error'); return null; }
    const slot = await apiPost('/api/media/upload-url', { name: file.name, mime: file.type, size: file.size });
    if (!slot || slot.error) return null;
    const ok = await new Promise(resolve => {
        const xhr = new XMLHttpRequest();
        xhr.open(slot.method || 'PUT', slot.upload_url);
        Object.entries(slot.headers || {}).forEach(([k, v]) => xhr.setRequestHeader(k, v));
        xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(Math.round(e.loaded / e.total * 100)); };
        xhr.onload = () => resolve(xhr.status >= 200 && xhr.status < 300);
        xhr.onerror = () => resolve(false);
        xhr.send(file);
    });
    if (!ok) { showToast('The upload did not finish. Try again.', 'error'); return null; }
    const done = await apiPost('/api/media', { media_id: slot.media_id });
    return done && !done.error ? done.item : null;
}
async function handleUpload(input, prefix, after) {
    const file = input.files[0];
    if (!file) return;
    const bar = el(`${prefix}-progress`);
    bar.value = 0; bar.classList.remove('hidden'); input.disabled = true;
    const item = await uploadMedia(file, p => { bar.value = p; });
    bar.classList.add('hidden'); input.disabled = false; input.value = '';
    if (item) { showToast('Uploaded.', 'success'); after(item); }
}

// --- Media library ---
let mediaItems = [];
async function fetchMedia(q) {
    const data = await apiCall('GET', `/api/media?q=${encodeURIComponent(q || '')}`, undefined, { quiet: true });
    return data && data.items ? data : null;
}
async function loadMedia() {
    const acct = getActiveAccountId();
    if (!acct) return;
    const data = await fetchMedia(el('media-search').value.trim());
    if (acct !== getActiveAccountId()) return;
    const grid = el('media-grid');
    el('media-not-ready').classList.toggle('hidden', !data || data.configured !== false);
    el('media-upload').classList.toggle('hidden', !data || data.configured === false || !has('media', 'manage'));
    if (!data) { grid.innerHTML = emptyStateHtml('Could not load the library', 'Try again in a moment.'); return; }
    mediaItems = data.items;
    grid.innerHTML = mediaItems.length ? mediaItems.map(m => `<article class="${cardClass} min-w-0">
        ${thumbHtml(m, 'w-full h-32')}
        <h3 class="text-xs font-semibold text-white mt-2 break-words">${escapeHtml(m.name)}</h3>
        <p class="text-[11px] text-slate-400">${fileSize(m.size)}${(m.used_by || []).length ? ` · Used in ${escapeHtml(m.used_by.join(', '))}` : ''}</p>
        <div class="flex flex-wrap gap-2 mt-2">
            ${safeUrl(m.preview_url) ? `<a class="btn-secondary text-xs" href="${escapeHtml(m.preview_url)}" target="_blank" rel="noopener">Open</a>` : ''}
            ${m.blog_url && isImage(m) ? `<button type="button" class="btn-secondary text-xs" data-copy="${escapeHtml(String(m.id))}">Copy for blog</button>` : ''}
            ${has('media', 'full') ? `<button type="button" class="btn-secondary text-xs text-red-300" data-delete="${escapeHtml(String(m.id))}">Delete</button>` : ''}
        </div></article>`).join('') : emptyStateHtml(el('media-search').value ? 'No files match' : 'No files yet', 'Images, PDFs and videos you upload appear here.');
    grid.querySelectorAll('[data-copy]').forEach(b => b.onclick = () => copyForBlog(mediaItems.find(m => String(m.id) === b.dataset.copy)));
    grid.querySelectorAll('[data-delete]').forEach(b => b.onclick = () => deleteMedia(mediaItems.find(m => String(m.id) === b.dataset.delete)));
}
let mediaSearchTimer;
function searchMedia() { clearTimeout(mediaSearchTimer); mediaSearchTimer = setTimeout(loadMedia, 300); }
async function copyForBlog(m) {
    const text = `![${m.name.replace(/\.[^.]+$/, '').replace(/[\[\]]/g, '')}](${m.blog_url})`;
    try { await navigator.clipboard.writeText(text); showToast('Copied. The link starts working once a post using it is published.', 'success'); }
    catch (e) { prompt('Copy this text:', text); }
}
async function deleteMedia(m) {
    if (!confirm(`Delete "${m.name}"?`)) return;
    const url = `/api/media/${m.id}`;
    let res = await apiCall('DELETE', url, undefined, { quiet: true });
    if (res && res.error === 'in_use') {
        if (!confirm(`"${m.name}" is used in ${(m.used_by || []).join(', ') || 'messages'}. Delete it anyway?`)) return;
        res = await apiCall('DELETE', `${url}?force=1`, undefined, { quiet: true });
    }
    if (res && res.error) showToast(errorText(res, 'Could not delete the file.'), 'error');
    loadMedia();
}

// --- Picker: resolves with the chosen item, or null when closed ---
let pickerDone = null, pickerFilter = () => true;
function pickMedia(filter, title) {
    pickerFilter = filter || (() => true);
    el('modal-media-h').innerText = title || 'Choose a file';
    el('picker-search').value = '';
    el('modal-media').classList.remove('hidden');
    loadPicker();
    return new Promise(resolve => { pickerDone = resolve; });
}
function closePicker(item) {
    el('modal-media').classList.add('hidden');
    const done = pickerDone; pickerDone = null;
    if (done) done(item || null);
}
async function loadPicker() {
    const box = el('picker-grid');
    const data = await fetchMedia(el('picker-search').value.trim());
    const ready = !!data && data.configured !== false;
    el('picker-upload').classList.toggle('hidden', !ready || !(has('media', 'manage') || has('posts', 'manage') || has('inbox', 'manage')));
    if (!ready) { box.innerHTML = emptyStateHtml(data ? 'The media library is not set up yet' : 'Could not load the library', data ? 'File storage has to be configured on the server first.' : 'Close and try again.'); return; }
    const items = data.items.filter(pickerFilter);
    box.innerHTML = items.length ? items.map((m, i) => `<button type="button" class="${cardClass} text-left min-w-0" data-i="${i}">${thumbHtml(m, 'w-full h-20')}<span class="block text-[11px] text-slate-200 mt-1 break-words">${escapeHtml(m.name)}</span></button>`).join('')
        : emptyStateHtml('No suitable files', 'Upload one here.');
    box.querySelectorAll('[data-i]').forEach(b => b.onclick = () => closePicker(items[Number(b.dataset.i)]));
}
let pickerSearchTimer;
function searchPicker() { clearTimeout(pickerSearchTimer); pickerSearchTimer = setTimeout(loadPicker, 300); }
function uploadFromPicker(input) { handleUpload(input, 'picker', item => pickerFilter(item) ? closePicker(item) : loadPicker()); }
document.addEventListener('keydown', e => {
    // Escape closes only the picker, not the dialog it was opened from.
    if (e.key === 'Escape' && pickerDone && !el('modal-media').classList.contains('hidden')) { e.stopImmediatePropagation(); closePicker(null); }
}, true);

// --- Blog editor images ---
let planImages = [];
const imagesPayload = list => (list || []).map(i => ({ media_id: i.media_id, alt: i.alt || '', cover: !!i.cover, og: !!i.og }));
function setPlanImages(images) { planImages = (images || []).map(i => ({ ...i })); renderPlanImages(); }
function renderPlanImages() {
    const box = el('plan-images');
    box.innerHTML = planImages.length ? planImages.map((m, i) => `<li class="flex flex-wrap items-center gap-2 border-t border-slate-800 pt-2">
        ${thumbHtml({ ...m, mime: 'image/' }, 'w-16 h-16 shrink-0')}
        <div class="flex-1 min-w-[10rem]"><label for="plan-alt-${i}" class="block text-[11px] text-slate-400 break-words">Alt text for ${escapeHtml(m.name || 'image')}</label>
            <input id="plan-alt-${i}" class="input-text text-sm w-full" maxlength="300" data-alt="${i}" value="${escapeHtml(m.alt || '')}"></div>
        <label class="text-xs text-slate-300 flex items-center gap-1"><input type="radio" name="plan-cover" data-cover="${i}" ${m.cover ? 'checked' : ''}> Cover</label>
        <label class="text-xs text-slate-300 flex items-center gap-1"><input type="checkbox" data-og="${i}" ${m.og ? 'checked' : ''}> Social image</label>
        <button type="button" class="btn-secondary text-xs text-red-300" data-remove="${i}" aria-label="Remove ${escapeHtml(m.name || 'image')}">Remove</button></li>`).join('')
        : '<li class="text-xs text-slate-500">No images yet.</li>';
    box.querySelectorAll('[data-alt]').forEach(n => n.oninput = () => { planImages[n.dataset.alt].alt = n.value; previewPlan(); });
    box.querySelectorAll('[data-cover]').forEach(n => n.onchange = () => { planImages.forEach((m, i) => { m.cover = i === Number(n.dataset.cover); }); previewPlan(); });
    box.querySelectorAll('[data-og]').forEach(n => n.onchange = () => { planImages.forEach((m, i) => { m.og = n.checked && i === Number(n.dataset.og); }); renderPlanImages(); });
    box.querySelectorAll('[data-remove]').forEach(n => n.onclick = () => { planImages.splice(Number(n.dataset.remove), 1); renderPlanImages(); previewPlan(); el('plan-add-image').focus(); });
}
async function addPlanImage() {
    if (planImages.length >= 20) { showToast('A post can have up to 20 images.', 'error'); return; }
    const m = await pickMedia(x => isImage(x) && !planImages.some(p => p.media_id === x.id), 'Add an image');
    if (m) {
        planImages.push({ media_id: m.id, alt: '', cover: !planImages.some(p => p.cover), name: m.name, url: m.preview_url });
        renderPlanImages(); previewPlan();
    }
    el('plan-add-image').focus();
}
function postPreviewHtml(body, images) {
    const img = m => safeUrl(m.url) ? `<figure class="my-2"><img src="${escapeHtml(m.url)}" alt="${escapeHtml(m.alt || '')}" loading="lazy" class="max-w-full max-h-64 rounded">${m.alt ? `<figcaption class="text-[11px] text-slate-500">${escapeHtml(m.alt)}</figcaption>` : ''}</figure>` : `<p class="text-xs text-amber-300">Image "${escapeHtml(m.name || '')}" has no preview.</p>`;
    const list = images || [];
    return list.filter(m => m.cover).map(img).join('') + `<div class="whitespace-pre-wrap break-words">${escapeHtml(body || 'Nothing written yet.')}</div>` + list.filter(m => !m.cover && !m.og).map(img).join('');
}

// --- Reject with a note ---
async function rejectPost(id, note) {
    const res = await apiPost(`/api/blog/plan/${id}/reject`, { note });
    return !!res && !res.error;
}
function toggleRejectBox() {
    const box = el('plan-reject-box');
    box.classList.toggle('hidden');
    if (!box.classList.contains('hidden')) el('plan-reject-note').focus();
}
async function rejectFromEditor() {
    const item = planEditing, note = el('plan-reject-note').value.trim();
    if (!item) return;
    if (!note) { showToast('Write why it is rejected.', 'error'); el('plan-reject-note').focus(); return; }
    if (!(await rejectPost(item.id, note))) return;
    showToast('Rejected. The writer sees your note.', 'success');
    await refreshAfterEdit();
    editPlan(item.id);
}

// --- Blog status and review queue ---
const STATE_NAMES = { in_review: 'needs_approval', scheduled: 'approved' };
const postState = i => STATE_NAMES[i.state] || i.state || (i.status === 'draft' && i.rejected_note ? 'rejected' : i.status);
const POST_STATES = { needs_approval: ['In review', 'text-amber-300'], approved: ['Scheduled', 'text-cyan-300'], published: ['Published', 'text-emerald-400'],
    failed: ['Failed', 'text-red-300'], rejected: ['Rejected', 'text-red-300'], draft: ['Draft', 'text-slate-300'] };
function confirmPublishNow(title) { return confirm(`Publish "${title}" now? It goes live on the website at once.`); }

// Assign a planned post to a writer token (admin only; the token list needs users.manage).
async function fillWriterSelect(item) {
    const wrap = el('plan-writer-wrap'), sel = el('plan-writer');
    sel.innerHTML = '';
    wrap.classList.add('hidden');
    if (!can('content.publish') || !can('users.manage')) return;
    const data = await apiCall('GET', '/api/writer-tokens', undefined, { quiet: true });
    if (!data || !data.tokens || planEditing !== item) return;
    sel.innerHTML = '';
    sel.add(new Option('No writer', ''));
    data.tokens.filter(t => !t.revoked_at || (item && item.writer_token_id === t.id)).forEach(t => sel.add(new Option(t.name, String(t.id))));
    sel.value = item && item.writer_token_id ? String(item.writer_token_id) : '';
    wrap.classList.toggle('hidden', sel.options.length < 2);
}
const writerChoice = () => el('plan-writer-wrap').classList.contains('hidden') ? undefined : (Number(el('plan-writer').value) || null);

// --- Writer tokens (AI writer agents submit drafts; they can never publish) ---
let tokenProjects = {};
async function loadTokenProjects() {
    const data = await apiCall('GET', '/api/projects', undefined, { quiet: true });
    const sel = el('token-project');
    sel.innerHTML = '';
    sel.add(new Option('No default project', ''));
    tokenProjects = {};
    ((data && data.projects) || []).forEach(p => { tokenProjects[p.id] = p.name; sel.add(new Option(p.name, String(p.id))); });
}
async function loadWriterTokens() {
    const acct = getActiveAccountId();
    const card = el('writer-tokens-card');
    if (!acct || !can('users.manage')) { card.classList.add('hidden'); return; }
    const [data] = await Promise.all([apiCall('GET', '/api/writer-tokens', undefined, { quiet: true }), loadTokenProjects()]);
    if (acct !== getActiveAccountId()) return;
    const ready = !!data && Array.isArray(data.tokens);
    card.classList.toggle('hidden', !ready);
    if (!ready) return;
    el('token-list').innerHTML = data.tokens.length ? data.tokens.map(t => `<li class="flex flex-wrap justify-between items-center gap-2 border-t border-slate-800 pt-2 text-xs">
        <div class="min-w-0 flex-1"><div class="text-slate-100 font-semibold break-words">${escapeHtml(t.name)} <code class="text-slate-500">${escapeHtml(t.prefix || '')}…</code></div>
        <div class="text-slate-500">${escapeHtml([`Created ${fmtWhen(t.created_at)}`, t.created_by_name && `by ${t.created_by_name}`, t.project_id && tokenProjects[t.project_id] && `for ${tokenProjects[t.project_id]}`, t.last_used_at ? `last used ${fmtWhen(t.last_used_at)}` : 'never used'].filter(Boolean).join(' · '))}</div></div>
        ${t.revoked_at ? `<span class="text-red-300">Revoked ${escapeHtml(fmtWhen(t.revoked_at))}</span>` : `<button type="button" class="btn-secondary text-xs text-red-300" data-revoke="${Number(t.id)}" data-name="${escapeHtml(t.name)}">Revoke</button>`}</li>`).join('')
        : '<li class="text-xs text-slate-400">No writer tokens yet.</li>';
    el('token-list').querySelectorAll('[data-revoke]').forEach(b => b.onclick = async () => {
        if (!confirm(`Revoke "${b.dataset.name}"? The agent using it stops working at once.`)) return;
        const res = await apiDelete(`/api/writer-tokens/${b.dataset.revoke}`);
        if (res && !res.error) loadWriterTokens();
    });
}
function hideNewToken() { el('token-new').classList.add('hidden'); el('token-value').value = ''; }
async function createWriterToken(e) {
    e.preventDefault();
    const name = el('token-name').value.trim();
    if (!name) return;
    const project = Number(el('token-project').value);
    const res = await apiPost('/api/writer-tokens', { name, ...(project ? { project_id: project } : {}) });
    if (!res || !res.token) return;
    e.target.reset();
    el('token-value').value = res.token;
    el('token-new').classList.remove('hidden');
    el('token-value').select();
    loadWriterTokens();
}
async function copyNewToken() {
    try { await navigator.clipboard.writeText(el('token-value').value); showToast('Copied.', 'success'); }
    catch (e) { el('token-value').select(); showToast('Select the text and copy it.', 'info'); }
}

// --- Media on WhatsApp chat and broadcasts ---
const attached = { chat: null, bc: null, tpl: null };
function showAttached(slot) {
    const m = attached[slot], box = el(`${slot}-media-name`);
    box.innerText = m ? m.name : '';
    el(`${slot}-media-clear`).classList.toggle('hidden', !m);
}
async function attachMedia(slot, headerFormat) {
    const want = { IMAGE: 'image', VIDEO: 'video', DOCUMENT: 'document' }[headerFormat];
    const m = await pickMedia(x => x.whatsapp_type && (!want || x.whatsapp_type === want), 'Attach a file');
    if (m) { attached[slot] = m; showAttached(slot); }
}
function clearMedia(slot) { attached[slot] = null; showAttached(slot); }
// Templates with an image, video or document header need a file of that kind.
function showHeaderPicker(prefix, template) {
    const wrap = el(`${prefix}-media-wrap`);
    if (!wrap) return;
    const format = template && ['IMAGE', 'VIDEO', 'DOCUMENT'].includes(template.header_format) ? template.header_format : '';
    wrap.classList.toggle('hidden', !format);
    wrap.dataset.format = format;
    clearMedia(prefix === 'chat' ? 'tpl' : prefix);
    if (format) wrap.querySelector('[data-label]').innerText = `This template needs ${format === 'IMAGE' ? 'an image' : format === 'VIDEO' ? 'a video' : 'a document'}.`;
}
function messageMediaHtml(media) {
    if (!media) return '';
    const url = safeUrl(media.url);
    if (!url) return `<div class="text-xs opacity-80">File: ${escapeHtml(media.name || 'attachment')}</div>`;
    return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="block underline text-xs mb-1">${isImage(media) ? `<img src="${escapeHtml(url)}" alt="${escapeHtml(media.name || 'Image')}" loading="lazy" class="max-w-[12rem] max-h-48 rounded">` : escapeHtml(media.name || 'Open file')}</a>`;
}

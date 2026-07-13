/* ============================================================
   BulletRevisor — Frontend Logic
   ============================================================ */

// ── State ────────────────────────────────────────────────────
const state = {
  step:         1,
  sessionId:    null,
  selectedFile: null,
  texContent:   '',     // raw .tex source, kept client-side for persistence
  resumeData:   null,   // {sections: {...}}  — editable
  scoredData:   null,   // same structure + score/selected per bullet
  scoredStale:  false,  // true when Step-2 edits happened after scoring
  editKeys:     [],     // ordered section names for Step 2 (index-keyed DOM)
  scoredKeys:   [],     // ordered section names for Step 4
  unlocked:     { 1: true, 2: false, 3: false, 4: false, 5: false },
};

// ── Inline icon set (1.5–1.8px stroke, no external assets) ────
const ICON_LOCK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>`;
const ICON_X    = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 6l12 12M18 6L6 18"></path></svg>`;
const ICON_CHEVRON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"></path></svg>`;
const ICON_GRIP = `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/></svg>`;
const ICON_SEARCH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4.3-4.3"></path></svg>`;
const ICON_TOAST = {
  success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"></path></svg>`,
  error:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16h.01"></path></svg>`,
  info:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 10.5v5.5"></path><path d="M12 7.5h.01"></path></svg>`,
};

// ── Bootstrap ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initUpload();
  initJobDesc();
  initExport();
  bindSidebarNav();
  renderNav();
  initRestore();
  initHelp();
});

// ── Help buttons: popover shows on hover, pins open on click ─
function initHelp() {
  document.querySelectorAll('.help-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const wasPinned = btn.classList.contains('pinned');
      document.querySelectorAll('.help-btn.pinned').forEach(b => b.classList.remove('pinned'));
      if (!wasPinned) btn.classList.add('pinned');
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.help-btn.pinned').forEach(b => b.classList.remove('pinned'));
  });
}

// ── Navigation ───────────────────────────────────────────────
function goToStep(n) {
  if (!state.unlocked[n]) return;

  document.querySelectorAll('.step-panel').forEach(p => p.classList.remove('active'));
  document.getElementById(`step-${n}`).classList.add('active');
  state.step = n;
  renderNav();

  // Ensure scored view is fresh when revisiting step 4
  if (n === 4 && state.scoredData) renderScoredStep();
}

function unlock(n) { state.unlocked[n] = true; }

function renderNav() {
  document.querySelectorAll('.step-item').forEach(el => {
    const n = parseInt(el.dataset.step);
    el.classList.remove('active', 'done', 'unlocked');
    if (n === state.step)              el.classList.add('active');
    if (state.unlocked[n])             el.classList.add('unlocked');
    if (state.unlocked[n] && n < state.step) el.classList.add('done');
  });
}

function bindSidebarNav() {
  document.querySelectorAll('.step-item').forEach(el => {
    el.addEventListener('click', () => {
      const n = parseInt(el.dataset.step);
      if (state.unlocked[n]) goToStep(n);
    });
  });
}

// ── Loading overlay ──────────────────────────────────────────
function showLoading(title = 'Working on it', sub = 'This should only take a moment…') {
  const el = document.createElement('div');
  el.id = 'loading-overlay';
  el.className = 'loading-overlay';
  el.innerHTML = `
    <div class="loading-card">
      <div class="spinner"></div>
      <h3>${esc(title)}</h3>
      <p>${esc(sub)}</p>
    </div>`;
  document.body.appendChild(el);
}
function hideLoading() {
  document.getElementById('loading-overlay')?.remove();
}

// ── Toast ────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const wrap = document.getElementById('toast-container');
  const el   = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-icon">${ICON_TOAST[type] || ICON_TOAST.info}</span><span class="toast-msg">${esc(msg)}</span>`;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

// ── API helper ───────────────────────────────────────────────
async function api(path, opts = {}) {
  const isForm = opts.body instanceof FormData;
  const res = await fetch(`/api/${path}`, {
    method: opts.method || 'GET',
    headers: (!isForm && opts.body) ? { 'Content-Type': 'application/json' } : {},
    body: (!isForm && opts.body) ? JSON.stringify(opts.body) : (opts.body || undefined),
  });
  // Hosting proxies can answer with an HTML error page (502/503) or an empty
  // body instead of our JSON — surface a readable error instead of a
  // JSON.parse exception.
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (e) {
    throw new Error(`The server had a hiccup (${res.status}). Give it a few seconds and try again.`);
  }
  if (!res.ok) throw new Error(data?.error || `Request failed (${res.status})`);
  return data ?? {};
}

// ── Utility ──────────────────────────────────────────────────
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}

function autoResize(ta) {
  ta.style.height = 'auto';
  ta.style.height = ta.scrollHeight + 'px';
}

function timeAgo(iso) {
  if (!iso) return 'recently';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 'recently';
  const diffMs = Date.now() - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins} minute${mins !== 1 ? 's' : ''} ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs} hour${hrs !== 1 ? 's' : ''} ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days} day${days !== 1 ? 's' : ''} ago`;
  return new Date(iso).toLocaleDateString();
}

// ────────────────────────────────────────────────────────────
//  Persistence — everything lives in the user's BROWSER
//  (localStorage). The server never stores resumes beyond the
//  transient compile session, so restarts/redeploys lose nothing.
// ────────────────────────────────────────────────────────────
const STORAGE_KEY = 'br_state';

function initRestore() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch (err) { /* corrupt entry — ignore */ }
  if (!saved || !saved.texContent || !saved.resume_data) return;
  showRestoreCard(saved);
}

function showRestoreCard(saved) {
  const card   = document.getElementById('restore-card');
  const detail = document.getElementById('restore-detail');
  if (!card || !detail) return;

  detail.textContent = `${saved.filename || 'resume.tex'} · Saved ${timeAgo(saved.saved_at)}`;
  card.style.display = '';

  document.getElementById('restore-continue-btn').onclick = async () => {
    showLoading('Restoring your session', 'Rebuilding your workspace…');
    try {
      // Mint a fresh server session from the locally-saved tex so compile
      // works even if the server restarted since the last visit.
      const file = new File([saved.texContent], saved.filename || 'resume.tex',
                           { type: 'text/x-tex' });
      const form = new FormData();
      form.append('file', file);
      const data = await api('upload', { method: 'POST', body: form });

      state.sessionId      = data.session_id;
      state.texContent     = saved.texContent;
      state.resumeFilename = saved.filename || '';
      // Use the SAVED resume data (edits/locks/caps), not the fresh parse.
      state.resumeData     = saved.resume_data;
      state.jobDescription = saved.job_description || '';

      const ta = document.getElementById('job-textarea');
      const wc = document.getElementById('word-count');
      if (ta) {
        ta.value = state.jobDescription;
        const words = ta.value.trim() ? ta.value.trim().split(/\s+/).length : 0;
        if (wc) wc.textContent = `${words} word${words !== 1 ? 's' : ''}`;
      }

      hideLoading();
      unlock(2);
      unlock(3);
      card.style.display = 'none';
      goToStep(2);
      renderEditStep();
      toast('Welcome back, your session was restored', 'success');
    } catch (err) {
      hideLoading();
      toast(`Couldn't restore: ${err.message}`, 'error');
    }
  };

  document.getElementById('restore-dismiss-btn').onclick = () => {
    card.style.display = 'none';
    localStorage.removeItem(STORAGE_KEY);
  };
}

let _autosaveTimer = null;
function scheduleAutosave() {
  if (!state.resumeData) return;
  clearTimeout(_autosaveTimer);
  _autosaveTimer = setTimeout(doAutosave, 800);
}

function doAutosave() {
  if (!state.resumeData || !state.texContent) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      texContent:      state.texContent,
      filename:        state.resumeFilename || '',
      resume_data:     state.resumeData,
      job_description: state.jobDescription || '',
      saved_at:        new Date().toISOString(),
    }));
    flashSaveIndicator();
  } catch (err) {
    // Quota exceeded or private-mode restrictions — best-effort only.
  }
}

let _saveIndicatorTimer = null;
function flashSaveIndicator() {
  const el = document.getElementById('save-indicator');
  if (!el) return;
  el.classList.add('visible');
  clearTimeout(_saveIndicatorTimer);
  _saveIndicatorTimer = setTimeout(() => el.classList.remove('visible'), 1500);
}

// ────────────────────────────────────────────────────────────
//  STEP 1 — Upload
// ────────────────────────────────────────────────────────────
function initUpload() {
  const zone  = document.getElementById('upload-zone');
  const input = document.getElementById('file-input');
  const btn   = document.getElementById('parse-btn');

  zone.addEventListener('click', () => input.click());

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  });

  input.addEventListener('change', () => {
    if (input.files[0]) setFile(input.files[0]);
  });

  btn.addEventListener('click', uploadAndParse);
}

function setFile(file) {
  if (!file.name.endsWith('.tex')) {
    toast('Only .tex files are supported', 'error');
    return;
  }
  state.selectedFile = file;
  document.getElementById('file-info').innerHTML = `
    <div class="file-selected">
      <span class="fi-icon"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg></span>
      <span class="fi-name">${esc(file.name)}</span>
      <span class="fi-size">${(file.size / 1024).toFixed(1)} KB</span>
    </div>`;
  document.getElementById('parse-btn').disabled = false;
}

async function uploadAndParse() {
  if (!state.selectedFile) return;
  showLoading('Reading your resume', 'Parsing LaTeX structure and pulling out every bullet…');
  try {
    // Keep the raw tex client-side: it's what localStorage persistence uses
    // to rebuild a server session after a restart/redeploy.
    state.texContent = await state.selectedFile.text();

    const form = new FormData();
    form.append('file', state.selectedFile);
    const data = await api('upload', { method: 'POST', body: form });

    state.sessionId      = data.session_id;
    state.resumeData     = data.data;
    state.resumeFilename = state.selectedFile.name;

    hideLoading();
    unlock(2);
    unlock(3);
    goToStep(2);
    renderEditStep();
    scheduleAutosave();
    toast('Resume parsed and ready to edit', 'success');
  } catch (err) {
    hideLoading();
    toast(err.message, 'error');
  }
}

// ────────────────────────────────────────────────────────────
//  STEP 2 — Edit Bullets
// ────────────────────────────────────────────────────────────
// Resolve a Step-2 section index to its data array. Section names are never
// placed in the DOM as ids/handlers (they could contain quotes/scripts);
// cards are keyed by numeric index into state.editKeys instead.
function editSection(si) { return state.resumeData.sections[state.editKeys[si]]; }

function renderEditStep() {
  const root = document.getElementById('edit-sections');
  root.innerHTML = '';
  if (!state.resumeData) return;

  state.editKeys = Object.keys(state.resumeData.sections);

  state.editKeys.forEach((sec, si) => {
    const entries = state.resumeData.sections[sec];
    const hasEntries = entries.some(e => e.bullets?.length > 0);
    if (!hasEntries) return;

    const grp = document.createElement('div');
    grp.className = 'section-group';
    grp.innerHTML = `<div class="section-title">${esc(sec)}</div>`;

    entries.forEach((entry, ei) => {
      if (!entry.bullets) return;
      grp.appendChild(buildEditCard(si, ei, entry));
    });

    root.appendChild(grp);
  });

  // Textareas are built detached, so scrollHeight was 0 during autoResize.
  // Re-measure now that they're laid out in the document (synchronous:
  // rAF can be throttled in embedded/background contexts).
  resizeAllBullets();
  setTimeout(resizeAllBullets, 60); // once more after fonts/layout settle
}

function resizeAllBullets() {
  document.querySelectorAll('textarea.bullet-text-el').forEach(autoResize);
}

function buildEditCard(si, ei, entry) {
  const card = document.createElement('div');
  card.className = 'entry-card open';
  card.id = `ec-${si}-${ei}`;
  card.style.setProperty('--i', ei);

  const title    = entryTitle(entry);
  const subtitle = entrySubtitle(entry);
  const date     = entry.date || '';
  const maxB     = entry.max_bullets ?? entry.bullets.length;

  card.innerHTML = `
    <div class="entry-header" onclick="toggleCard('ec-${si}-${ei}')">
      <div class="entry-header-info">
        <div class="entry-title">${esc(title)}</div>
        ${subtitle ? `<div class="entry-subtitle">${esc(subtitle)}</div>` : ''}
      </div>
      ${date ? `<span class="entry-date">${esc(date)}</span>` : ''}
      <span class="entry-chevron">${ICON_CHEVRON}</span>
    </div>
    <div class="entry-body">
      <ul class="bullets-list" id="bl-${si}-${ei}"></ul>
      <button class="add-bullet-btn" onclick="addBullet(${si},${ei})">+ Add bullet point</button>
      <div class="max-ctrl">
        <label for="max-${si}-${ei}">Max bullets in output:</label>
        <input type="number" id="max-${si}-${ei}" min="1" max="30" value="${maxB}"
          onchange="updateMax(${si},${ei},this.value)" />
        <span class="max-hint">bullet${maxB !== 1 ? 's' : ''} shown on resume</span>
      </div>
    </div>`;

  // Pass the card as context so renderBulletList can find the <ul>
  // before the card is attached to the document DOM.
  renderBulletList(si, ei, card);
  return card;
}

function renderBulletList(si, ei, context) {
  // context is passed during initial build (card not yet in DOM);
  // omit it for re-renders when the card is already in the document.
  const ul = context
    ? context.querySelector(`#bl-${si}-${ei}`)
    : document.getElementById(`bl-${si}-${ei}`);
  if (!ul) return;

  const entry = editSection(si)[ei];
  ul.innerHTML = '';

  entry.bullets.forEach((b, bi) => {
    const text   = typeof b === 'string' ? b : (b.clean || b.raw || '');
    const locked = !!b.locked;
    const li     = document.createElement('li');
    li.className = `bullet-item${locked ? ' locked-bullet' : ''}`;
    li.innerHTML = `
      <span class="bullet-drag" title="Drag to reorder" draggable="true">${ICON_GRIP}</span>
      <textarea class="bullet-text-el" rows="1"
        data-si="${si}" data-ei="${ei}" data-bi="${bi}"
      >${esc(text)}</textarea>
      <button class="bullet-lock${locked ? ' is-locked' : ''}"
        title="${locked ? 'Unlock bullet' : 'Lock this bullet so it always stays in the output'}"
        onclick="toggleLock(${si},${ei},${bi})">${ICON_LOCK}</button>
      <button class="bullet-del" title="Remove"
        onclick="removeBullet(${si},${ei},${bi})">${ICON_X}</button>`;
    ul.appendChild(li);
    li.dataset.bi = bi;

    const ta = li.querySelector('textarea');
    autoResize(ta);
    ta.addEventListener('input',  () => { autoResize(ta); saveBulletEdit(si, ei, bi, ta.value); });
    ta.addEventListener('change', () => saveBulletEdit(si, ei, bi, ta.value));

    wireBulletDrag(li, si, ei, bi);
  });
}

// Drag-to-reorder bullets within an entry (handle = the grip icon).
function wireBulletDrag(li, si, ei, bi) {
  const grip = li.querySelector('.bullet-drag');
  grip.addEventListener('dragstart', e => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(bi));
    li.classList.add('dragging');
  });
  grip.addEventListener('dragend', () => li.classList.remove('dragging'));

  li.addEventListener('dragover', e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    li.classList.add('drag-target');
  });
  li.addEventListener('dragleave', () => li.classList.remove('drag-target'));
  li.addEventListener('drop', e => {
    e.preventDefault();
    li.classList.remove('drag-target');
    const from = parseInt(e.dataTransfer.getData('text/plain'), 10);
    const to   = bi;
    if (Number.isNaN(from) || from === to) return;
    const bullets = editSection(si)[ei].bullets;
    const [moved] = bullets.splice(from, 1);
    bullets.splice(to, 0, moved);
    renderBulletList(si, ei);
    markScoredStale();
    scheduleAutosave();
  });
}

function markScoredStale() {
  if (state.scoredData) state.scoredStale = true;
}

function saveBulletEdit(si, ei, bi, val) {
  const bullets = editSection(si)[ei].bullets;
  const bullet = bullets[bi];
  if (typeof bullet === 'string') {
    bullets[bi] = { raw: val, clean: val };
  } else {
    bullet.raw   = val;
    bullet.clean = val;
  }
  markScoredStale();
  scheduleAutosave();
}

function toggleLock(si, ei, bi) {
  const bullets = editSection(si)[ei].bullets;
  const bullet = bullets[bi];
  if (typeof bullet === 'string') {
    bullets[bi] = { raw: bullet, clean: bullet, locked: true };
  } else {
    bullet.locked = !bullet.locked;
  }
  renderBulletList(si, ei); // re-render without context (card already in DOM)
  markScoredStale();
  scheduleAutosave();
}

function addBullet(si, ei) {
  editSection(si)[ei].bullets.push({ raw: '', clean: '', locked: false });
  renderBulletList(si, ei);
  const ul  = document.getElementById(`bl-${si}-${ei}`);
  const tas = ul.querySelectorAll('textarea');
  if (tas.length) tas[tas.length - 1].focus();
  markScoredStale();
  scheduleAutosave();
}

function removeBullet(si, ei, bi) {
  editSection(si)[ei].bullets.splice(bi, 1);
  renderBulletList(si, ei);
  markScoredStale();
  scheduleAutosave();
}

function updateMax(si, ei, val) {
  editSection(si)[ei].max_bullets = Math.max(1, parseInt(val) || 1);
  markScoredStale();
  scheduleAutosave();
}

function toggleCard(id) {
  const card = document.getElementById(id);
  if (!card) return;
  card.classList.toggle('open');
  // Re-measure textareas when a card opens (hidden elements report scrollHeight 0)
  if (card.classList.contains('open')) resizeAllBullets();
}

window.addEventListener('resize', resizeAllBullets);

// ────────────────────────────────────────────────────────────
//  STEP 3 — Job Description
// ────────────────────────────────────────────────────────────
function initJobDesc() {
  const ta  = document.getElementById('job-textarea');
  const wc  = document.getElementById('word-count');
  const btn = document.getElementById('score-btn');
  const clr = document.getElementById('clear-jd-btn');

  ta.addEventListener('input', () => {
    state.jobDescription = ta.value;
    const words = ta.value.trim() ? ta.value.trim().split(/\s+/).length : 0;
    wc.textContent = `${words} word${words !== 1 ? 's' : ''}`;
    scheduleAutosave();
  });

  clr.addEventListener('click', () => {
    ta.value = '';
    state.jobDescription = '';
    wc.textContent = '0 words';
  });

  btn.addEventListener('click', scoreResume);
}

// ────────────────────────────────────────────────────────────
//  STEP 4 — Score & Match
// ────────────────────────────────────────────────────────────
async function scoreResume() {
  const jd = document.getElementById('job-textarea').value.trim();
  if (!jd) { toast('Add a job description first', 'error'); return; }

  showLoading('Matching to the job', 'Scoring every bullet against the description…');
  try {
    const data = await api('score', {
      method: 'POST',
      body: { job_description: jd, resume_data: state.resumeData },
    });

    state.scoredData = data.result;
    state.scoredStale = false;

    // Transfer lock flags from resumeData → scoredData (bullets may be reordered)
    for (const [sec, entries] of Object.entries(state.scoredData.sections)) {
      entries.forEach((entry, ei) => {
        if (!entry.bullets) return;
        const srcBullets = state.resumeData.sections[sec]?.[ei]?.bullets || [];
        entry.bullets.forEach(scoredB => {
          const srcMatch = srcBullets.find(
            sb => (sb.raw || sb.clean || '') === (scoredB.raw || scoredB.clean || '')
          );
          if (srcMatch?.locked) scoredB.locked = true;
        });
      });
    }

    // Default-select: locked bullets always, then top-scoring up to the cap.
    for (const entries of Object.values(state.scoredData.sections)) {
      entries.forEach(entry => {
        if (!entry.bullets) return;
        const cap = effectiveCap(entry);
        let used = 0;
        entry.bullets.forEach(b => {
          if (b.locked)            { b.selected = true;  used++; }
          else if (used < cap)     { b.selected = true;  used++; }
          else                      { b.selected = false; }
        });
      });
    }

    hideLoading();
    unlock(4);
    goToStep(4);
    renderScoredStep();
    toast('Bullets ranked by relevance', 'success');
  } catch (err) {
    hideLoading();
    toast(err.message, 'error');
  }
}

// Locked bullets are always kept, so the real cap is at least the lock count.
function effectiveCap(entry) {
  const cap    = entry.max_bullets ?? entry.bullets.length;
  const locked = entry.bullets.filter(b => b.locked).length;
  return Math.max(cap, locked);
}

function scoredSection(si) { return state.scoredData.sections[state.scoredKeys[si]]; }

function renderScoredStep() {
  const root = document.getElementById('scored-sections');
  root.innerHTML = '';
  if (!state.scoredData) return;

  // If the resume was edited after scoring, the ranking is out of date.
  if (state.scoredStale) {
    root.innerHTML = `
      <div class="restale-banner">
        <div>
          <strong>Your bullets changed since the last match.</strong>
          <span>Re-run matching so the rankings and PDF reflect your edits.</span>
        </div>
        <button class="btn btn-primary" id="rescore-btn">Re-run matching</button>
      </div>`;
    document.getElementById('rescore-btn').onclick = () => { goToStep(3); scoreResume(); };
    return;
  }

  state.scoredKeys = Object.keys(state.scoredData.sections);
  let anyScored = false;

  state.scoredKeys.forEach((sec, si) => {
    const entries = state.scoredData.sections[sec];
    const scoredEntries = entries.filter(e => e.bullets?.length && e.bullets[0]?.score != null);
    if (!scoredEntries.length) return;
    anyScored = true;

    const grp = document.createElement('div');
    grp.className = 'section-group';
    grp.innerHTML = `<div class="section-title">${esc(sec)}</div>`;

    entries.forEach((entry, ei) => {
      if (!entry.bullets?.length || entry.bullets[0]?.score == null) return;
      grp.appendChild(buildScoredCard(si, ei, entry));
    });

    root.appendChild(grp);
  });

  if (!anyScored) {
    root.innerHTML = `
      <div class="empty-state">
        <span class="empty-state-icon">${ICON_SEARCH}</span>
        <p>No scored bullets found. Go back and check your resume data.</p>
      </div>`;
  }
}

function buildScoredCard(si, ei, entry) {
  const card = document.createElement('div');
  card.className = 'entry-card open';
  card.id = `sc-${si}-${ei}`;
  card.style.setProperty('--i', ei);

  const title    = entryTitle(entry);
  const subtitle = entrySubtitle(entry);
  const date     = entry.date || '';
  const selCount = entry.bullets.filter(b => b.selected).length;
  const cap      = effectiveCap(entry);

  card.innerHTML = `
    <div class="entry-header" onclick="toggleCard('sc-${si}-${ei}')">
      <div class="entry-header-info">
        <div class="entry-title">${esc(title)}</div>
        ${subtitle ? `<div class="entry-subtitle">${esc(subtitle)}</div>` : ''}
      </div>
      <span class="counter-badge" id="cnt-${si}-${ei}">
        <span class="cnt">${selCount}</span>&thinsp;/&thinsp;${cap} selected
      </span>
      ${date ? `<span class="entry-date">${esc(date)}</span>` : ''}
      <span class="entry-chevron">${ICON_CHEVRON}</span>
    </div>
    <div class="entry-body">
      <ul class="bullets-list" id="sbl-${si}-${ei}"></ul>
    </div>`;

  renderScoredBullets(si, ei, entry);
  return card;
}

function renderScoredBullets(si, ei, entry) {
  setTimeout(() => {
    const ul = document.getElementById(`sbl-${si}-${ei}`);
    if (!ul) return;
    ul.innerHTML = '';

    entry.bullets.forEach((b, bi) => {
      const score    = b.score ?? 0;
      const pct      = Math.round(score * 100);
      const cls      = score >= 0.65 ? 'score-high' : score >= 0.40 ? 'score-mid' : 'score-low';
      const text     = b.clean || b.raw || '';
      const selected = b.selected;
      const locked   = !!b.locked;

      const li = document.createElement('li');
      li.className = `bullet-item${selected ? '' : ' deselected'}${locked ? ' locked-bullet' : ''}`;
      li.id = `sbi-${si}-${ei}-${bi}`;
      li.innerHTML = `
        <input type="checkbox" class="bullet-chk" ${selected ? 'checked' : ''}
          ${locked ? 'disabled' : `onchange="toggleBullet(${si},${ei},${bi},this.checked)"`} />
        <span class="bullet-text-el">${esc(text)}</span>
        ${locked ? `<span class="lock-icon" title="Locked: always included in output">${ICON_LOCK}</span>` : ''}
        <span class="score-pill ${cls}">
          <span class="score-pill-bar"><span class="score-pill-fill" style="width:${pct}%"></span></span>
          <span class="score-pill-num">${pct}%</span>
        </span>`;
      ul.appendChild(li);
    });
  }, 0);
}

function toggleBullet(si, ei, bi, checked) {
  const entry  = scoredSection(si)[ei];
  const bullet = entry.bullets[bi];
  if (bullet.locked) return; // locked bullets cannot be deselected

  // Enforce the per-entry cap: block selecting beyond it.
  if (checked) {
    const cap = effectiveCap(entry);
    const selCount = entry.bullets.filter(b => b.selected).length;
    if (selCount >= cap) {
      const chk = document.querySelector(`#sbi-${si}-${ei}-${bi} .bullet-chk`);
      if (chk) chk.checked = false;
      toast(`This entry is capped at ${cap} bullet${cap !== 1 ? 's' : ''}. Raise "Max bullets" or deselect another.`, 'info');
      return;
    }
  }

  bullet.selected = checked;

  const li = document.getElementById(`sbi-${si}-${ei}-${bi}`);
  li?.classList.toggle('deselected', !checked);

  // Update counter
  const selCount = entry.bullets.filter(b => b.selected).length;
  const cap      = effectiveCap(entry);
  const cnt      = document.getElementById(`cnt-${si}-${ei}`);
  if (cnt) cnt.innerHTML = `<span class="cnt">${selCount}</span>&thinsp;/&thinsp;${cap} selected`;
}

// ────────────────────────────────────────────────────────────
//  STEP 5 — Export
// ────────────────────────────────────────────────────────────
function initExport() {
  document.getElementById('generate-btn').addEventListener('click', generatePDF);
  document.getElementById('download-btn').addEventListener('click', downloadPDF);
  document.getElementById('start-over-btn').addEventListener('click', startOver);
}

async function generatePDF() {
  if (!state.scoredData) return;
  if (state.scoredStale) {
    toast('Re-run matching first. Your bullets changed since scoring', 'error');
    goToStep(4);
    return;
  }

  // Build final data: selected bullets only (locked bullets are always selected)
  const finalData = { sections: {} };
  for (const [sec, entries] of Object.entries(state.scoredData.sections)) {
    finalData.sections[sec] = entries.map(entry => {
      if (!entry.bullets?.length || entry.bullets[0]?.score == null) return entry;
      return {
        ...entry,
        bullets: entry.bullets
          .filter(b => b.selected || b.locked) // safety net: locked always included
          .map(b => ({ raw: b.raw, clean: b.clean })),
      };
    });
  }

  showLoading('Typesetting your resume', 'Compiling LaTeX to PDF. This can take a minute on the free server…');
  try {
    // Compilation is asynchronous server-side (pdflatex can outlive proxy
    // timeouts on slow hosts): kick it off, then poll for completion.
    await api('compile', {
      method: 'POST',
      body: { session_id: state.sessionId, resume_data: finalData },
    });

    const status = await pollCompile(state.sessionId);
    if (status !== 'done') throw new Error(status);

    hideLoading();
    unlock(5);
    goToStep(5);

    document.getElementById('pdf-iframe').src = `/api/preview/${state.sessionId}`;

    // Default the download filename to "<source-resume-name>.pdf"
    const nameInput = document.getElementById('pdf-name');
    if (nameInput && !nameInput.value.trim()) {
      const base = (state.resumeFilename || 'tailored_resume').replace(/\.tex$/i, '');
      nameInput.value = `${base}.pdf`;
    }

    toast('PDF ready, take a look', 'success');
  } catch (err) {
    hideLoading();
    toast(err.message, 'error');
  }
}

// Poll the async compile until it finishes. Resolves 'done' on success, or
// an error message string on failure/timeout.
async function pollCompile(sessionId, { intervalMs = 2000, maxMs = 300000 } = {}) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    await new Promise(r => setTimeout(r, intervalMs));
    let s;
    try {
      s = await api(`compile/status/${sessionId}`);
    } catch (err) {
      continue; // transient proxy hiccup; keep polling
    }
    if (s.status === 'done') return 'done';
    if (s.status === 'error') return s.error || 'PDF compilation failed';
    if (s.status === 'none') return 'Compile session was lost. Please try again';
  }
  return 'Compilation timed out. The free server may be overloaded, try again in a minute';
}

function downloadPDF() {
  if (!state.sessionId) return;
  let name = (document.getElementById('pdf-name')?.value || '').trim();
  if (name && !/\.pdf$/i.test(name)) name += '.pdf';
  const q = name ? `?name=${encodeURIComponent(name)}` : '';
  window.location.href = `/api/download/${state.sessionId}${q}`;
}

function startOver() {
  state.step        = 1;
  state.sessionId   = null;
  state.selectedFile = null;
  state.resumeData  = null;
  state.scoredData  = null;
  state.scoredStale = false;
  state.texContent  = '';
  state.resumeFilename = '';
  state.jobDescription = '';
  localStorage.removeItem(STORAGE_KEY);
  const nameInput = document.getElementById('pdf-name');
  if (nameInput) nameInput.value = '';
  state.unlocked    = { 1: true, 2: false, 3: false, 4: false, 5: false };

  document.getElementById('file-info').innerHTML   = '';
  document.getElementById('file-input').value      = '';
  document.getElementById('parse-btn').disabled    = true;
  document.getElementById('job-textarea').value    = '';
  document.getElementById('word-count').textContent = '0 words';
  document.getElementById('edit-sections').innerHTML   = '';
  document.getElementById('scored-sections').innerHTML = '';
  document.getElementById('pdf-iframe').src        = '';

  goToStep(1);
  toast('Cleared. Upload a new resume to begin', 'info');
}

// ────────────────────────────────────────────────────────────
//  Helpers
// ────────────────────────────────────────────────────────────
function entryTitle(e) {
  return e.company || e.title || e.school || e.role || e.item || 'Entry';
}
function entrySubtitle(e) {
  const parts = [];
  // Skip role in the subtitle when it's already being used as the title
  if (e.role && (e.company || e.title || e.school)) parts.push(e.role);
  if (e.location) parts.push(e.location);
  return parts.join(' · ');
}

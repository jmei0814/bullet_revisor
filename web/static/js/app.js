/* ============================================================
   BulletRevisor — Frontend Logic
   ============================================================ */

// ── State ────────────────────────────────────────────────────
const state = {
  step:         1,
  sessionId:    null,
  selectedFile: null,
  resumeData:   null,   // {sections: {...}}  — editable
  scoredData:   null,   // same structure + score/selected per bullet
  unlocked:     { 1: true, 2: false, 3: false, 4: false, 5: false },
};

// ── Bootstrap ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initUpload();
  initJobDesc();
  initExport();
  bindSidebarNav();
  renderNav();
});

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
function showLoading(title = 'Processing…', sub = 'Please wait') {
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
  el.textContent = msg;
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
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
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
    toast('Please select a .tex LaTeX file', 'error');
    return;
  }
  state.selectedFile = file;
  document.getElementById('file-info').innerHTML = `
    <div class="file-selected">
      <span class="fi-icon">📄</span>
      <span class="fi-name">${esc(file.name)}</span>
      <span class="fi-size">${(file.size / 1024).toFixed(1)} KB</span>
    </div>`;
  document.getElementById('parse-btn').disabled = false;
}

async function uploadAndParse() {
  if (!state.selectedFile) return;
  showLoading('Parsing Resume', 'Extracting sections and bullet points…');
  try {
    const form = new FormData();
    form.append('file', state.selectedFile);
    const data = await api('upload', { method: 'POST', body: form });

    state.sessionId  = data.session_id;
    state.resumeData = data.data;

    hideLoading();
    unlock(2);
    unlock(3);
    goToStep(2);
    renderEditStep();
    toast('Resume parsed successfully!', 'success');
  } catch (err) {
    hideLoading();
    toast(err.message, 'error');
  }
}

// ────────────────────────────────────────────────────────────
//  STEP 2 — Edit Bullets
// ────────────────────────────────────────────────────────────
function renderEditStep() {
  const root = document.getElementById('edit-sections');
  root.innerHTML = '';
  if (!state.resumeData) return;

  for (const [sec, entries] of Object.entries(state.resumeData.sections)) {
    const hasEntries = entries.some(e => e.bullets?.length > 0);
    if (!hasEntries) continue;

    const grp = document.createElement('div');
    grp.className = 'section-group';
    grp.innerHTML = `<div class="section-title">${esc(sec)}</div>`;

    entries.forEach((entry, ei) => {
      if (!entry.bullets) return;
      grp.appendChild(buildEditCard(sec, ei, entry));
    });

    root.appendChild(grp);
  }
}

function buildEditCard(sec, ei, entry) {
  const card = document.createElement('div');
  card.className = 'entry-card open';
  card.id = `ec-${sec}-${ei}`;

  const title    = entryTitle(entry);
  const subtitle = entrySubtitle(entry);
  const date     = entry.date || '';
  const maxB     = entry.max_bullets ?? entry.bullets.length;

  card.innerHTML = `
    <div class="entry-header" onclick="toggleCard('ec-${sec}-${ei}')">
      <div class="entry-header-info">
        <div class="entry-title">${esc(title)}</div>
        ${subtitle ? `<div class="entry-subtitle">${esc(subtitle)}</div>` : ''}
      </div>
      ${date ? `<span class="entry-date">${esc(date)}</span>` : ''}
      <span class="entry-chevron">▼</span>
    </div>
    <div class="entry-body">
      <ul class="bullets-list" id="bl-${sec}-${ei}"></ul>
      <button class="add-bullet-btn" onclick="addBullet('${sec}',${ei})">+ Add bullet point</button>
      <div class="max-ctrl">
        <label for="max-${sec}-${ei}">Max bullets in output:</label>
        <input type="number" id="max-${sec}-${ei}" min="1" max="30" value="${maxB}"
          onchange="updateMax('${sec}',${ei},this.value)" />
        <span class="max-hint">bullet${maxB !== 1 ? 's' : ''} shown on resume</span>
      </div>
    </div>`;

  // Pass the card as context so renderBulletList can find the <ul>
  // before the card is attached to the document DOM.
  renderBulletList(sec, ei, card);
  return card;
}

function renderBulletList(sec, ei, context) {
  // context is passed during initial build (card not yet in DOM);
  // omit it for re-renders when the card is already in the document.
  const ul = context
    ? context.querySelector(`[id="bl-${sec}-${ei}"]`)
    : document.getElementById(`bl-${sec}-${ei}`);
  if (!ul) return;

  const entry = state.resumeData.sections[sec][ei];
  ul.innerHTML = '';

  entry.bullets.forEach((b, bi) => {
    const text   = typeof b === 'string' ? b : (b.clean || b.raw || '');
    const locked = !!b.locked;
    const li     = document.createElement('li');
    li.className = `bullet-item${locked ? ' locked-bullet' : ''}`;
    li.innerHTML = `
      <span class="bullet-drag" title="Drag to reorder">⠿</span>
      <textarea class="bullet-text-el" rows="1"
        data-sec="${esc(sec)}" data-ei="${ei}" data-bi="${bi}"
      >${esc(text)}</textarea>
      <button class="bullet-lock${locked ? ' is-locked' : ''}"
        title="${locked ? 'Unlock bullet' : 'Lock — always keep in output'}"
        onclick="toggleLock('${sec}',${ei},${bi})">🔒</button>
      <button class="bullet-del" title="Remove"
        onclick="removeBullet('${sec}',${ei},${bi})">×</button>`;
    ul.appendChild(li);

    const ta = li.querySelector('textarea');
    autoResize(ta);
    ta.addEventListener('input',  () => { autoResize(ta); saveBulletEdit(sec, ei, bi, ta.value); });
    ta.addEventListener('change', () => saveBulletEdit(sec, ei, bi, ta.value));
  });
}

function saveBulletEdit(sec, ei, bi, val) {
  const bullet = state.resumeData.sections[sec][ei].bullets[bi];
  if (typeof bullet === 'string') {
    state.resumeData.sections[sec][ei].bullets[bi] = { raw: val, clean: val };
  } else {
    bullet.raw   = val;
    bullet.clean = val;
  }
}

function toggleLock(sec, ei, bi) {
  const bullet = state.resumeData.sections[sec][ei].bullets[bi];
  if (typeof bullet === 'string') {
    state.resumeData.sections[sec][ei].bullets[bi] = { raw: bullet, clean: bullet, locked: true };
  } else {
    bullet.locked = !bullet.locked;
  }
  renderBulletList(sec, ei); // re-render without context (card already in DOM)
}

function addBullet(sec, ei) {
  state.resumeData.sections[sec][ei].bullets.push({ raw: '', clean: '', locked: false });
  renderBulletList(sec, ei);
  const ul  = document.getElementById(`bl-${sec}-${ei}`);
  const tas = ul.querySelectorAll('textarea');
  if (tas.length) tas[tas.length - 1].focus();
}

function removeBullet(sec, ei, bi) {
  state.resumeData.sections[sec][ei].bullets.splice(bi, 1);
  renderBulletList(sec, ei);
}

function updateMax(sec, ei, val) {
  state.resumeData.sections[sec][ei].max_bullets = Math.max(1, parseInt(val) || 1);
}

function toggleCard(id) {
  document.getElementById(id)?.classList.toggle('open');
}

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
  if (!jd) { toast('Please enter a job description', 'error'); return; }

  showLoading('Scoring Bullets', 'Running semantic similarity — this takes a moment…');
  try {
    const data = await api('score', {
      method: 'POST',
      body: { job_description: jd, resume_data: state.resumeData },
    });

    state.scoredData = data.result;

    // Default-select top max_bullets per entry
    for (const entries of Object.values(state.scoredData.sections)) {
      entries.forEach(entry => {
        if (!entry.bullets) return;
        const cap = entry.max_bullets ?? entry.bullets.length;
        entry.bullets.forEach((b, i) => { b.selected = i < cap; });
      });
    }

    // Transfer lock flags from resumeData → scoredData (bullets may be reordered)
    for (const [sec, entries] of Object.entries(state.scoredData.sections)) {
      entries.forEach((entry, ei) => {
        if (!entry.bullets) return;
        const srcBullets = state.resumeData.sections[sec]?.[ei]?.bullets || [];
        entry.bullets.forEach(scoredB => {
          const srcMatch = srcBullets.find(
            sb => (sb.raw || sb.clean || '') === (scoredB.raw || scoredB.clean || '')
          );
          if (srcMatch?.locked) {
            scoredB.locked   = true;
            scoredB.selected = true; // locked bullets are always selected
          }
        });
      });
    }

    hideLoading();
    unlock(4);
    goToStep(4);
    renderScoredStep();
    toast('Bullets scored and ranked!', 'success');
  } catch (err) {
    hideLoading();
    toast(err.message, 'error');
  }
}

function renderScoredStep() {
  const root = document.getElementById('scored-sections');
  root.innerHTML = '';
  if (!state.scoredData) return;

  let anyScored = false;

  for (const [sec, entries] of Object.entries(state.scoredData.sections)) {
    const scoredEntries = entries.filter(e => e.bullets?.length && e.bullets[0]?.score != null);
    if (!scoredEntries.length) continue;
    anyScored = true;

    const grp = document.createElement('div');
    grp.className = 'section-group';
    grp.innerHTML = `<div class="section-title">${esc(sec)}</div>`;

    entries.forEach((entry, ei) => {
      if (!entry.bullets?.length || entry.bullets[0]?.score == null) return;
      grp.appendChild(buildScoredCard(sec, ei, entry));
    });

    root.appendChild(grp);
  }

  if (!anyScored) {
    root.innerHTML = `
      <div class="empty-state">
        <span class="empty-state-icon">🔍</span>
        <p>No scored bullets found. Go back and check your resume data.</p>
      </div>`;
  }
}

function buildScoredCard(sec, ei, entry) {
  const card = document.createElement('div');
  card.className = 'entry-card open';
  card.id = `sc-${sec}-${ei}`;

  const title    = entryTitle(entry);
  const subtitle = entrySubtitle(entry);
  const date     = entry.date || '';
  const selCount = entry.bullets.filter(b => b.selected).length;
  const cap      = entry.max_bullets ?? entry.bullets.length;

  card.innerHTML = `
    <div class="entry-header" onclick="toggleCard('sc-${sec}-${ei}')">
      <div class="entry-header-info">
        <div class="entry-title">${esc(title)}</div>
        ${subtitle ? `<div class="entry-subtitle">${esc(subtitle)}</div>` : ''}
      </div>
      <span class="counter-badge" id="cnt-${sec}-${ei}">
        <span class="cnt">${selCount}</span>&thinsp;/&thinsp;${cap} selected
      </span>
      ${date ? `<span class="entry-date">${esc(date)}</span>` : ''}
      <span class="entry-chevron">▼</span>
    </div>
    <div class="entry-body">
      <ul class="bullets-list" id="sbl-${sec}-${ei}"></ul>
    </div>`;

  renderScoredBullets(sec, ei, entry);
  return card;
}

function renderScoredBullets(sec, ei, entry) {
  setTimeout(() => {
    const ul = document.getElementById(`sbl-${sec}-${ei}`);
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
      li.id = `sbi-${sec}-${ei}-${bi}`;
      li.innerHTML = `
        <input type="checkbox" class="bullet-chk" ${selected ? 'checked' : ''}
          ${locked ? 'disabled' : `onchange="toggleBullet('${sec}',${ei},${bi},this.checked)"`} />
        <span class="bullet-text-el">${esc(text)}</span>
        ${locked ? '<span class="lock-icon" title="Locked — always included in output">🔒</span>' : ''}
        <span class="score-pill ${cls}">${pct}%</span>`;
      ul.appendChild(li);
    });
  }, 0);
}

function toggleBullet(sec, ei, bi, checked) {
  const bullet = state.scoredData.sections[sec][ei].bullets[bi];
  if (bullet.locked) return; // locked bullets cannot be deselected

  bullet.selected = checked;

  const li = document.getElementById(`sbi-${sec}-${ei}-${bi}`);
  li?.classList.toggle('deselected', !checked);

  // Update counter
  const entry    = state.scoredData.sections[sec][ei];
  const selCount = entry.bullets.filter(b => b.selected).length;
  const cap      = entry.max_bullets ?? entry.bullets.length;
  const cnt      = document.getElementById(`cnt-${sec}-${ei}`);
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

  showLoading('Compiling PDF', 'Running pdflatex — this usually takes under 10 seconds…');
  try {
    await api('compile', {
      method: 'POST',
      body: { session_id: state.sessionId, resume_data: finalData },
    });

    hideLoading();
    unlock(5);
    goToStep(5);

    document.getElementById('pdf-iframe').src = `/api/preview/${state.sessionId}`;
    toast('PDF compiled successfully!', 'success');
  } catch (err) {
    hideLoading();
    toast(err.message, 'error');
  }
}

function downloadPDF() {
  if (!state.sessionId) return;
  window.location.href = `/api/download/${state.sessionId}`;
}

function startOver() {
  state.step        = 1;
  state.sessionId   = null;
  state.selectedFile = null;
  state.resumeData  = null;
  state.scoredData  = null;
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
  toast('Ready for a new resume!', 'info');
}

// ────────────────────────────────────────────────────────────
//  Helpers
// ────────────────────────────────────────────────────────────
function entryTitle(e) {
  return e.company || e.title || e.school || e.item || 'Entry';
}
function entrySubtitle(e) {
  const parts = [];
  if (e.role)     parts.push(e.role);
  if (e.location) parts.push(e.location);
  return parts.join(' · ');
}

/* ============================================================
   GLM-OCR — Single-Page Application Logic
   ============================================================ */

'use strict';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const API = '';          // same origin
const SAVE_DEBOUNCE_MS = 1200;
const STATUS_POLL_MS   = 30_000;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let state = {
  jobId:       null,
  filename:    null,
  pageCount:   0,
  currentPage: 1,
  pageStatus:  {},   // pageNum (int) -> 'pending'|'processing'|'done'|'error'
  markdown:    {},   // pageNum (int) -> string
  ocrAllCtrl:  null, // AbortController for SSE
  ocrAllRunning: false,
  previewMode: false,
  saveTimer:   null,
  imageCache:  new Set(),
};

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $ = id => document.getElementById(id);

const uploadZone      = $('uploadZone');
const workspace       = $('workspace');
const dropArea        = $('dropArea');
const fileInput       = $('fileInput');
const statusPill      = $('statusPill');
const statusText      = $('statusText');
const jobFilename     = $('jobFilename');
const btnClose        = $('btnClose');
const btnPrev         = $('btnPrev');
const btnNext         = $('btnNext');
const pageInput       = $('pageInput');
const pageLabel       = $('pageLabel');
const btnOcrPage      = $('btnOcrPage');
const btnOcrAll       = $('btnOcrAll');
const progressWrap    = $('progressWrap');
const progressFill    = $('progressFill');
const progressLabel   = $('progressLabel');
const btnCancelOcr    = $('btnCancelOcr');
const currentPageDot  = $('currentPageDot');
const markdownPageDot = $('markdownPageDot');
const markdownEditor  = $('markdownEditor');
const markdownPreview = $('markdownPreview');
const btnTogglePreview= $('btnTogglePreview');
const btnCopyMd       = $('btnCopyMd');
const btnDownloadMd   = $('btnDownloadMd');
const thumbStrip      = $('thumbStrip');
const saveIndicator   = $('saveIndicator');
const loadingOverlay  = $('loadingOverlay');
const loadingMsg      = $('loadingMsg');
const toastContainer  = $('toastContainer');

// ---------------------------------------------------------------------------
// Utility: toast
// ---------------------------------------------------------------------------
function toast(msg, type = 'info', duration = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ---------------------------------------------------------------------------
// Utility: loading overlay
// ---------------------------------------------------------------------------
function showLoading(msg = 'Processing…') {
  loadingMsg.textContent = msg;
  loadingOverlay.classList.add('show');
}
function hideLoading() {
  loadingOverlay.classList.remove('show');
}

// ---------------------------------------------------------------------------
// Ollama status check
// ---------------------------------------------------------------------------
async function checkStatus() {
  try {
    const res = await fetch(`${API}/api/status`);
    const data = await res.json();
    if (data.ollama_reachable && data.model_available) {
      statusPill.className = 'ok';
      statusText.textContent = 'Ollama · glm-ocr ready';
    } else if (data.ollama_reachable) {
      statusPill.className = 'warn';
      statusText.textContent = 'Ollama up · glm-ocr missing';
    } else {
      statusPill.className = 'err';
      statusText.textContent = data.error || 'Ollama unreachable';
    }
  } catch {
    statusPill.className = 'err';
    statusText.textContent = 'Cannot reach server';
  }
}

// ---------------------------------------------------------------------------
// Upload / drop handling
// ---------------------------------------------------------------------------
dropArea.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

dropArea.addEventListener('dragover', e => {
  e.preventDefault();
  dropArea.classList.add('drag-over');
});
dropArea.addEventListener('dragleave', () => dropArea.classList.remove('drag-over'));
dropArea.addEventListener('drop', e => {
  e.preventDefault();
  dropArea.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f && f.name.toLowerCase().endsWith('.pdf')) handleFile(f);
  else toast('Please drop a PDF file.', 'error');
});

async function handleFile(file) {
  showLoading('Uploading & converting PDF pages…');
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${API}/api/upload`, { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    initJob(data.job_id, data.filename, data.page_count);
  } catch (err) {
    toast(`Upload failed: ${err.message}`, 'error', 5000);
  } finally {
    hideLoading();
  }
}

// ---------------------------------------------------------------------------
// Job initialisation
// ---------------------------------------------------------------------------
function initJob(jobId, filename, pageCount) {
  state.jobId      = jobId;
  state.filename   = filename;
  state.pageCount  = pageCount;
  state.pageStatus = {};
  state.markdown   = {};
  state.currentPage = 1;
  state.imageCache.clear();

  for (let i = 1; i <= pageCount; i++) state.pageStatus[i] = 'pending';

  // UI
  uploadZone.style.display = 'none';
  workspace.style.display  = 'flex';
  jobFilename.textContent  = filename;
  jobFilename.classList.remove('hidden');
  btnClose.classList.remove('hidden');
  pageLabel.textContent = `/ ${pageCount}`;
  pageInput.max = pageCount;

  buildThumbStrip();
  navigateTo(1);
  toast(`Loaded "${filename}" — ${pageCount} page${pageCount !== 1 ? 's' : ''}.`, 'success');
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
function navigateTo(page) {
  page = Math.max(1, Math.min(page, state.pageCount));
  state.currentPage = page;
  pageInput.value = page;

  updateNavButtons();
  updateDots();
  highlightThumb(page);
  loadPageImage(page);
  loadPageMarkdown(page);
}

function updateNavButtons() {
  btnPrev.disabled = state.currentPage <= 1;
  btnNext.disabled = state.currentPage >= state.pageCount;
}

btnPrev.addEventListener('click', () => navigateTo(state.currentPage - 1));
btnNext.addEventListener('click', () => navigateTo(state.currentPage + 1));

pageInput.addEventListener('change', () => {
  const v = parseInt(pageInput.value, 10);
  if (!isNaN(v)) navigateTo(v);
});
pageInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    const v = parseInt(pageInput.value, 10);
    if (!isNaN(v)) navigateTo(v);
  }
});

// ---------------------------------------------------------------------------
// Page image loading
// ---------------------------------------------------------------------------
function loadPageImage(page) {
  const img = $('pageImage');
  const loading = $('imageLoading');

  img.style.display = 'none';
  loading.style.display = 'block';

  const src = `${API}/api/page/${state.jobId}/${page}`;
  img.onload  = () => { loading.style.display = 'none'; img.style.display = 'block'; };
  img.onerror = () => { loading.textContent = 'Image unavailable'; };
  img.src = src;
}

// ---------------------------------------------------------------------------
// Markdown loading
// ---------------------------------------------------------------------------
async function loadPageMarkdown(page) {
  if (state.markdown[page] !== undefined) {
    setEditor(state.markdown[page]);
    return;
  }
  try {
    const res = await fetch(`${API}/api/ocr/${state.jobId}/${page}`);
    if (res.ok) {
      const data = await res.json();
      const md = data.markdown || '';
      state.markdown[page] = md;
      setEditor(md);
    }
  } catch {
    // no markdown yet — that's fine
    setEditor('');
  }
}

function setEditor(text) {
  markdownEditor.value = text;
  if (state.previewMode) renderPreview(text);
}

// ---------------------------------------------------------------------------
// Status dots
// ---------------------------------------------------------------------------
function updateDots() {
  const s = state.pageStatus[state.currentPage] || 'pending';
  currentPageDot.className  = `page-status-dot ${s}`;
  markdownPageDot.className = `page-status-dot ${s}`;
}

function setPageStatus(page, status) {
  state.pageStatus[page] = status;
  updateThumbDot(page, status);
  if (page === state.currentPage) updateDots();
}

// ---------------------------------------------------------------------------
// Thumbnail strip
// ---------------------------------------------------------------------------
function buildThumbStrip() {
  thumbStrip.innerHTML = '';
  for (let i = 1; i <= state.pageCount; i++) {
    const item = document.createElement('div');
    item.className = 'thumb-item';
    item.dataset.page = i;
    item.title = `Page ${i}`;

    const img = document.createElement('img');
    img.loading = 'lazy';
    img.src = `${API}/api/page/${state.jobId}/${i}`;
    img.alt = `Page ${i}`;

    const label = document.createElement('span');
    label.className = 'thumb-label';
    label.textContent = i;

    const dot = document.createElement('span');
    dot.className = 'thumb-dot pending';
    dot.id = `thumbDot-${i}`;

    item.appendChild(img);
    item.appendChild(label);
    item.appendChild(dot);
    item.addEventListener('click', () => navigateTo(i));
    thumbStrip.appendChild(item);
  }
}

function highlightThumb(page) {
  thumbStrip.querySelectorAll('.thumb-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.page, 10) === page);
  });
  // Scroll thumb into view
  const active = thumbStrip.querySelector('.thumb-item.active');
  if (active) active.scrollIntoView({ inline: 'center', behavior: 'smooth', block: 'nearest' });
}

function updateThumbDot(page, status) {
  const dot = $(`thumbDot-${page}`);
  if (dot) dot.className = `thumb-dot ${status}`;
}

// ---------------------------------------------------------------------------
// OCR — single page
// ---------------------------------------------------------------------------
btnOcrPage.addEventListener('click', () => ocrPage(state.currentPage));

async function ocrPage(page) {
  if (!state.jobId) return;
  setPageStatus(page, 'processing');
  if (page === state.currentPage) updateDots();

  try {
    const res = await fetch(`${API}/api/ocr/${state.jobId}/${page}`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    state.markdown[page] = data.markdown;
    setPageStatus(page, 'done');
    if (page === state.currentPage) {
      setEditor(data.markdown);
      toast(`Page ${page} OCR complete.`, 'success');
    }
  } catch (err) {
    setPageStatus(page, 'error');
    toast(`OCR page ${page} failed: ${err.message}`, 'error', 5000);
  }
}

// ---------------------------------------------------------------------------
// OCR — all pages (SSE streaming)
// ---------------------------------------------------------------------------
btnOcrAll.addEventListener('click', startOcrAll);
btnCancelOcr.addEventListener('click', cancelOcrAll);

function startOcrAll() {
  if (!state.jobId || state.ocrAllRunning) return;

  state.ocrAllRunning = true;
  progressWrap.style.display = 'flex';
  btnOcrAll.disabled = true;
  btnOcrPage.disabled = true;
  setProgress(0, state.pageCount);

  // Use fetch + ReadableStream for SSE
  const ctrl = new AbortController();
  state.ocrAllCtrl = ctrl;

  (async () => {
    try {
      const res = await fetch(`${API}/api/ocr/${state.jobId}/all`, {
        method: 'POST',
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || res.statusText);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop(); // last incomplete line stays

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));
            handleOcrAllEvent(event);
          } catch { /* ignore malformed */ }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        toast(`OCR all failed: ${err.message}`, 'error', 5000);
      }
    } finally {
      finishOcrAll();
    }
  })();
}

function handleOcrAllEvent(event) {
  if (event.status === 'complete') return;

  const page = event.page_num;
  setProgress(page, event.total);

  if (event.status === 'processing') {
    setPageStatus(page, 'processing');
  } else if (event.status === 'done') {
    setPageStatus(page, 'done');
    state.markdown[page] = event.markdown;
    if (page === state.currentPage) {
      setEditor(event.markdown);
    }
  } else if (event.status === 'error') {
    setPageStatus(page, 'error');
    toast(`Page ${page} OCR error: ${event.error}`, 'error', 4000);
  }
}

function setProgress(done, total) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  progressFill.style.width = `${pct}%`;
  progressLabel.textContent = `${done} / ${total}`;
}

function cancelOcrAll() {
  if (state.ocrAllCtrl) state.ocrAllCtrl.abort();
  finishOcrAll();
}

function finishOcrAll() {
  state.ocrAllRunning = false;
  state.ocrAllCtrl = null;
  progressWrap.style.display = 'none';
  btnOcrAll.disabled = false;
  btnOcrPage.disabled = false;
  toast('OCR complete.', 'success');
}

// ---------------------------------------------------------------------------
// Markdown editor — auto-save (debounced)
// ---------------------------------------------------------------------------
markdownEditor.addEventListener('input', () => {
  const page = state.currentPage;
  state.markdown[page] = markdownEditor.value;

  if (state.previewMode) renderPreview(markdownEditor.value);

  showSaveIndicator('saving');
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => saveMarkdown(page, markdownEditor.value), SAVE_DEBOUNCE_MS);
});

async function saveMarkdown(page, markdown) {
  if (!state.jobId) return;
  try {
    const res = await fetch(`${API}/api/ocr/${state.jobId}/${page}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markdown }),
    });
    if (res.ok) {
      showSaveIndicator('saved');
      setPageStatus(page, 'done');
    }
  } catch {
    showSaveIndicator('');
  }
}

function showSaveIndicator(state_) {
  if (state_ === 'saving') {
    saveIndicator.textContent = 'Saving…';
    saveIndicator.className = 'saving';
  } else if (state_ === 'saved') {
    saveIndicator.textContent = 'Saved';
    saveIndicator.className = 'saved';
    setTimeout(() => { saveIndicator.textContent = ''; saveIndicator.className = ''; }, 2000);
  } else {
    saveIndicator.textContent = '';
    saveIndicator.className = '';
  }
}

// ---------------------------------------------------------------------------
// Markdown preview toggle
// ---------------------------------------------------------------------------
btnTogglePreview.addEventListener('click', () => {
  state.previewMode = !state.previewMode;
  if (state.previewMode) {
    markdownEditor.style.display  = 'none';
    markdownPreview.style.display = 'block';
    btnTogglePreview.textContent  = 'Edit';
    renderPreview(markdownEditor.value);
  } else {
    markdownEditor.style.display  = '';
    markdownPreview.style.display = 'none';
    btnTogglePreview.textContent  = 'Preview';
  }
});

function renderPreview(md) {
  if (typeof marked !== 'undefined') {
    markdownPreview.innerHTML = marked.parse(md || '');
  } else {
    markdownPreview.textContent = md;
  }
}

// ---------------------------------------------------------------------------
// Copy markdown
// ---------------------------------------------------------------------------
btnCopyMd.addEventListener('click', async () => {
  const text = markdownEditor.value;
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied to clipboard.', 'success');
  } catch {
    toast('Could not copy — use Ctrl+A, Ctrl+C.', 'error');
  }
});

// ---------------------------------------------------------------------------
// Download all pages as one .md file
// ---------------------------------------------------------------------------
btnDownloadMd.addEventListener('click', () => {
  if (!state.jobId) return;
  const parts = [];
  for (let i = 1; i <= state.pageCount; i++) {
    const md = state.markdown[i];
    if (md) {
      parts.push(`<!-- Page ${i} -->\n${md}`);
    }
  }
  if (parts.length === 0) {
    toast('No OCR results yet.', 'error');
    return;
  }
  const blob = new Blob([parts.join('\n\n---\n\n')], { type: 'text/markdown' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = (state.filename || 'document').replace(/\.pdf$/i, '') + '.md';
  a.click();
  URL.revokeObjectURL(url);
});

// ---------------------------------------------------------------------------
// Close job
// ---------------------------------------------------------------------------
btnClose.addEventListener('click', async () => {
  if (!state.jobId) return;
  if (!confirm('Close this job and delete temporary files?')) return;

  try {
    await fetch(`${API}/api/jobs/${state.jobId}`, { method: 'DELETE' });
  } catch { /* best-effort */ }

  resetState();
});

function resetState() {
  state = {
    jobId:         null,
    filename:      null,
    pageCount:     0,
    currentPage:   1,
    pageStatus:    {},
    markdown:      {},
    ocrAllCtrl:    null,
    ocrAllRunning: false,
    previewMode:   false,
    saveTimer:     null,
    imageCache:    new Set(),
  };

  workspace.style.display  = 'none';
  uploadZone.style.display = '';
  jobFilename.classList.add('hidden');
  btnClose.classList.add('hidden');
  fileInput.value          = '';
  markdownEditor.value     = '';
  markdownPreview.innerHTML= '';
  thumbStrip.innerHTML     = '';
  progressWrap.style.display = 'none';
  btnOcrAll.disabled  = false;
  btnOcrPage.disabled = false;
  markdownEditor.style.display  = '';
  markdownPreview.style.display = 'none';
  btnTogglePreview.textContent  = 'Preview';
}

// ---------------------------------------------------------------------------
// Keyboard shortcuts
// ---------------------------------------------------------------------------
document.addEventListener('keydown', e => {
  if (!state.jobId) return;
  // Don't intercept when typing in the editor
  if (document.activeElement === markdownEditor) return;

  if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   { e.preventDefault(); navigateTo(state.currentPage - 1); }
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown')  { e.preventDefault(); navigateTo(state.currentPage + 1); }
  if (e.key === 'Enter' && !e.shiftKey)                 { e.preventDefault(); ocrPage(state.currentPage); }
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
checkStatus();
setInterval(checkStatus, STATUS_POLL_MS);

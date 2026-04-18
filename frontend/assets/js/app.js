/**
 * PDF AI — Upload e envio para análise (resultado na página Relatório).
 */

document.querySelectorAll('.nav-link[href]').forEach((link) => {
  link.addEventListener('click', (e) => {
    const href = link.getAttribute('href');
    if (href && href.endsWith('.html')) {
      e.preventDefault();
      document.body.classList.add('page-exit');
      setTimeout(() => { window.location.href = href; }, 500);
    }
  });
});

if (sessionStorage.getItem('page-transition') === 'enter') {
  document.body.classList.add('page-enter');
  sessionStorage.removeItem('page-transition');
}

const STORAGE_KEY = 'pdfAnalysisReportV1';

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('pdfFile');
const fileLabel = document.getElementById('fileLabel');
const pdfForm = document.getElementById('pdfForm');

if (pdfForm) {
  pdfForm.addEventListener('submit', handleUpload);
}

if (dropZone && fileInput) {
  ['dragenter', 'dragover'].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => { e.preventDefault(); dropZone.classList.add('dragover'); })
  );
  ['dragleave', 'drop'].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); })
  );
  dropZone.addEventListener('drop', (e) => {
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      updateFileLabel(fileInput.files[0]);
    }
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) updateFileLabel(fileInput.files[0]);
  });
}

function updateFileLabel(file) {
  if (fileLabel) {
    const sizeMB = (file.size / 1024 / 1024).toFixed(1);
    fileLabel.innerHTML = `<span class="upload-selected">${esc(file.name)}</span> <span style="color:var(--text-muted)">(${sizeMB} MB)</span>`;
  }
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function renderLastProfileCard(data) {
  const card = document.getElementById('lastProfileCard');
  const chipsNode = document.getElementById('lastProfileChips');
  const noteNode = document.getElementById('lastProfileNote');
  if (!card || !chipsNode || !noteNode) return;

  const profile = (data && data.document_profile) || {};
  const type = String(profile.type || data?.document_type_label || data?.document_type || '').trim();
  const domain = String(profile.domain || '').trim();
  const subtype = String(profile.subtype || '').trim();
  if (!type && !domain && !subtype) {
    card.hidden = true;
    return;
  }

  const chips = [];
  if (domain) chips.push(`<span class="home-profile-chip">${esc(domain)}</span>`);
  if (subtype && subtype !== type) chips.push(`<span class="home-profile-chip">${esc(subtype)}</span>`);
  if (type) chips.push(`<span class="home-profile-chip home-profile-chip-main">${esc(type)}</span>`);
  chipsNode.innerHTML = chips.join('');

  const openSet = data?.document_type_open_set === true;
  const reason = String(data?.document_type_reason || '').trim();
  noteNode.textContent = openSet
    ? `Open-set ativo na última análise (${reason || 'sinal fraco'}).`
    : 'Perfil inferido pela IA e heurística do backend.';
  card.hidden = false;
}

function loadLastProfileFromStorage() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    renderLastProfileCard(data);
  } catch {
    // ignore storage parsing issues
  }
}

let progressInterval = null;

function showProgress(step, percent) {
  const container = document.getElementById('progressContainer');
  const fill = document.getElementById('progressFill');
  const label = document.getElementById('progressLabel');
  if (container) container.style.display = 'block';
  if (fill) fill.style.width = `${percent}%`;
  if (label) label.textContent = step;
}

function startProgressAnimation() {
  const steps = [
    { text: 'Lendo PDF…', pct: 15 },
    { text: 'Extraindo texto…', pct: 30 },
    { text: 'Classificando documento…', pct: 45 },
    { text: 'Analisando com IA…', pct: 60 },
    { text: 'Montando relatório…', pct: 82 },
    { text: 'Quase pronto…', pct: 92 },
  ];
  let i = 0;
  showProgress(steps[0].text, steps[0].pct);
  progressInterval = setInterval(() => {
    i += 1;
    if (i < steps.length) showProgress(steps[i].text, steps[i].pct);
  }, 4200);
}

function stopProgress(success) {
  clearInterval(progressInterval);
  showProgress(success ? 'Concluído' : 'Falhou', 100);
  setTimeout(() => {
    const container = document.getElementById('progressContainer');
    if (container) container.style.display = 'none';
  }, 900);
}

async function handleUpload(e) {
  e.preventDefault();
  if (!fileInput.files[0]) return;

  const btn = document.getElementById('submitBtn');
  const status = document.getElementById('statusMsg');

  btn.disabled = true;
  btn.textContent = 'Processando…';
  btn.classList.add('processing');
  status.className = 'status-msg info';
  status.textContent = 'Enviando arquivo ao servidor…';

  startProgressAnimation();

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  try {
    const res = await fetch('/analyze', { method: 'POST', body: formData });
    const data = await res.json();

    if (res.ok && data.extracted_data) {
      renderLastProfileCard(data);
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      status.className = 'status-msg success';
      status.textContent = 'Análise concluída. Abrindo relatório…';
      stopProgress(true);
      sessionStorage.setItem('page-transition', 'enter');
      setTimeout(() => { window.location.href = 'analise.html'; }, 450);
    } else {
      status.className = 'status-msg error';
      status.textContent = data.error || 'Erro desconhecido';
      stopProgress(false);
    }
  } catch (err) {
    console.error('[PDF AI]', err);
    status.className = 'status-msg error';
    status.textContent = 'Falha na conexão. Verifique se o backend está em execução e se o modelo local está ativo.';
    stopProgress(false);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Iniciar análise';
    btn.classList.remove('processing');
  }
}

async function refreshLlmBanner() {
  const el = document.getElementById('llmStatusBanner');
  if (!el) return;
  try {
    const r = await fetch('/health/llm');
    const d = await r.json();
    let show = false;
    let msg = '';
    if (!d.reachable) {
      show = true;
      const extra = d.error || d.error_type || (d.http_status !== undefined ? `HTTP ${d.http_status}` : '');
      const tip = d.hint_pt ? ` ${d.hint_pt}` : '';
      msg = `Servidor LLM inacessível.${tip}${extra ? ` Detalhe técnico: ${extra}` : ''}`;
    } else if (d.configured_model_listed === false) {
      show = true;
      msg = `O modelo "${d.configured_model || ''}" não aparece na lista do servidor. Ajuste LLM_MODEL no .env para o id exato em GET /models.`;
    }
    if (show) {
      el.hidden = false;
      el.textContent = msg;
    } else {
      el.hidden = true;
      el.textContent = '';
    }
  } catch {
    el.hidden = false;
    el.textContent = 'Não foi possível contactar o backend para verificar o LLM.';
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    refreshLlmBanner();
    loadLastProfileFromStorage();
  });
} else {
  refreshLlmBanner();
  loadLastProfileFromStorage();
}

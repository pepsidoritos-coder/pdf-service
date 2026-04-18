/**
 * Relatório rico de análise (página analise.html).
 * Lê sessionStorage `pdfAnalysisReportV1` preenchido após upload em index.
 */
const STORAGE_KEY = 'pdfAnalysisReportV1';
const TWO_DIGIT_YEAR_PIVOT = 30;

let lastResponse = null;

function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function uniqueDates(arr) {
  if (!arr || !arr.length) return [];
  const seen = new Map();
  const order = [];
  for (const raw of arr) {
    const s = String(raw).trim();
    const m = s.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/);
    let key;
    let display = s;
    if (m) {
      const d = parseInt(m[1], 10);
      const mo = parseInt(m[2], 10);
      const yStr = m[3];
      let yi = parseInt(yStr, 10);
      if (yStr.length === 2) yi = yi <= TWO_DIGIT_YEAR_PIVOT ? 2000 + yi : 1900 + yi;
      key = `${d}-${mo}-${yi}`;
      display = `${String(d).padStart(2, '0')}/${String(mo).padStart(2, '0')}/${yi}`;
    } else {
      key = `raw:${s}`;
    }
    if (!seen.has(key)) {
      seen.set(key, display);
      order.push(key);
    }
  }
  return order.map((k) => seen.get(k));
}

function monetaryValues(ext) {
  if (ext.values_found?.length) return ext.values_found;
  if (ext.values?.length) return ext.values;
  if (ext.total_value) return [ext.total_value];
  return [];
}

const LLM_STRATEGY_LABELS = {
  full_document: 'leitura integral',
  head_tail: 'início + fim',
  chunked_synthesis: 'multi-trechos + síntese',
};

function refreshLlmLiveStrip() {
  const live = document.getElementById('reportLlmLive');
  if (!live) return;
  live.style.display = 'block';
  live.className = 'glass-panel report-llm-live';
  live.textContent = 'A consultar GET /health/llm…';
  fetch('/health/llm')
    .then((r) => r.json())
    .then((p) => {
      if (p.reachable) {
        live.classList.add('report-llm-live-ok');
        const modelWarn = p.configured_model_listed === false;
        const url = esc(String(p.probe_url || ''));
        const model = esc(String(p.configured_model || ''));
        live.innerHTML = `<strong>Servidor LLM acessível agora.</strong> <span class="mono">${url}</span>${
          modelWarn ? `<p class="report-live-warn">O modelo <code>${model}</code> não aparece na lista <code>/models</code>; ajuste <code>LLM_MODEL</code> no .env.</p>` : ''
        }<p class="report-live-next"><a href="index.html">Voltar ao Início</a> e reenvie o PDF para obter análise com IA.</p>`;
      } else {
        live.classList.add('report-llm-live-bad');
        const err = esc(`${p.error_type || ''} ${String(p.error || '').slice(0, 220)}`.trim());
        const tip = p.hint_pt ? `<p class="report-hint-action">${esc(String(p.hint_pt))}</p>` : '';
        live.innerHTML = `<strong>Servidor LLM inacessível</strong> (verificação em tempo real). <span class="mono">${err}</span>${tip}`;
      }
    })
    .catch(() => {
      live.classList.add('report-llm-live-bad');
      live.textContent = 'Não foi possível obter GET /health/llm. Confirme se o backend está em execução.';
    });
}

function renderGroupedAccordion(gi) {
  if (!gi || typeof gi !== 'object' || Array.isArray(gi)) return '';
  const cats = Object.entries(gi);
  if (!cats.length) return '';
  return cats.map(([cat, obj], idx) => {
    let inner = '';
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      inner = Object.entries(obj).map(([k, v]) => {
        const val = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v);
        return `<div class="report-kv"><span class="report-k">${esc(k)}</span><span class="report-v">${esc(val)}</span></div>`;
      }).join('');
    } else {
      inner = `<pre class="report-pre">${esc(JSON.stringify(obj, null, 2))}</pre>`;
    }
    return `<details class="report-acc" ${idx === 0 ? 'open' : ''}>
      <summary>${esc(cat)}</summary>
      <div class="report-acc-body">${inner}</div>
    </details>`;
  }).join('');
}

function renderStructuredCards(data) {
  const ext = data.extracted_data || {};
  let html = '';

  const name = ext.personal_info?.name || ext.student_name || ext.account_holder || ext.patient_name;
  if (name) html += `<div class="report-mini"><span class="lbl">Identificação</span><span class="val">${esc(name)}</span></div>`;

  if (ext.cnpjs?.length) {
    html += `<div class="report-mini"><span class="lbl">CNPJ</span><span class="val">${ext.cnpjs.map(esc).join(', ')}</span></div>`;
  }
  const moneyList = monetaryValues(ext);
  if (moneyList.length) {
    html += `<div class="report-mini"><span class="lbl">Valores</span><span class="val">${moneyList.slice(0, 8).map((v) => esc(String(v))).join(' · ')}</span></div>`;
  }
  const datesRaw = ext.dates_found || ext.dates || ext.dates_mentioned;
  const dates = datesRaw?.length ? uniqueDates(datesRaw) : [];
  if (dates.length) {
    html += `<div class="report-tags"><span class="lbl">Datas</span>${dates.slice(0, 20).map((d) => `<span class="tag">${esc(d)}</span>`).join('')}</div>`;
  }
  return html;
}

function renderDocumentProfile(data) {
  const profileNode = document.getElementById('reportProfile');
  if (!profileNode) return;
  const profile = data.document_profile || {};
  const type = String(profile.type || data.document_type_label || data.document_type || '').trim();
  const domain = String(profile.domain || '').trim();
  const subtype = String(profile.subtype || '').trim();
  const openSet = data.document_type_open_set === true;
  const reason = String(data.document_type_reason || '').trim();

  const chips = [];
  if (domain) chips.push(`<span class="profile-chip">${esc(domain)}</span>`);
  if (subtype && subtype !== type) chips.push(`<span class="profile-chip">${esc(subtype)}</span>`);
  if (type) chips.push(`<span class="profile-chip profile-chip-main">${esc(type)}</span>`);

  let explain = '';
  if (openSet) {
    explain = `<p class="report-profile-note">Classificação aberta ativa: o sistema evitou forçar tipo quando o sinal estava fraco (${esc(reason || 'open-set')}).</p>`;
  }
  profileNode.innerHTML = `
    <div class="report-profile-row">
      ${chips.length ? chips.join('') : '<span class="profile-chip">Tipo em análise</span>'}
    </div>
    ${explain}
  `;
}

function renderReport(data) {
  lastResponse = data;
  const ext = data.extracted_data || {};
  const cov = data.llm_coverage || {};

  const hint = document.getElementById('reportLlmHint');
  const live = document.getElementById('reportLlmLive');
  if (live) {
    live.style.display = 'none';
    live.innerHTML = '';
    live.className = 'glass-panel report-llm-live';
  }
  if (hint) {
    if (data.analysis_method !== 'ai') {
      hint.style.display = 'block';
      if (cov.error || cov.strategy === 'error') {
        const msg = cov.error ? String(cov.error).slice(0, 280) : 'Modelo indisponível.';
        const tip = cov.hint_pt ? `<p class="report-hint-action">${esc(String(cov.hint_pt))}</p>` : '';
        hint.innerHTML = `<strong>Análise sem IA nesta execução.</strong> O backend não conseguiu concluir a chamada ao LLM. O resultado abaixo usa leitura automática do texto. <span class="mono" style="display:block;margin-top:8px;font-size:0.78rem;opacity:0.9">${esc(msg)}</span>${tip}<p style="margin-top:12px;font-size:0.85rem">Consulte o painel seguinte (estado <em>atual</em> do servidor) e o README (<code>LLM_API_BASE</code>, <code>LLM_MODEL</code>).</p>`;
      } else {
        hint.innerHTML = '<p><strong>Análise heurística.</strong> O LLM não devolveu JSON utilizável (servidor parado, timeout ou resposta inválida). O painel abaixo mostra o estado <em>atual</em> do servidor.</p>';
      }
      refreshLlmLiveStrip();
    } else {
      hint.style.display = 'none';
      hint.innerHTML = '';
    }
  }

  if (hint && Array.isArray(data.quality_warnings) && data.quality_warnings.length) {
    hint.style.display = 'block';
    const warnText = data.quality_warnings.map((w) => `<li>${esc(String(w))}</li>`).join('');
    const existing = hint.innerHTML || '';
    hint.innerHTML = `${existing}${existing ? '' : '<strong>Atenção na qualidade de leitura.</strong>'}<ul class="report-ul">${warnText}</ul>`;
  }

  const title = document.getElementById('reportTitle');
  if (title) title.textContent = data.filename || 'Documento';

  const sub = document.getElementById('reportSubtitle');
  if (sub) {
    const method = data.analysis_method === 'ai' ? 'Análise com modelo de linguagem (local)' : 'Leitura automática do texto (fallback)';
    sub.textContent = `${data.document_type_label || ''} · ${method}`;
  }

  const badges = document.getElementById('reportBadges');
  if (badges) {
    const ai = data.analysis_method === 'ai';
    badges.innerHTML = `
      <span class="badge-pill ${ai ? 'badge-ai' : 'badge-fb'}">${ai ? 'IA' : 'Regex / heurística'}</span>
      <span class="badge-pill">${esc(String(data.pages ?? '—'))} pág.</span>
      <span class="badge-pill">${data.text_length != null ? (data.text_length / 1000).toFixed(1) + 'k chars' : '—'}</span>
      <span class="badge-pill">Conf. ${data.confidence ?? '—'}%</span>
      ${cov.strategy ? `<span class="badge-pill mono">${esc(LLM_STRATEGY_LABELS[cov.strategy] || cov.strategy)}</span>` : ''}
    `;
  }
  renderDocumentProfile(data);

  const purpose = document.getElementById('reportPurpose');
  if (purpose) {
    purpose.innerHTML = ext.document_purpose
      ? `<p>${esc(String(ext.document_purpose).trim())}</p>`
      : '<p class="muted">Propósito não extraído nesta execução.</p>';
  }

  const summary = document.getElementById('reportSummary');
  if (summary) {
    const t = (ext.detailed_summary || ext.summary_preview || '').trim();
    summary.innerHTML = t ? `<p>${esc(t)}</p>` : '<p class="muted">Resumo não disponível.</p>';
  }

  const grouped = document.getElementById('reportGrouped');
  if (grouped) {
    const acc = renderGroupedAccordion(ext.grouped_info);
    grouped.innerHTML = acc || '<p class="muted">Nenhum agrupamento estruturado retornado pelo modelo.</p>';
  }

  const findings = document.getElementById('reportFindings');
  if (findings) {
    if (ext.key_findings?.length) {
      findings.innerHTML = `<ul class="report-ul">${ext.key_findings.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>`;
    } else {
      findings.innerHTML = '<p class="muted">Nenhum achado em lista.</p>';
    }
  }

  const rec = document.getElementById('reportRecs');
  if (rec) {
    if (ext.recommendations?.length) {
      rec.innerHTML = `<ul class="report-ul">${ext.recommendations.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`;
    } else {
      rec.innerHTML = '<p class="muted">Sem recomendações.</p>';
    }
  }

  const extra = document.getElementById('reportExtra');
  if (extra) extra.innerHTML = renderStructuredCards(data) || '<p class="muted">Sem campos adicionais destacados.</p>';

  const meta = document.getElementById('reportMeta');
  if (meta) {
    const q = data.extraction_quality || {};
    const density = q.avg_chars_per_page != null ? ` · Extração: ~${q.avg_chars_per_page} chars/pág` : '';
    meta.textContent = `Tempo: ${data.processing_time_sec ?? '—'}s · Provedor: ${cov.provider || '—'} · Estratégia: ${cov.strategy || '—'}${density}`;
  }
}

function copyJSON(evt) {
  if (!lastResponse) return;
  navigator.clipboard.writeText(JSON.stringify(lastResponse, null, 2));
  const btn = (evt && evt.currentTarget) || document.querySelector('.btn-action.primary');
  if (!btn) return;
  const original = btn.textContent;
  btn.textContent = 'Copiado';
  setTimeout(() => { btn.textContent = original; }, 2000);
}

function downloadJSON() {
  if (!lastResponse) return;
  const blob = new Blob([JSON.stringify(lastResponse, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `analise-${lastResponse.filename || 'pdf'}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function initReportPage() {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  const empty = document.getElementById('reportEmpty');
  const content = document.getElementById('reportContent');
  if (!raw) {
    if (empty) empty.style.display = 'block';
    if (content) content.style.display = 'none';
    return;
  }
  try {
    const data = JSON.parse(raw);
    if (empty) empty.style.display = 'none';
    if (content) content.style.display = 'block';
    renderReport(data);
  } catch (e) {
    console.error(e);
    if (empty) {
      empty.style.display = 'block';
      empty.querySelector('p').textContent = 'Não foi possível ler o relatório salvo. Faça uma nova análise na página inicial.';
    }
    if (content) content.style.display = 'none';
  }
}

document.addEventListener('DOMContentLoaded', initReportPage);

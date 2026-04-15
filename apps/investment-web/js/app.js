/**
 * JERA FX Investment Mode — premium analyst workspace.
 */

import { api } from './api.js';
import { C, fmtBRL, fmtNum, fmtPct, fmtDate, fmtDateTime, lineChart, gaugeChart, waterfallHTML, fanChart, bandChart } from './charts.js';

function $(id) { return document.getElementById(id); }
function showError(el, msg) { if (typeof el === 'string') el = $(el); if (el) el.innerHTML = `<div class="status-msg error">${msg}</div>`; }
function showLoading(el) { if (typeof el === 'string') el = $(el); if (el) el.innerHTML = '<div class="status-msg loading">Carregando dados...</div>'; }
function badge(status) {
  const m = { scored: 'scored', degraded: 'degraded', 'missing-drivers': 'missing', available: 'scored', missing: 'missing' };
  return `<span class="badge badge-${m[status]||'missing'}">${status}</span>`;
}

/* ── Navigation ────────────────────────────────────────── */

let activeSection = 'dashboard';

function navigate(section) {
  activeSection = section;
  document.querySelectorAll('.section-panel').forEach(p => p.classList.remove('active'));
  const panel = $(`panel-${section}`);
  if (panel) panel.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.section === section);
  });
}

/* ── Dashboard ─────────────────────────────────────────── */

async function renderDashboard() {
  showLoading('dashboard-content');
  const [ov, sig, sc] = await Promise.all([api.overview(), api.tacticalSignal(), api.scenarios()]);

  let html = '<div class="kpi-row">';

  if (ov.ok) {
    html += `
      <div class="kpi-tile"><div class="label">PTAX Spot</div><div class="value">${fmtBRL(ov.data.spot?.value)}</div><div class="delta">${fmtDate(ov.data.spot?.observation_date)}</div></div>
      <div class="kpi-tile"><div class="label">REER Broad</div><div class="value">${fmtNum(ov.data.reer?.broad?.canonical?.value)}</div><div class="delta">p${fmtNum(ov.data.reer?.broad?.distribution?.percentile_rank,0)}</div></div>
      <div class="kpi-tile"><div class="label">REER Narrow</div><div class="value">${fmtNum(ov.data.reer?.narrow?.canonical?.value)}</div><div class="delta">p${fmtNum(ov.data.reer?.narrow?.distribution?.percentile_rank,0)}</div></div>
    `;
  }

  if (sig.ok) {
    const sc_val = sig.data.score;
    const col = sc_val == null ? C.muted : sc_val > 10 ? C.red : sc_val < -10 ? C.green : C.gold;
    html += `<div class="kpi-tile"><div class="label">Sinal Tatico</div><div class="value" style="color:${col}">${sc_val != null ? fmtNum(sc_val, 1) : '—'}</div><div class="delta">${badge(sig.data.status)}</div></div>`;
  }

  if (sc.ok) {
    const exp1y = sc.data.expected_path?.find(p => p.horizon_years === 1);
    html += `<div class="kpi-tile"><div class="label">Esperado 1A</div><div class="value">${fmtBRL(exp1y?.expected_fair_value)}</div><div class="delta">${sc.data.scenario_count} cenarios</div></div>`;
  }

  html += '</div>';

  // Signal gauge + contributions
  if (sig.ok) {
    html += `<div class="grid-2">
      <div class="card"><div class="card-header"><h3>Score Tatico</h3><div class="tag">${sig.data.methodology?.version || ''}</div></div>
        <div class="gauge-center">${gaugeChart(sig.data.score, sig.data.regime)}</div>
      </div>
      <div class="card"><div class="card-header"><h3>Contribuicoes</h3><div class="tag">por driver</div></div>
        ${waterfallHTML(sig.data.driver_contributions || [])}
      </div>
    </div>`;
  }

  // Fan chart
  if (sc.ok) {
    html += `<div class="card"><div class="card-header"><h3>Fan Chart — Cenarios</h3><div class="tag">${sc.data.methodology_version}</div></div>
      <div class="chart-wrap">${fanChart(sc.data.fan_chart, sc.data.scenarios)}</div>
    </div>`;
  }

  if (ov.ok) {
    html += `<div class="updated">Snapshot: ${fmtDateTime(ov.data.last_updated?.snapshot_created_at)}</div>`;
  }

  $('dashboard-content').innerHTML = html;
}

/* ── Variations ────────────────────────────────────────── */

async function renderVariations() {
  showLoading('variations-content');
  const { ok, data, error } = await api.driverVariations();
  if (!ok) return showError('variations-content', `Indisponivel: ${error}`);

  const rows = (data.variations || []).map(v => {
    const cls = v.change_percent > 0 ? 'pos' : v.change_percent < 0 ? 'neg' : '';
    return `<tr>
      <td>${v.label}</td>
      <td><span class="badge badge-${v.status === 'available' ? 'scored' : 'missing'}">${v.status}</span></td>
      <td class="num">${fmtNum(v.current_value, 2)}</td>
      <td class="num">${fmtNum(v.value_12m_ago, 2)}</td>
      <td class="num ${cls}">${fmtNum(v.change_absolute, 2)}</td>
      <td class="num ${cls}">${fmtPct(v.change_percent)}</td>
    </tr>`;
  }).join('');

  $('variations-content').innerHTML = `
    <div class="card"><div class="card-header"><h3>Variacoes 12 Meses</h3><div class="tag">todos os drivers</div></div>
      <table class="data-table">
        <thead><tr><th>Driver</th><th>Status</th><th>Atual</th><th>12m atras</th><th>Delta</th><th>Variacao</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="updated">${fmtDateTime(data.snapshot_created_at)}</div>
    </div>`;
}

/* ── Regressions ───────────────────────────────────────── */

async function renderRegressions() {
  showLoading('regressions-content');
  const { ok, data, error } = await api.rollingRegression();
  if (!ok) return showError('regressions-content', `Indisponivel: ${error}`);

  let html = '<div class="kpi-row">';
  for (const w of (data.windows || [])) {
    const col = w.r_squared > 0.6 ? C.green : w.r_squared > 0.3 ? C.gold : C.red;
    html += `<div class="kpi-tile"><div class="label">${w.window_label} (${w.n_obs} obs)</div><div class="value" style="color:${col}">R² ${fmtNum(w.r_squared, 3)}</div><div class="delta">adj ${fmtNum(w.adj_r_squared, 3)}</div></div>`;
  }
  html += '</div>';

  // Per-window details
  for (const w of (data.windows || [])) {
    if (!w.factor_contributions?.length) continue;
    html += `<div class="card"><div class="card-header"><h3>Janela ${w.window_label}</h3><div class="tag">R² = ${fmtNum(w.r_squared, 3)}</div></div>
      <div class="grid-2">
        <div>
          <h4 style="font-size:12px;color:var(--text-2);margin-bottom:8px;">Betas</h4>
          <table class="data-table">
            <thead><tr><th>Driver</th><th class="num">Beta</th><th class="num">Delta</th><th class="num">Contribuicao</th></tr></thead>
            <tbody>${w.factor_contributions.map(c => `<tr>
              <td>${c.driver_key.replace(/_/g,' ')}</td>
              <td class="num">${fmtNum(c.beta, 4)}</td>
              <td class="num">${fmtNum(c.delta_driver, 2)}</td>
              <td class="num ${c.contribution > 0 ? 'pos' : 'neg'}">${fmtNum(c.contribution, 4)}</td>
            </tr>`).join('')}
            <tr style="border-top:2px solid var(--border)"><td><strong>Residual</strong></td><td></td><td></td><td class="num"><strong>${fmtNum(w.residual, 4)}</strong></td></tr>
            </tbody>
          </table>
        </div>
        <div>
          <h4 style="font-size:12px;color:var(--text-2);margin-bottom:8px;">Waterfall</h4>
          ${waterfallHTML(w.factor_contributions)}
        </div>
      </div>
      <div class="updated">PTAX: ${fmtBRL(w.dependent_first)} → ${fmtBRL(w.dependent_latest)} (move total: ${fmtBRL(w.total_move)})</div>
    </div>`;
  }

  $('regressions-content').innerHTML = html;
}

/* ── Scenarios ─────────────────────────────────────────── */

async function renderScenarios() {
  showLoading('scenarios-content');
  const { ok, data, error } = await api.scenarios();
  if (!ok) return showError('scenarios-content', `Indisponivel: ${error}`);

  const colorMap = { green: C.green, gold: C.gold, red: C.red, orange: C.orange };
  const cards = (data.scenarios || []).map(sc => {
    const col = colorMap[sc.color] || C.muted;
    const terminal = sc.horizons?.[sc.horizons.length-1]?.fair_value;
    return `<div class="scenario-card" style="border-left:3px solid ${col}">
      <div class="prob">${fmtNum(sc.probability*100,0)}%</div>
      <h4 style="color:${col}">${sc.label}</h4>
      <p>${sc.narrative}</p>
      <div class="path" style="color:${col}">${fmtBRL(terminal)}</div>
    </div>`;
  }).join('');

  const expected = (data.expected_path || []).map(ep =>
    `<div class="kpi-tile"><div class="label">${ep.horizon_years}A esperado</div><div class="value">${fmtBRL(ep.expected_fair_value)}</div></div>`
  ).join('');

  $('scenarios-content').innerHTML = `
    <div class="scenario-grid">${cards}</div>
    <div class="card"><div class="card-header"><h3>Fan Chart</h3><div class="tag">${data.methodology_version}</div></div>
      <div class="chart-wrap">${fanChart(data.fan_chart, data.scenarios)}</div>
    </div>
    <div class="kpi-row">${expected}</div>
    <div class="updated">Ancora: ${fmtBRL(data.anchor_value)} (${data.anchor_source}) | Spot: ${fmtBRL(data.spot_value)}</div>
  `;
}

/* ── Freshness ─────────────────────────────────────────── */

async function renderFreshness() {
  showLoading('freshness-content');
  const [sf, df] = await Promise.all([api.sourceFreshness(), api.driverFreshness()]);

  let html = '';

  if (sf.ok) {
    const rows = (sf.data.sources || []).map(s => `<tr>
      <td>${s.source_key}</td>
      <td class="num">${fmtDate(s.latest_observation_date)}</td>
      <td class="num">${fmtDate(s.latest_reference_month_end)}</td>
      <td class="num">${fmtDateTime(s.latest_ingested_at)}</td>
    </tr>`).join('');
    html += `<div class="card"><div class="card-header"><h3>Fontes</h3><div class="tag">source freshness</div></div>
      <table class="data-table"><thead><tr><th>Fonte</th><th>Ultima obs.</th><th>Ref. mensal</th><th>Ingestao</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="updated">${fmtDateTime(sf.data.snapshot_created_at)}</div>
    </div>`;
  }

  if (df.ok) {
    const rows = (df.data.drivers || []).map(d => `<tr>
      <td>${d.label}</td>
      <td><span class="badge badge-${d.status === 'available' ? 'scored' : 'missing'}">${d.status}</span></td>
      <td class="num">${fmtDate(d.latest_observation_date)}</td>
      <td class="num">${fmtDateTime(d.latest_ingested_at)}</td>
      <td>${d.source_mode || '—'}</td>
    </tr>`).join('');
    html += `<div class="card"><div class="card-header"><h3>Drivers Taticos</h3><div class="tag">driver freshness</div></div>
      <table class="data-table"><thead><tr><th>Driver</th><th>Status</th><th>Ultima obs.</th><th>Ingestao</th><th>Modo</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="updated">${fmtDateTime(df.data.snapshot_created_at)}</div>
    </div>`;
  }

  if (!html) html = '<div class="status-msg error">Dados indisponiveis</div>';
  $('freshness-content').innerHTML = html;
}

/* ── Init ──────────────────────────────────────────────── */

const SECTION_LOADERS = {
  dashboard: renderDashboard,
  variations: renderVariations,
  regressions: renderRegressions,
  scenarios: renderScenarios,
  freshness: renderFreshness,
};

async function init() {
  // Wire navigation
  document.querySelectorAll('.nav-item[data-section]').forEach(el => {
    el.addEventListener('click', async (e) => {
      e.preventDefault();
      const section = el.dataset.section;
      navigate(section);
      const loader = SECTION_LOADERS[section];
      if (loader) await loader();
    });
  });

  navigate('dashboard');
  await renderDashboard();
}

document.addEventListener('DOMContentLoaded', init);

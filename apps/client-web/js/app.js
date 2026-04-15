/**
 * JERA FX Client Mode — page orchestration.
 *
 * Fetches all data from the API and renders each section.
 * Every displayed number comes from the API. Zero hardcode.
 */

import { api } from './api.js';
import {
  fmtBRL, fmtNum, fmtDate, fmtDateTime,
  lineChart, hBarChart, gaugeChart, fanChart, bandChart, COLORS,
} from './charts.js';

/* ── Helpers ───────────────────────────────────────────── */

function $(id) { return document.getElementById(id); }

function showError(el, msg) {
  if (typeof el === 'string') el = $(el);
  if (el) el.innerHTML = `<div class="status-msg error">${msg}</div>`;
}

function showLoading(el) {
  if (typeof el === 'string') el = $(el);
  if (el) el.innerHTML = '<div class="status-msg loading">Carregando...</div>';
}

function badge(status) {
  const map = {
    'scored': ['scored', 'Score publicado'],
    'degraded': ['degraded', 'Degradado'],
    'missing-drivers': ['missing', 'Drivers faltantes'],
    'available': ['available', 'Disponivel'],
    'missing': ['missing', 'Ausente'],
  };
  const [cls, label] = map[status] || ['unknown', status];
  return `<span class="badge badge-${cls}">${label}</span>`;
}

/* ── Section: Overview ─────────────────────────────────── */

async function renderOverview() {
  showLoading('overview-content');
  const { ok, data, error } = await api.overview();
  if (!ok) return showError('overview-content', `Dados indisponiveis: ${error}`);

  $('overview-content').innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">PTAX Spot (venda)</div>
        <div class="kpi-value">${fmtBRL(data.spot?.value)}</div>
        <div class="kpi-sub">${fmtDate(data.spot?.observation_date)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">REER Broad (canonical)</div>
        <div class="kpi-value">${fmtNum(data.reer?.broad?.canonical?.value)}</div>
        <div class="kpi-sub">Percentil: ${fmtNum(data.reer?.broad?.distribution?.percentile_rank, 0)}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">REER Narrow (canonical)</div>
        <div class="kpi-value">${fmtNum(data.reer?.narrow?.canonical?.value)}</div>
        <div class="kpi-sub">Percentil: ${fmtNum(data.reer?.narrow?.distribution?.percentile_rank, 0)}%</div>
      </div>
    </div>
    <div class="updated">Atualizado: ${fmtDateTime(data.last_updated?.snapshot_created_at)}</div>
  `;
}

/* ── Section: REER Bands ───────────────────────────────── */

async function renderReerBands() {
  showLoading('reer-bands-content');
  const { ok, data, error } = await api.reerBands();
  if (!ok) return showError('reer-bands-content', `Dados indisponiveis: ${error}`);

  const broadDist = data.broad?.distribution;
  const narrowDist = data.narrow?.distribution;
  const broadCurrent = data.broad?.canonical?.value;
  const narrowCurrent = data.narrow?.canonical?.value;

  $('reer-bands-content').innerHTML = `
    <div class="band-section">
      <h4>REER Broad (120 paises)</h4>
      <div class="band-chart">${bandChart(broadCurrent, broadDist, { width: 600, label: 'Broad' })}</div>
      <div class="band-meta">Atual: ${fmtNum(broadCurrent)} | Mediana (p50): ${fmtNum(broadDist?.p50)} | Ref: ${fmtDate(data.broad?.reference_month_end)}</div>
    </div>
    <div class="band-section">
      <h4>REER Narrow (51 paises)</h4>
      <div class="band-chart">${bandChart(narrowCurrent, narrowDist, { width: 600, label: 'Narrow' })}</div>
      <div class="band-meta">Atual: ${fmtNum(narrowCurrent)} | Mediana (p50): ${fmtNum(narrowDist?.p50)} | Ref: ${fmtDate(data.narrow?.reference_month_end)}</div>
    </div>
    <div class="updated">Escala: ${data.client_default_scale_policy || '—'}</div>
  `;
}

/* ── Section: PTAX History ─────────────────────────────── */

async function renderPtaxHistory() {
  showLoading('ptax-history-content');
  const { ok, data, error } = await api.ptaxHistory();
  if (!ok) return showError('ptax-history-content', `Dados indisponiveis: ${error}`);

  const sellSeries = data.series?.find(s => s.series_key === 'ptax_usd_brl_sell');
  if (!sellSeries || !sellSeries.points?.length) {
    return showError('ptax-history-content', 'Historico PTAX nao disponivel');
  }

  const points = sellSeries.points.map(p => ({
    value: p.value,
    label: p.reference_month_end?.slice(0, 7) || '',
  }));

  $('ptax-history-content').innerHTML = `
    <div class="chart-container">${lineChart(points, { color: COLORS.blue, valuePrefix: 'R$ ' })}</div>
    <div class="updated">Atualizado: ${fmtDateTime(data.snapshot_created_at)}</div>
  `;
}

/* ── Section: Tactical Signal ──────────────────────────── */

async function renderTacticalSignal() {
  showLoading('tactical-signal-content');
  const { ok, data, error } = await api.tacticalSignal();
  if (!ok) return showError('tactical-signal-content', `Dados indisponiveis: ${error}`);

  const score = data.score;
  const regime = data.regime;
  const status = data.status;

  // Driver contributions bar chart
  const contributions = (data.driver_contributions || []).map(c => ({
    label: c.driver_key.replace(/_/g, ' '),
    value: c.weighted_contribution,
  }));

  const degradedHtml = data.degraded_reasons?.length
    ? `<div class="degraded-reasons"><strong>Motivo:</strong> ${data.degraded_reasons.map(r => `<div class="reason">${r}</div>`).join('')}</div>`
    : '';

  $('tactical-signal-content').innerHTML = `
    <div class="signal-layout">
      <div class="signal-gauge">
        ${gaugeChart(score, regime)}
        <div class="signal-status">${badge(status)}</div>
      </div>
      <div class="signal-detail">
        <h4>Contribuicoes por driver</h4>
        ${contributions.length ? hBarChart(contributions) : '<p class="no-data">Sem contribuicoes disponiveis</p>'}
        ${degradedHtml}
      </div>
    </div>
    <div class="updated">Metodologia: ${data.methodology?.version || '—'} | Atualizado: ${fmtDateTime(data.snapshot_created_at)}</div>
  `;
}

/* ── Section: Scenarios ────────────────────────────────── */

async function renderScenarios() {
  showLoading('scenarios-content');
  const { ok, data, error } = await api.scenarios();
  if (!ok) return showError('scenarios-content', `Dados indisponiveis: ${error}`);

  const scenarioCards = (data.scenarios || []).map(sc => {
    const colorMap = { green: COLORS.green, gold: COLORS.gold, red: COLORS.red, orange: COLORS.orange };
    const col = colorMap[sc.color] || COLORS.muted;
    const terminal = sc.horizons?.[sc.horizons.length - 1]?.fair_value;
    return `
      <div class="scenario-card" style="border-left: 3px solid ${col}">
        <div class="scenario-prob">${fmtNum(sc.probability * 100, 0)}%</div>
        <h4 style="color:${col}">${sc.label}</h4>
        <p>${sc.narrative}</p>
        <div class="scenario-path" style="color:${col}">${fmtBRL(terminal)}</div>
      </div>
    `;
  }).join('');

  const expectedHtml = (data.expected_path || []).map(ep =>
    `<div class="kpi-card compact"><div class="kpi-label">${ep.horizon_years}A esperado</div><div class="kpi-value">${fmtBRL(ep.expected_fair_value)}</div></div>`
  ).join('');

  $('scenarios-content').innerHTML = `
    <div class="scenario-grid">${scenarioCards}</div>
    <h4>Fan chart</h4>
    <div class="chart-container">${fanChart(data.fan_chart, data.scenarios)}</div>
    <div class="kpi-grid compact-grid">${expectedHtml}</div>
    <div class="updated">Ancora: ${fmtBRL(data.anchor_value)} (${data.anchor_source || '—'}) | Spot: ${fmtBRL(data.spot_value)} | ${data.methodology_version}</div>
  `;
}

/* ── Section: Freshness ────────────────────────────────── */

async function renderFreshness() {
  showLoading('freshness-content');
  const { ok, data, error } = await api.sourceFreshness();
  if (!ok) return showError('freshness-content', `Dados indisponiveis: ${error}`);

  const rows = (data.sources || []).map(s => `
    <tr>
      <td>${s.source_key}</td>
      <td>${fmtDate(s.latest_observation_date)}</td>
      <td>${fmtDate(s.latest_reference_month_end)}</td>
      <td>${fmtDateTime(s.latest_ingested_at)}</td>
    </tr>
  `).join('');

  $('freshness-content').innerHTML = `
    <table class="data-table">
      <thead><tr><th>Fonte</th><th>Ultima obs.</th><th>Ref. mensal</th><th>Ingestao</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="updated">Atualizado: ${fmtDateTime(data.snapshot_created_at)}</div>
  `;
}

/* ── Init ──────────────────────────────────────────────── */

async function init() {
  // Fire all sections in parallel.
  await Promise.allSettled([
    renderOverview(),
    renderReerBands(),
    renderPtaxHistory(),
    renderTacticalSignal(),
    renderScenarios(),
    renderFreshness(),
  ]);
}

document.addEventListener('DOMContentLoaded', init);

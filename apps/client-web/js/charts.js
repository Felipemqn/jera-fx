/**
 * JERA FX Charts — lightweight SVG chart generators.
 *
 * All charts are pure SVG strings injected via innerHTML.
 * No external dependencies.
 */

const COLORS = {
  blue:   '#5B9BD5',
  gold:   '#E6A817',
  green:  '#4CAF50',
  red:    '#E53935',
  orange: '#FF9800',
  muted:  '#8899AA',
  grid:   '#2A3040',
  bg:     '#1A1F2E',
  text:   '#E0E8F0',
};

/* ── Helpers ───────────────────────────────────────────── */

function fmtBRL(v) {
  if (v == null) return '—';
  return 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtNum(v, d = 2) {
  if (v == null) return '—';
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/* ── Line Chart ────────────────────────────────────────── */

function lineChart(points, { width = 700, height = 250, color = COLORS.blue, labelX = '', labelY = '', valuePrefix = '' } = {}) {
  if (!points || points.length < 2) return '<p class="no-data">Dados insuficientes para o grafico</p>';

  const pad = { t: 20, r: 20, b: 40, l: 60 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;

  const vals = points.map(p => p.value);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const rangeV = maxV - minV || 1;

  const sx = (i) => pad.l + (i / (points.length - 1)) * w;
  const sy = (v) => pad.t + h - ((v - minV) / rangeV) * h;

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${sx(i).toFixed(1)},${sy(p.value).toFixed(1)}`).join(' ');

  // Y-axis ticks (5 ticks)
  const yTicks = Array.from({ length: 5 }, (_, i) => minV + (rangeV * i) / 4);

  // X-axis labels (first, mid, last)
  const xLabels = [0, Math.floor(points.length / 2), points.length - 1].map(i => ({
    x: sx(i),
    label: points[i].label || ''
  }));

  return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
    ${yTicks.map(v => `
      <line x1="${pad.l}" y1="${sy(v)}" x2="${width - pad.r}" y2="${sy(v)}" stroke="${COLORS.grid}" stroke-width="0.5"/>
      <text x="${pad.l - 8}" y="${sy(v) + 4}" text-anchor="end" fill="${COLORS.muted}" font-size="11">${valuePrefix}${fmtNum(v)}</text>
    `).join('')}
    <path d="${pathD}" fill="none" stroke="${color}" stroke-width="2"/>
    ${xLabels.map(l => `
      <text x="${l.x}" y="${height - 8}" text-anchor="middle" fill="${COLORS.muted}" font-size="11">${l.label}</text>
    `).join('')}
  </svg>`;
}

/* ── Horizontal Bar (contributions) ────────────────────── */

function hBarChart(items, { width = 600, barHeight = 28, maxLabelWidth = 140 } = {}) {
  if (!items || items.length === 0) return '<p class="no-data">Sem dados</p>';

  const maxAbs = Math.max(...items.map(d => Math.abs(d.value)), 0.01);
  const totalHeight = items.length * (barHeight + 8) + 20;
  const barArea = width - maxLabelWidth - 40;
  const center = maxLabelWidth + barArea / 2;

  return `<svg viewBox="0 0 ${width} ${totalHeight}" class="chart-svg">
    <line x1="${center}" y1="0" x2="${center}" y2="${totalHeight}" stroke="${COLORS.grid}" stroke-width="1"/>
    ${items.map((d, i) => {
      const y = i * (barHeight + 8) + 10;
      const bw = (Math.abs(d.value) / maxAbs) * (barArea / 2);
      const bx = d.value >= 0 ? center : center - bw;
      const col = d.value >= 0 ? COLORS.red : COLORS.green;
      return `
        <text x="${maxLabelWidth - 8}" y="${y + barHeight / 2 + 4}" text-anchor="end" fill="${COLORS.text}" font-size="12">${d.label}</text>
        <rect x="${bx}" y="${y}" width="${bw}" height="${barHeight}" fill="${col}" rx="3" opacity="0.85"/>
        <text x="${bx + (d.value >= 0 ? bw + 6 : -6)}" y="${y + barHeight / 2 + 4}" text-anchor="${d.value >= 0 ? 'start' : 'end'}" fill="${COLORS.text}" font-size="11">${fmtNum(d.value, 2)}</text>
      `;
    }).join('')}
  </svg>`;
}

/* ── Gauge (tactical score) ────────────────────────────── */

function gaugeChart(score, regime, { width = 300, height = 180 } = {}) {
  const cx = width / 2;
  const cy = height - 20;
  const r = Math.min(cx - 20, cy - 10);
  const startAngle = Math.PI;
  const endAngle = 0;

  if (score == null) {
    return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
      <path d="${arcPath(cx, cy, r, startAngle, endAngle)}" fill="none" stroke="${COLORS.grid}" stroke-width="16" stroke-linecap="round"/>
      <text x="${cx}" y="${cy - r / 2}" text-anchor="middle" fill="${COLORS.muted}" font-size="16">sem score</text>
      ${regime ? `<text x="${cx}" y="${cy - r / 2 + 22}" text-anchor="middle" fill="${COLORS.muted}" font-size="12">${regime}</text>` : ''}
    </svg>`;
  }

  const clamped = Math.max(-100, Math.min(100, score));
  const pct = (clamped + 100) / 200; // 0..1
  const needleAngle = Math.PI - pct * Math.PI;
  const nx = cx + Math.cos(needleAngle) * (r - 10);
  const ny = cy - Math.sin(needleAngle) * (r - 10);

  // Color segments
  const segments = [
    { from: 0, to: 0.2, color: COLORS.green },
    { from: 0.2, to: 0.4, color: '#81C784' },
    { from: 0.4, to: 0.6, color: COLORS.gold },
    { from: 0.6, to: 0.8, color: COLORS.orange },
    { from: 0.8, to: 1.0, color: COLORS.red },
  ];

  return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
    ${segments.map(s => {
      const a1 = Math.PI - s.from * Math.PI;
      const a2 = Math.PI - s.to * Math.PI;
      return `<path d="${arcPath(cx, cy, r, a1, a2)}" fill="none" stroke="${s.color}" stroke-width="16" stroke-linecap="butt" opacity="0.7"/>`;
    }).join('')}
    <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="${COLORS.text}" stroke-width="3" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="6" fill="${COLORS.text}"/>
    <text x="${cx}" y="${cy - r / 2 - 5}" text-anchor="middle" fill="${COLORS.text}" font-size="28" font-weight="700">${fmtNum(score, 1)}</text>
    <text x="${cx}" y="${cy - r / 2 + 18}" text-anchor="middle" fill="${COLORS.muted}" font-size="13">${regime || ''}</text>
    <text x="${cx - r}" y="${cy + 16}" text-anchor="middle" fill="${COLORS.muted}" font-size="10">-100</text>
    <text x="${cx + r}" y="${cy + 16}" text-anchor="middle" fill="${COLORS.muted}" font-size="10">+100</text>
  </svg>`;
}

function arcPath(cx, cy, r, startAngle, endAngle) {
  const x1 = cx + Math.cos(startAngle) * r;
  const y1 = cy - Math.sin(startAngle) * r;
  const x2 = cx + Math.cos(endAngle) * r;
  const y2 = cy - Math.sin(endAngle) * r;
  const large = Math.abs(startAngle - endAngle) > Math.PI ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
}

/* ── Fan Chart (scenarios) ─────────────────────────────── */

function fanChart(fanData, scenarios, { width = 700, height = 300 } = {}) {
  if (!fanData || fanData.length === 0) return '<p class="no-data">Sem dados de cenario</p>';

  const pad = { t: 20, r: 20, b: 50, l: 70 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;

  const allVals = fanData.flatMap(f => [f.min, f.max, f.expected]);
  const minV = Math.min(...allVals) * 0.95;
  const maxV = Math.max(...allVals) * 1.05;
  const rangeV = maxV - minV || 1;

  const sx = (i) => pad.l + (i / Math.max(fanData.length - 1, 1)) * w;
  const sy = (v) => pad.t + h - ((v - minV) / rangeV) * h;

  // Fan band (min to max area)
  const topLine = fanData.map((f, i) => `${sx(i)},${sy(f.max)}`).join(' ');
  const bottomLine = fanData.map((f, i) => `${sx(fanData.length - 1 - i)},${sy(fanData[fanData.length - 1 - i].min)}`).join(' ');
  const bandPath = `M ${topLine} L ${bottomLine} Z`;

  // Scenario lines
  const scenarioColors = { benign: COLORS.green, base: COLORS.gold, fiscal_stress: COLORS.red, superdollar: COLORS.orange };
  const scenarioLines = (scenarios || []).map(sc => {
    const pts = sc.horizons.map((hp, i) => `${i === 0 ? 'M' : 'L'}${sx(i)},${sy(hp.fair_value)}`).join(' ');
    return `<path d="${pts}" fill="none" stroke="${scenarioColors[sc.scenario_key] || COLORS.muted}" stroke-width="1.5" stroke-dasharray="4,3"/>`;
  }).join('');

  // Expected path (bold blue)
  const expectedPath = fanData.map((f, i) => `${i === 0 ? 'M' : 'L'}${sx(i)},${sy(f.expected)}`).join(' ');

  // Y ticks
  const yTicks = Array.from({ length: 5 }, (_, i) => minV + (rangeV * i) / 4);

  return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
    ${yTicks.map(v => `
      <line x1="${pad.l}" y1="${sy(v)}" x2="${width - pad.r}" y2="${sy(v)}" stroke="${COLORS.grid}" stroke-width="0.5"/>
      <text x="${pad.l - 8}" y="${sy(v) + 4}" text-anchor="end" fill="${COLORS.muted}" font-size="11">${fmtBRL(v)}</text>
    `).join('')}
    <polygon points="${topLine} ${bottomLine}" fill="${COLORS.blue}" opacity="0.12"/>
    ${scenarioLines}
    <path d="${expectedPath}" fill="none" stroke="${COLORS.blue}" stroke-width="2.5"/>
    ${fanData.map((f, i) => `
      <text x="${sx(i)}" y="${height - 10}" text-anchor="middle" fill="${COLORS.muted}" font-size="11">${f.horizon_years}A</text>
    `).join('')}
  </svg>`;
}

/* ── Percentile Band (REER) ────────────────────────────── */

function bandChart(current, distribution, { width = 500, height = 60, label = '' } = {}) {
  if (!distribution) return '<p class="no-data">Sem dados</p>';

  const pad = { l: 10, r: 10 };
  const bw = width - pad.l - pad.r;

  const { p10, p25, p50, p75, p90 } = distribution;
  const minV = p10 * 0.98;
  const maxV = p90 * 1.02;
  const range = maxV - minV || 1;

  const sx = (v) => pad.l + ((v - minV) / range) * bw;
  const cy = height / 2;
  const barH = 18;

  return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
    <rect x="${sx(p10)}" y="${cy - barH/2}" width="${sx(p90) - sx(p10)}" height="${barH}" fill="${COLORS.grid}" rx="4"/>
    <rect x="${sx(p25)}" y="${cy - barH/2}" width="${sx(p75) - sx(p25)}" height="${barH}" fill="${COLORS.blue}" rx="3" opacity="0.5"/>
    <line x1="${sx(p50)}" y1="${cy - barH/2 - 4}" x2="${sx(p50)}" y2="${cy + barH/2 + 4}" stroke="${COLORS.muted}" stroke-width="1.5"/>
    ${current != null ? `<circle cx="${sx(current)}" cy="${cy}" r="6" fill="${COLORS.gold}" stroke="${COLORS.bg}" stroke-width="2"/>` : ''}
    <text x="${sx(p10)}" y="${cy + barH/2 + 14}" text-anchor="middle" fill="${COLORS.muted}" font-size="10">p10: ${fmtNum(p10)}</text>
    <text x="${sx(p50)}" y="${cy - barH/2 - 8}" text-anchor="middle" fill="${COLORS.muted}" font-size="10">p50: ${fmtNum(p50)}</text>
    <text x="${sx(p90)}" y="${cy + barH/2 + 14}" text-anchor="middle" fill="${COLORS.muted}" font-size="10">p90: ${fmtNum(p90)}</text>
  </svg>`;
}

export { COLORS, fmtBRL, fmtNum, fmtDate, fmtDateTime, lineChart, hBarChart, gaugeChart, fanChart, bandChart };

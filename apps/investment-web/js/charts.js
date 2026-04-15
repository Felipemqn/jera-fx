/**
 * JERA FX Investment Charts — premium SVG generators.
 */

const C = {
  accent:  '#6C8EEF',
  accent2: '#8B5CF6',
  green:   '#10B981',
  red:     '#EF4444',
  gold:    '#F59E0B',
  orange:  '#F97316',
  cyan:    '#06B6D4',
  blue:    '#3B82F6',
  muted:   '#4A5060',
  grid:    'rgba(255,255,255,0.04)',
  text:    '#C4CAD4',
  text0:   '#F0F2F5',
};

function fmtBRL(v) {
  if (v == null) return '—';
  return 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtNum(v, d = 2) {
  if (v == null) return '—';
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
}

function fmtPct(v) {
  if (v == null) return '—';
  const sign = v > 0 ? '+' : '';
  return sign + fmtNum(v, 2) + '%';
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' });
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/* ── Line Chart (premium) ──────────────────────────────── */

function lineChart(points, { width = 700, height = 220, color = C.accent, showArea = true } = {}) {
  if (!points || points.length < 2) return '<div class="no-data">Dados insuficientes</div>';
  const pad = { t: 16, r: 16, b: 36, l: 56 };
  const w = width - pad.l - pad.r, h = height - pad.t - pad.b;
  const vals = points.map(p => p.value);
  const mn = Math.min(...vals), mx = Math.max(...vals), rng = mx - mn || 1;
  const sx = i => pad.l + (i / (points.length - 1)) * w;
  const sy = v => pad.t + h - ((v - mn) / rng) * h;

  const pathD = points.map((p, i) => `${i ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(p.value).toFixed(1)}`).join(' ');
  const areaD = pathD + ` L${sx(points.length-1)},${pad.t+h} L${sx(0)},${pad.t+h} Z`;

  const yTicks = Array.from({length: 4}, (_, i) => mn + rng * i / 3);
  const xIdx = [0, Math.floor(points.length/2), points.length-1];

  return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
    <defs>
      <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.15"/>
        <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${yTicks.map(v => `<line x1="${pad.l}" y1="${sy(v)}" x2="${width-pad.r}" y2="${sy(v)}" stroke="${C.grid}" stroke-width="0.5"/><text x="${pad.l-6}" y="${sy(v)+4}" text-anchor="end" fill="${C.muted}" font-size="10" font-family="var(--mono)">${fmtNum(v)}</text>`).join('')}
    ${showArea ? `<path d="${areaD}" fill="url(#areaGrad)"/>` : ''}
    <path d="${pathD}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${sx(points.length-1)}" cy="${sy(vals[vals.length-1])}" r="4" fill="${color}" stroke="${C.text0}" stroke-width="1.5"/>
    ${xIdx.map(i => `<text x="${sx(i)}" y="${height-6}" text-anchor="middle" fill="${C.muted}" font-size="10">${points[i].label||''}</text>`).join('')}
  </svg>`;
}

/* ── Gauge (premium) ───────────────────────────────────── */

function gaugeChart(score, regime, { width = 280, height = 160 } = {}) {
  const cx = width/2, cy = height - 16, r = Math.min(cx-16, cy-8);
  const segs = [
    {f:0, t:0.2, c:C.green}, {f:0.2, t:0.4, c:'#34D399'},
    {f:0.4, t:0.6, c:C.gold}, {f:0.6, t:0.8, c:C.orange}, {f:0.8, t:1, c:C.red}
  ];
  const arc = (a1,a2) => {
    const x1=cx+Math.cos(a1)*r, y1=cy-Math.sin(a1)*r;
    const x2=cx+Math.cos(a2)*r, y2=cy-Math.sin(a2)*r;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${Math.abs(a1-a2)>Math.PI?1:0} 1 ${x2} ${y2}`;
  };

  if (score == null) {
    return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
      <path d="${arc(Math.PI,0)}" fill="none" stroke="${C.grid}" stroke-width="14" stroke-linecap="round"/>
      <text x="${cx}" y="${cy-r/2}" text-anchor="middle" fill="${C.muted}" font-size="15" font-weight="600">sem score</text>
      ${regime ? `<text x="${cx}" y="${cy-r/2+20}" text-anchor="middle" fill="${C.muted}" font-size="11">${regime}</text>` : ''}
    </svg>`;
  }

  const pct = (Math.max(-100,Math.min(100,score))+100)/200;
  const na = Math.PI - pct*Math.PI;
  const nx = cx+Math.cos(na)*(r-8), ny = cy-Math.sin(na)*(r-8);

  return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
    ${segs.map(s => `<path d="${arc(Math.PI-s.f*Math.PI, Math.PI-s.t*Math.PI)}" fill="none" stroke="${s.c}" stroke-width="14" opacity="0.6"/>`).join('')}
    <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="${C.text0}" stroke-width="2.5" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="5" fill="${C.text0}"/>
    <text x="${cx}" y="${cy-r/2-4}" text-anchor="middle" fill="${C.text0}" font-size="28" font-weight="800">${fmtNum(score,1)}</text>
    <text x="${cx}" y="${cy-r/2+18}" text-anchor="middle" fill="${C.accent}" font-size="12" font-weight="600">${regime||''}</text>
  </svg>`;
}

/* ── Waterfall bars (factor contributions) ─────────────── */

function waterfallHTML(contributions) {
  if (!contributions?.length) return '<div class="no-data">Sem contribuicoes</div>';
  const maxAbs = Math.max(...contributions.map(c => Math.abs(c.contribution)), 0.01);
  return contributions.map(c => {
    const pct = Math.abs(c.contribution) / maxAbs * 100;
    const col = c.contribution >= 0 ? C.red : C.green;
    const dir = c.contribution >= 0 ? 'right' : 'left';
    const label = c.driver_key.replace(/_/g, ' ');
    return `<div class="waterfall-row">
      <div class="label">${label}</div>
      <div class="bar-wrap"><div class="bar" style="width:${pct}%; background:${col}; margin-${dir === 'left' ? 'left' : 'right'}:auto; float:${dir};"></div></div>
      <div class="val" style="color:${col}">${c.contribution >= 0 ? '+' : ''}${fmtNum(c.contribution, 4)}</div>
    </div>`;
  }).join('');
}

/* ── Fan Chart ─────────────────────────────────────────── */

function fanChart(fanData, scenarios, { width = 700, height = 280 } = {}) {
  if (!fanData?.length) return '<div class="no-data">Sem dados de cenario</div>';
  const pad = { t: 16, r: 16, b: 44, l: 64 };
  const w = width-pad.l-pad.r, h = height-pad.t-pad.b;
  const all = fanData.flatMap(f => [f.min, f.max]);
  const mn = Math.min(...all)*0.95, mx = Math.max(...all)*1.05, rng = mx-mn||1;
  const sx = i => pad.l + (i/Math.max(fanData.length-1,1))*w;
  const sy = v => pad.t + h - ((v-mn)/rng)*h;

  const top = fanData.map((f,i) => `${sx(i)},${sy(f.max)}`).join(' ');
  const bot = fanData.map((f,i) => `${sx(fanData.length-1-i)},${sy(fanData[fanData.length-1-i].min)}`).join(' ');
  const colMap = { benign: C.green, base: C.gold, fiscal_stress: C.red, superdollar: C.orange };
  const sLines = (scenarios||[]).map(sc => {
    const pts = sc.horizons.map((hp,i) => `${i?'L':'M'}${sx(i)},${sy(hp.fair_value)}`).join(' ');
    return `<path d="${pts}" fill="none" stroke="${colMap[sc.scenario_key]||C.muted}" stroke-width="1.5" stroke-dasharray="5,4" opacity="0.7"/>`;
  }).join('');
  const exp = fanData.map((f,i) => `${i?'L':'M'}${sx(i)},${sy(f.expected)}`).join(' ');
  const yTicks = Array.from({length:4},(_, i) => mn + rng*i/3);

  return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
    <defs><linearGradient id="fanGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${C.accent}" stop-opacity="0.12"/><stop offset="100%" stop-color="${C.accent}" stop-opacity="0.02"/></linearGradient></defs>
    ${yTicks.map(v => `<line x1="${pad.l}" y1="${sy(v)}" x2="${width-pad.r}" y2="${sy(v)}" stroke="${C.grid}" stroke-width="0.5"/><text x="${pad.l-6}" y="${sy(v)+4}" text-anchor="end" fill="${C.muted}" font-size="10" font-family="var(--mono)">${fmtBRL(v)}</text>`).join('')}
    <polygon points="${top} ${bot}" fill="url(#fanGrad)"/>
    ${sLines}
    <path d="${exp}" fill="none" stroke="${C.accent}" stroke-width="2.5" stroke-linecap="round"/>
    ${fanData.map((f,i) => `<text x="${sx(i)}" y="${height-8}" text-anchor="middle" fill="${C.muted}" font-size="11" font-weight="600">${f.horizon_years}A</text>`).join('')}
  </svg>`;
}

/* ── Band chart ────────────────────────────────────────── */

function bandChart(current, dist, { width=520, height=50 } = {}) {
  if (!dist) return '';
  const pad = {l:8,r:8};
  const bw = width-pad.l-pad.r;
  const {p10,p25,p50,p75,p90} = dist;
  const mn = p10*0.98, mx = p90*1.02, rng = mx-mn||1;
  const sx = v => pad.l + ((v-mn)/rng)*bw;
  const cy = height/2, bh = 16;

  return `<svg viewBox="0 0 ${width} ${height}" class="chart-svg">
    <rect x="${sx(p10)}" y="${cy-bh/2}" width="${sx(p90)-sx(p10)}" height="${bh}" fill="rgba(255,255,255,0.04)" rx="4"/>
    <rect x="${sx(p25)}" y="${cy-bh/2}" width="${sx(p75)-sx(p25)}" height="${bh}" fill="${C.accent}" rx="3" opacity="0.3"/>
    <line x1="${sx(p50)}" y1="${cy-bh/2-3}" x2="${sx(p50)}" y2="${cy+bh/2+3}" stroke="${C.muted}" stroke-width="1.5"/>
    ${current != null ? `<circle cx="${sx(current)}" cy="${cy}" r="5" fill="${C.gold}" stroke="var(--bg-0)" stroke-width="2"/>` : ''}
  </svg>`;
}

export { C, fmtBRL, fmtNum, fmtPct, fmtDate, fmtDateTime, lineChart, gaugeChart, waterfallHTML, fanChart, bandChart };

/**
 * common.js — shared helpers for popup.html and analyse.html.
 * Must be loaded before popup.js / analyse.js.
 */

// ── Escape server-sourced strings before innerHTML interpolation ──
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmt(n) {
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtCompact(n) {
  if (n == null || isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e9) return (n / 1e9).toFixed(2) + ' Arba';
  if (abs >= 1e7) return (n / 1e7).toFixed(2) + ' Cr';
  if (abs >= 1e5) return (n / 1e5).toFixed(2) + ' Lakh';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

// ── Engine port discovery (cached — revalidated with one ping per call) ──
const ENGINE_PORT_MIN = 5758;
const ENGINE_PORT_MAX = 5768;
let cachedEnginePort = null;

async function pingEnginePort(p) {
  try {
    const r = await fetch(`http://localhost:${p}/ping`, { signal: AbortSignal.timeout(300) });
    return r.ok;
  } catch (_) {
    return false;
  }
}

async function findPort() {
  if (cachedEnginePort && await pingEnginePort(cachedEnginePort)) return cachedEnginePort;
  cachedEnginePort = null;
  for (let p = ENGINE_PORT_MIN; p <= ENGINE_PORT_MAX; p++) {
    if (await pingEnginePort(p)) { cachedEnginePort = p; return p; }
  }
  return null;
}

// ── Theme persistence (shared across popup and analyse pages) ──
function loadThemeIsDark() {
  return localStorage.getItem('theme') !== 'light';
}

function saveThemeIsDark(isDark) {
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
}

// ── Local name→ticker fallbacks (used when server search is offline) ──
const LOCAL_NAME_ALIASES = [
  { pattern: /\beverest\b/i, symbol: 'EBL' },
  { pattern: /\bnabil\b/i, symbol: 'NABIL' },
  { pattern: /\bnepal life\b/i, symbol: 'NLIC' },
  { pattern: /\bnic asia\b/i, symbol: 'NICA' },
  { pattern: /\bglobal ime\b/i, symbol: 'GBIME' },
  { pattern: /\bhimalayan bank\b/i, symbol: 'HBL' },
  { pattern: /\bstandard chartered\b/i, symbol: 'SCB' },
  { pattern: /\bprabhu bank\b/i, symbol: 'PRVU' },
  { pattern: /\bmachhapuchchhre\b/i, symbol: 'MBL' },
  { pattern: /\bkumari bank\b/i, symbol: 'KBL' },
  { pattern: /\bmuktinath\b/i, symbol: 'MNBBL' },
];

const LOCAL_NAME_GROUPS = [
  {
    pattern: /\bhimalayan\b/i,
    items: [
      { symbol: 'HBL', name: 'Himalayan Bank Limited' },
      { symbol: 'HDL', name: 'Himalayan Distillery Limited' },
      { symbol: 'HEI', name: 'Himalayan Everest Insurance Limited' },
      { symbol: 'HEIP', name: 'Himalayan Everest Insurance Limited Promoter' },
      { symbol: 'HHL', name: 'Himalayan Hydropower Limited' },
      { symbol: 'HLBSL', name: 'Himalayan Laghubitta Bittiya Sanstha Limited' },
      { symbol: 'HLI', name: 'Himalayan Life Insurance Limited' },
      { symbol: 'HPPL', name: 'Himalayan Power Partner Limited' },
      { symbol: 'HRL', name: 'Himalayan Reinsurance Limited' },
    ],
  },
];

function localResolveCandidates(query) {
  const q = query.trim();
  const grouped = LOCAL_NAME_GROUPS.find(item => item.pattern.test(q));
  if (grouped) return grouped.items;
  return LOCAL_NAME_ALIASES
    .filter(item => item.pattern.test(q))
    .map(item => ({ symbol: item.symbol, name: item.symbol }));
}

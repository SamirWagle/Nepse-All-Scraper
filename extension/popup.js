/**
 * popup.js — NEPSE CAGR Calculator Extension
 */

const symbolInput     = document.getElementById('symbol-input');
const yearsInput      = document.getElementById('years-input');
const dateInput       = document.getElementById('date-input');
const investmentInput = document.getElementById('investment-input');
const calcBtn         = document.getElementById('calc-btn');
const statusEl        = document.getElementById('status');
const resultsEl       = document.getElementById('results');
const perfToggleBtn   = document.getElementById('perf-toggle-btn');
const perfDetails     = document.getElementById('perf-details');
const themeBtn        = document.getElementById('theme-btn');
const analyseBtn      = document.getElementById('analyse-btn');
const toggleYears     = document.getElementById('toggle-years');
const toggleDate      = document.getElementById('toggle-date');
const yearsWrap       = document.getElementById('years-input-wrap');
const dateWrap        = document.getElementById('date-input-wrap');

// ── Theme ─────────────────────────────────────────────────────────────────────
let isDark = true;
themeBtn.onclick = () => {
  isDark = !isDark;
  document.body.classList.toggle('light', !isDark);
  themeBtn.textContent = isDark ? '☀️' : '🌙';
};

// ── Period toggle ─────────────────────────────────────────────────────────────
let useYears = true;
toggleYears.onclick = () => {
  useYears = true;
  toggleYears.classList.add('active');
  toggleDate.classList.remove('active');
  yearsWrap.style.display = 'flex';
  dateWrap.style.display = 'none';
};
toggleDate.onclick = () => {
  useYears = false;
  toggleDate.classList.add('active');
  toggleYears.classList.remove('active');
  yearsWrap.style.display = 'none';
  dateWrap.style.display = 'block';
};

// ── Resolve name/ticker → symbol via server search ────────────────────────────
async function resolveSymbol(query) {
  for (let p = 5758; p <= 5768; p++) {
    try {
      const probe = await fetch(`http://localhost:${p}/ping`, { signal: AbortSignal.timeout(300) });
      if (!probe.ok) continue;
      const resp = await fetch(`http://localhost:${p}/search?q=${encodeURIComponent(query)}`);
      const data = await resp.json();
      return { port: p, results: data.results || [] };
    } catch(_) { continue; }
  }
  return { port: null, results: [] };
}

function normalizeQueryFallback(query) {
  return query.trim().toUpperCase().replace(/[^A-Z0-9]+/g, '');
}

function looksLikeTicker(query) {
  return /^[A-Za-z0-9]{1,15}$/.test(query.trim());
}

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

function localResolveSymbol(query) {
  const q = query.trim();
  const hit = LOCAL_NAME_ALIASES.find(item => item.pattern.test(q));
  return hit ? hit.symbol : null;
}

function localResolveCandidates(query) {
  const q = query.trim();
  return LOCAL_NAME_ALIASES
    .filter(item => item.pattern.test(q))
    .map(item => ({ symbol: item.symbol, name: item.symbol }));
}

function showPickerInStatus(candidates, onSelect) {
  const list = candidates.map(c =>
    `<div class="picker-item" data-symbol="${c.symbol}"><strong>${c.symbol}</strong> — ${c.name}</div>`
  ).join('');
  statusEl.innerHTML = `<div style="font-size:12px;color:var(--label);margin-bottom:4px">Pick one:</div>${list}`;
  statusEl.querySelectorAll('.picker-item').forEach(el => {
    el.style.cssText = 'cursor:pointer;padding:4px 6px;border-radius:6px;margin:2px 0;font-size:12px;';
    el.addEventListener('mouseenter', () => { el.style.background = 'rgba(78,205,196,0.2)'; });
    el.addEventListener('mouseleave', () => { el.style.background = ''; });
    el.addEventListener('click', () => {
      statusEl.innerHTML = '';
      onSelect(el.dataset.symbol);
    });
  });
}

// ── Analyse Stock button — opens full-page analysis ───────────────────────────
analyseBtn.onclick = async () => {
  const query = symbolInput.value.trim();
  if (!query) {
    chrome.tabs.create({ url: chrome.runtime.getURL('analyse.html') });
    return;
  }
  const { results } = await resolveSymbol(query);
  if (results.length === 0) {
    const localResults = localResolveCandidates(query);
    if (localResults.length === 1) {
      const url = chrome.runtime.getURL('analyse.html') + '?symbol=' + encodeURIComponent(localResults[0].symbol);
      chrome.tabs.create({ url });
      return;
    } else if (localResults.length > 1) {
      showPickerInStatus(localResults, sym => {
        chrome.tabs.create({ url: chrome.runtime.getURL('analyse.html') + '?symbol=' + encodeURIComponent(sym) });
      });
      return;
    }
    if (looksLikeTicker(query)) {
      const url = chrome.runtime.getURL('analyse.html') + '?symbol=' + encodeURIComponent(normalizeQueryFallback(query));
      chrome.tabs.create({ url });
    } else {
      setStatus(`No company found for "${query}"`);
    }
  } else if (results.length === 1) {
    const url = chrome.runtime.getURL('analyse.html') + '?symbol=' + encodeURIComponent(results[0].symbol);
    chrome.tabs.create({ url });
  } else {
    showPickerInStatus(results, sym => {
      chrome.tabs.create({ url: chrome.runtime.getURL('analyse.html') + '?symbol=' + encodeURIComponent(sym) });
    });
  }
};

perfToggleBtn.onclick = () => {
  const open = perfDetails.style.display === 'block';
  perfDetails.style.display = open ? 'none' : 'block';
  perfToggleBtn.textContent = open ? '▼ Performance Details' : '▲ Performance Details';
};

// ── Calculate ─────────────────────────────────────────────────────────────────
calcBtn.onclick = async () => {
  const query = symbolInput.value.trim();
  if (!query) { setStatus('Please enter a stock symbol or name.'); return; }

  calcBtn.disabled = true;
  resultsEl.style.display = 'none';
  setStatus('⏳ Resolving...');

  const { results } = await resolveSymbol(query);
  if (results.length === 0) {
    const localResults = localResolveCandidates(query);
    if (localResults.length === 1) {
      runCalc(localResults[0].symbol);
      return;
    } else if (localResults.length > 1) {
      calcBtn.disabled = false;
      showPickerInStatus(localResults, sym => { symbolInput.value = sym; calcBtn.click(); });
      return;
    }
    if (looksLikeTicker(query)) {
      runCalc(normalizeQueryFallback(query));
    } else {
      setStatus(`No company found for "${query}"`);
      calcBtn.disabled = false;
    }
    return;
  }
  if (results.length > 1) {
    calcBtn.disabled = false;
    showPickerInStatus(results, sym => { symbolInput.value = sym; calcBtn.click(); });
    return;
  }
  runCalc(results[0].symbol);
};

async function runCalc(symbol) {
  symbolInput.value = symbol;
  calcBtn.disabled = true;
  const investment = parseFloat(investmentInput.value) || 100000;
  let years = null;
  let startDate = null;

  if (useYears) {
    years = parseFloat(yearsInput.value) || 5;
  } else {
    startDate = dateInput.value;
    if (!startDate) { setStatus('Please select a start date.'); calcBtn.disabled = false; return; }
  }

  setStatus('⏳ Calculating...');

  const payload = { symbol, investment };
  if (useYears) payload.years = years;
  else payload.start_date = startDate;

  // ── Try direct fetch first (engine already running) ───────────────────────
  let enginePort = await findEnginePort();

  if (enginePort) {
    try {
      const resp = await fetch(`http://localhost:${enginePort}/cagr`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await resp.json();
      handleResult(data);
      calcBtn.disabled = false;
      return;
    } catch (err) {
      setStatus(`❌ Engine error: ${err.message}`);
      calcBtn.disabled = false;
      return;
    }
  }

  // ── Engine not running — start via native messaging ───────────────────────
  setStatus('⚙️ Starting engine (first time may take ~15s)...');
  chrome.runtime.sendMessage({ action: 'cagrViaNative', payload }, (data) => {
    if (chrome.runtime.lastError) {
      setStatus('❌ Native host error: ' + chrome.runtime.lastError.message);
    } else if (!data) {
      setStatus('❌ No response from engine.');
    } else {
      handleResult(data);
    }
    calcBtn.disabled = false;
  });
}

// ── Find engine port ──────────────────────────────────────────────────────────
async function findEnginePort() {
  for (let p = 5758; p <= 5768; p++) {
    try {
      const probe = await fetch(`http://localhost:${p}/ping`, {
        method: 'GET',
        signal: AbortSignal.timeout(300)
      });
      if (probe.ok) return p;
    } catch (_) { continue; }
  }
  return null;
}

// ── Display results ───────────────────────────────────────────────────────────
function handleResult(data) {
  if (!data || data.error) {
    setStatus('❌ ' + (data?.error || 'Unknown error'));
    return;
  }

  setStatus('');
  resultsEl.style.display = 'block';
  perfDetails.style.display = 'none';
  perfToggleBtn.textContent = '▼ Performance Details';

  // CAGR banner
  const cagr = data.cagr_pct;
  const cagrEl = document.getElementById('cagr-display');
  cagrEl.textContent = (cagr >= 0 ? '+' : '') + cagr.toFixed(2) + '%';
  cagrEl.className = 'cagr-value ' + (cagr >= 0 ? 'positive' : 'negative');
  document.getElementById('cagr-meta').textContent =
    `${data.start_date} → ${data.end_date}  (${data.years} yrs)`;

  // Summary cells
  document.getElementById('res-units').textContent  = data.is_index ? '— (Index)' : data.total_units_today + ' kitta';
  document.getElementById('res-ltp').textContent    = (data.is_index ? '' : 'Rs. ') + fmt(data.ltp);
  document.getElementById('res-market').textContent = 'Rs. ' + fmt(data.market_value);
  document.getElementById('res-cash').textContent   = data.is_index ? '—' : 'Rs. ' + fmt(data.total_cash_dividends);

  // Events table
  const tbody = document.getElementById('events-body');
  tbody.innerHTML = '';
  if (data.events && data.events.length > 0) {
    data.events.forEach(ev => {
      const tr = document.createElement('tr');
      let badge;
      if (ev.type === 'bonus') {
        badge = `<span class="badge badge-bonus">Bonus ${(ev.pct * 100).toFixed(0)}%</span>`;
      } else if (ev.type === 'right') {
        badge = `<span class="badge badge-right">Rights ${ev.ratio} @ Rs.${ev.issue_price}</span>`;
      } else {
        badge = `<span class="badge badge-cash">Cash ${(ev.pct * 100).toFixed(1)}%</span>`;
      }
      const cashCol = ev.type === 'cash' ? 'Rs. ' + fmt(ev.cash_rs) : '—';
      tr.innerHTML = `
        <td>${ev.date}</td>
        <td>${badge} ${ev.fiscal_year || ''}</td>
        <td>${ev.units_after.toFixed(4)}</td>
        <td>${cashCol}</td>
      `;
      tbody.appendChild(tr);
    });
  } else {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--label);padding:12px">No bonus/dividend events in this period</td></tr>';
  }
}

function fmt(n) {
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function setStatus(msg) {
  statusEl.textContent = msg;
}

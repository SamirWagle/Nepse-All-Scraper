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

// ── Analyse Stock button — opens full-page analysis ───────────────────────────
analyseBtn.onclick = () => {
  chrome.tabs.create({ url: chrome.runtime.getURL('analyse.html') });
};

// ── Calculate ─────────────────────────────────────────────────────────────────
calcBtn.onclick = async () => {
  const symbol = symbolInput.value.trim().toUpperCase();
  if (!symbol) { setStatus('Please enter a stock symbol.'); return; }

  const investment = parseFloat(investmentInput.value) || 100000;
  let years = null;
  let startDate = null;

  if (useYears) {
    years = parseFloat(yearsInput.value) || 5;
  } else {
    startDate = dateInput.value;
    if (!startDate) { setStatus('Please select a start date.'); return; }
  }

  calcBtn.disabled = true;
  resultsEl.style.display = 'none';
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
};

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

  // CAGR banner
  const cagr = data.cagr_pct;
  const cagrEl = document.getElementById('cagr-display');
  cagrEl.textContent = (cagr >= 0 ? '+' : '') + cagr.toFixed(2) + '%';
  cagrEl.className = 'cagr-value ' + (cagr >= 0 ? 'positive' : 'negative');
  document.getElementById('cagr-meta').textContent =
    `${data.start_date} → ${data.end_date}  (${data.years} yrs)`;

  // Summary cells
  document.getElementById('res-units').textContent  = data.total_units_today + ' kitta';
  document.getElementById('res-ltp').textContent    = 'Rs. ' + fmt(data.ltp);
  document.getElementById('res-market').textContent = 'Rs. ' + fmt(data.market_value);
  document.getElementById('res-cash').textContent   = 'Rs. ' + fmt(data.total_cash_dividends);

  // Events table
  const tbody = document.getElementById('events-body');
  tbody.innerHTML = '';
  if (data.events && data.events.length > 0) {
    data.events.forEach(ev => {
      const tr = document.createElement('tr');
      const badge = ev.type === 'bonus'
        ? `<span class="badge badge-bonus">Bonus ${(ev.pct * 100).toFixed(0)}%</span>`
        : `<span class="badge badge-cash">Cash ${(ev.pct * 100).toFixed(1)}%</span>`;
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

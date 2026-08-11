/**
 * popup.js — NEPSE CAGR Calculator Extension
 * Depends on common.js (esc, fmt, findPort, localResolveCandidates, theme helpers).
 */

const symbolInput     = document.getElementById('symbol-input');
const yearsInput      = document.getElementById('years-input');
const dateInput       = document.getElementById('date-input');
const endDateInput    = document.getElementById('end-date-input');
const endDateClear    = document.getElementById('end-date-clear');
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
let isDark = loadThemeIsDark();
document.documentElement.classList.toggle('light', !isDark);
themeBtn.textContent = isDark ? '☀️' : '🌙';
themeBtn.onclick = () => {
  isDark = !isDark;
  saveThemeIsDark(isDark);
  document.documentElement.classList.toggle('light', !isDark);
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
endDateClear.onclick = () => {
  const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
  endDateInput.value = today;
};

// ── Resolve name/ticker → symbol via server search ────────────────────────────
async function resolveSymbol(query) {
  const port = await findPort();
  if (!port) return { port: null, results: [] };
  try {
    const resp = await fetch(
      `http://localhost:${port}/search?q=${encodeURIComponent(query)}&max_results=30`,
      { signal: AbortSignal.timeout(5000) }
    );
    const data = await resp.json();
    return { port, results: data.results || [] };
  } catch (_) {
    return { port: null, results: [] };
  }
}

function normalizeQueryFallback(query) {
  return query.trim().toUpperCase().replace(/[^A-Z0-9]+/g, '');
}

function looksLikeTicker(query) {
  return /^[A-Za-z0-9]{1,15}$/.test(query.trim());
}

function showPickerInStatus(candidates, onSelect, onMore, hasMore = false) {
  const list = candidates.map(c =>
    `<div class="picker-item" data-symbol="${esc(c.symbol)}"><strong>${esc(c.symbol)}</strong> — ${esc(c.name)}</div>`
  ).join('');
  const moreBtn = hasMore
    ? `<button class="picker-more-btn" type="button">Show 10 more</button>`
    : '';
  statusEl.innerHTML = `<div style="font-size:12px;color:var(--label);margin-bottom:4px">Pick one:</div>${list}${moreBtn}`;
  statusEl.querySelectorAll('.picker-item').forEach(el => {
    el.style.cssText = 'cursor:pointer;padding:4px 6px;border-radius:6px;margin:2px 0;font-size:12px;';
    el.addEventListener('mouseenter', () => { el.style.background = 'rgba(78,205,196,0.2)'; });
    el.addEventListener('mouseleave', () => { el.style.background = ''; });
    el.addEventListener('click', () => {
      statusEl.innerHTML = '';
      onSelect(el.dataset.symbol);
    });
  });
  const moreEl = statusEl.querySelector('.picker-more-btn');
  if (moreEl && onMore) {
    moreEl.addEventListener('click', () => onMore());
  }
}

function openAnalysePage(symbol) {
  const url = chrome.runtime.getURL('analyse.html')
    + (symbol ? '?symbol=' + encodeURIComponent(symbol) : '');
  chrome.tabs.create({ url });
}

// ── Analyse Stock button — opens full-page analysis ───────────────────────────
analyseBtn.onclick = async () => {
  const query = symbolInput.value.trim();
  if (!query) {
    openAnalysePage(null);
    return;
  }
  const { results } = await resolveSymbol(query);
  if (results.length === 0) {
    const localResults = localResolveCandidates(query);
    if (localResults.length === 1) {
      openAnalysePage(localResults[0].symbol);
      return;
    } else if (localResults.length > 1) {
      showPickerInStatus(localResults, sym => openAnalysePage(sym), null, false);
      return;
    }
    if (looksLikeTicker(query)) {
      openAnalysePage(normalizeQueryFallback(query));
    } else {
      setStatus(`No company found for "${query}"`);
    }
  } else if (results.length === 1) {
    openAnalysePage(results[0].symbol);
  } else {
    showPickerInStatus(results, sym => openAnalysePage(sym), null, false);
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
      showPickerInStatus(localResults, sym => { symbolInput.value = sym; calcBtn.click(); }, null, false);
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
    showPickerInStatus(results, sym => { symbolInput.value = sym; calcBtn.click(); }, null, false);
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
  if (useYears) {
    payload.years = years;
  } else {
    payload.start_date = startDate;
    const endDateVal = endDateInput.value;
    if (endDateVal) payload.end_date = endDateVal;
  }

  // ── Try direct fetch first (engine already running) ───────────────────────
  const enginePort = await findPort();

  if (enginePort) {
    try {
      const resp = await fetch(`http://localhost:${enginePort}/cagr`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(10000)
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

  // Returns banner — XIRR when rights shares occurred in the window
  // (money-weighted, each cashflow timed correctly), CAGR otherwise.
  const isXirr = data.method === 'XIRR';
  const cagr = isXirr ? data.xirr_pct : data.cagr_pct;
  const cagrEl = document.getElementById('cagr-display');
  cagrEl.textContent = (cagr >= 0 ? '+' : '') + cagr.toFixed(2) + '%';
  cagrEl.className = 'cagr-value ' + (cagr >= 0 ? 'positive' : 'negative');
  document.getElementById('cagr-label').textContent =
    isXirr ? 'XIRR (Money-Weighted Return)' : 'Compound Annual Growth Rate';
  document.getElementById('cagr-meta').textContent =
    `${data.start_date} → ${data.end_date}  (${data.years} yrs)`;

  const investmentVal = parseFloat(document.getElementById('investment-input').value) || 0;
  const multiplierEl = document.getElementById('cagr-multiplier');
  if (investmentVal > 0 && data.market_value > 0) {
    const mult = data.market_value / investmentVal;
    multiplierEl.textContent = mult.toFixed(2) + 'x';
    multiplierEl.className = 'cagr-multiplier ' + (cagr >= 0 ? 'positive' : 'negative');
    multiplierEl.style.display = '';
  } else {
    multiplierEl.style.display = 'none';
  }

  // Summary cells
  document.getElementById('res-units').textContent  = data.is_index ? '— (Index)' : data.total_units_today + ' kitta';
  document.getElementById('res-ltp').textContent    = (data.is_index ? '' : 'Rs. ') + fmt(data.ltp);
  document.getElementById('res-market').textContent = 'Rs. ' + fmt(data.market_value);
  document.getElementById('res-cash').textContent   = data.is_index ? '—' : 'Rs. ' + fmt(data.total_cash_dividends);

  // Events table
  const tbody = document.getElementById('events-body');
  tbody.innerHTML = '';

  // Initial purchase row
  if (!data.is_index && data.units_bought > 0) {
    const initTr = document.createElement('tr');
    initTr.innerHTML = `
      <td>${esc(data.start_date)}</td>
      <td><span class="badge" style="background:rgba(78,205,196,0.15);color:var(--accent)">Purchase @ Rs.${fmt(data.start_price)}</span></td>
      <td>${Number(data.units_bought).toFixed(4)}</td>
      <td>—</td>
    `;
    tbody.appendChild(initTr);
  }

  if (data.events && data.events.length > 0) {
    data.events.forEach(ev => {
      const tr = document.createElement('tr');
      let badge;
      if (ev.type === 'bonus') {
        badge = `<span class="badge badge-bonus">Bonus ${(ev.pct * 100).toFixed(0)}%</span>`;
      } else if (ev.type === 'right') {
        badge = `<span class="badge badge-right">Rights ${esc(ev.ratio)} @ Rs.${esc(ev.issue_price)}</span>`;
      } else {
        badge = `<span class="badge badge-cash">Cash ${(ev.pct * 100).toFixed(1)}%</span>`;
      }
      const cashCol = ev.type === 'cash' ? 'Rs. ' + fmt(ev.cash_rs) : '—';
      tr.innerHTML = `
        <td>${esc(ev.date)}</td>
        <td>${badge} ${esc(ev.fiscal_year || '')}</td>
        <td>${ev.units_after.toFixed(4)}</td>
        <td>${cashCol}</td>
      `;
      tbody.appendChild(tr);
    });
  } else {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--label);padding:12px">No bonus/dividend events in this period</td></tr>';
  }
}

function setStatus(msg) {
  statusEl.textContent = msg;
}

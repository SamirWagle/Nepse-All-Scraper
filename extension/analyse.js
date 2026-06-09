    // ── Page switching ──
    const backDestination = { buffett: 'nexttop', nexttop: 'bullbear', fdrates: 'nexttop' };
    let lastSearchedSymbol = null;
    const MERGED_COMPANIES = {
      HAMA: {
        merged_date: '2016-09-04',
        merged_to: 'CBL',
        merged_to_name: 'Civil Bank Limited',
        note: 'Hama Merchant & Finance Limited merged into Civil Bank Limited.'
      },
      CBL: {
        merged_date: '2023-01-10',
        merged_to: 'HBL',
        merged_to_name: 'Himalayan Bank Limited',
        note: 'Civil Bank Limited merged into Himalayan Bank Limited.'
      },
      CCBL: {
        merged_date: '2023-01-10',
        merged_to: 'PRVU',
        merged_to_name: 'Prabhu Bank Limited',
        note: 'Century Commercial Bank Ltd. merged into Prabhu Bank Limited.'
      },
      PRVU: {
        status: 'active_survivor',
        merged_date: '2023-01-10',
        merged_from: 'CCBL',
        merged_from_name: 'Century Commercial Bank Ltd.',
        surviving_name: 'Prabhu Bank Limited',
        note: 'Prabhu Bank Limited is the surviving company after merging with Century Commercial Bank Ltd.'
      },
      MEGA: {
        merged_date: '2023-01-10',
        merged_to: 'NIMB',
        merged_to_name: 'Nepal Investment Mega Bank Limited',
        note: 'Mega Bank Nepal Limited merged into Nepal Investment Mega Bank Limited.'
      },
      NIMB: {
        status: 'active_survivor',
        merged_date: '2023-01-10',
        merged_from: 'MEGA',
        merged_from_name: 'Mega Bank Nepal Limited',
        surviving_name: 'Nepal Investment Mega Bank Limited',
        note: 'Nepal Investment Mega Bank Limited is the surviving company after merging with Mega Bank Nepal Limited.'
      }
    };

    // ── Sub-index tickers recognised by the app ──
    const INDEX_SYMBOL_MAP = {
      NEPSE: 'NEPSE',
      NEPSEIND: 'NEPSE',
      SENSITIVE: 'Sensitive Index',
      SENSITIVEIND: 'Sensitive Index',
      SENSITIVEFLOAT: 'Sensitive Float Index',
      SFLOAT: 'Sensitive Float Index',
      SFLOATIND: 'Sensitive Float Index',
      FLOAT: 'Float Index',
      FLOATIND: 'Float Index',
      BANKEX: 'Banking SubIndex',
      BANKING: 'Banking SubIndex',
      BANKINGIND: 'Banking SubIndex',
      DEVBANKEX: 'Development Bank Index',
      DEVBANK: 'Development Bank Index',
      DEVBANKIND: 'Development Bank Index',
      FINEX: 'Finance Index',
      FINANCE: 'Finance Index',
      FINANCEIND: 'Finance Index',
      HOTLEX: 'Hotels & Tourism',
      HOTEL: 'Hotels & Tourism',
      HOTELIND: 'Hotels & Tourism',
      HYDROEX: 'HydroPower Index',
      HYDRO: 'HydroPower Index',
      HYDROIND: 'HydroPower Index',
      HYDROPOWERIND: 'HydroPower Index',
      HYDROPOWIND: 'HydroPower Index',
      INSURE: 'Insurance',
      INSURANCE: 'Insurance',
      INSURANCEIND: 'Insurance',
      INVEST: 'Investment',
      INVESTMENT: 'Investment',
      INVESTMENTIND: 'Investment',
      LIFEINSURE: 'Life Insurance',
      LIFEINSURANCE: 'Life Insurance',
      LIFEINSURANCEIND: 'Life Insurance',
      LIFEINSUIND: 'Life Insurance',
      LIFEIND: 'Life Insurance',
      MANUIND: 'Manufacturing & Processing',
      MANUFACTUREIND: 'Manufacturing & Processing',
      MANUFACTURING: 'Manufacturing & Processing',
      MANUFACTURINGIND: 'Manufacturing & Processing',
      MICROEX: 'Microfinance Index',
      MICROFINANCE: 'Microfinance Index',
      MICROFINANCEIND: 'Microfinance Index',
      MFEX: 'Mutual Fund',
      MUTUALFUND: 'Mutual Fund',
      MUTUALFUNDIND: 'Mutual Fund',
      NONLIFEINSURE: 'Non Life Insurance',
      NONLIFEINSURANCE: 'Non Life Insurance',
      NONLIFEIND: 'Non Life Insurance',
      OTHERS: 'Others Index',
      OTHERSIND: 'Others Index',
      TRADING: 'Trading Index',
      TRADINGIND: 'Trading Index',
    };

    async function switchPage(name) {
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      document.getElementById('page-' + name).classList.add('active');
      document.getElementById('analyse-menu').classList.remove('open');
      document.getElementById('analyse-trigger').classList.remove('open');
      document.getElementById('back-btn').style.display = name === 'analyse' ? 'none' : 'inline-block';
      if (name === 'bullbear') {
        buildChart();
        if (lastSearchedSymbol) doBullSearch(lastSearchedSymbol);
      }
      if (name === 'fdrates') {
        buildFdChart();
      }
    }

    async function openBullBearFromQuery(query) {
      if (!query) return;
      // Index tickers bypass company symbol resolution
      const upperQ = query.toUpperCase();
      if (INDEX_SYMBOL_MAP[upperQ]) {
        runIndexBullBear(upperQ);
        return;
      }
      document.getElementById('page-status').textContent = '⏳ Resolving...';
      const { results, error } = await resolveBullSymbol(query);
      if (error) {
        document.getElementById('page-status').textContent = '❌ ' + error;
        return;
      }
      if (!results || results.length === 0) {
        document.getElementById('page-status').textContent = '❌ No company found for "' + query + '"';
        return;
      }
      if (results.length > 1) {
        showPagedPicker(async (offset, limit) => {
          const { results: pageResults, error: pageError } = await resolveSymbolPage(query, offset, limit);
          return { results: pageResults || [], error: pageError };
        }, sym => {
          lastSearchedSymbol = sym;
          showLtpWidget();
          document.getElementById('search-input').value = sym;
          switchPage('bullbear');
        });
        return;
      }
      lastSearchedSymbol = results[0].symbol;
      document.getElementById('search-input').value = results[0].symbol;
      document.getElementById('page-status').textContent = '';

      switchPage('bullbear');
    }

    // ── Back button ──
    document.getElementById('back-btn').addEventListener('click', () => {
      const current = document.querySelector('.page.active').id.replace('page-', '');
      switchPage(backDestination[current] || 'analyse');
    });

    // ── Dropdown ──
    document.getElementById('analyse-trigger').addEventListener('click', (e) => {
      e.stopPropagation();
      const menu = document.getElementById('analyse-menu');
      const trigger = document.getElementById('analyse-trigger');
      const isOpen = menu.classList.contains('open');
      menu.classList.toggle('open', !isOpen);
      trigger.classList.toggle('open', !isOpen);
    });
    document.getElementById('menu-analyse').addEventListener('click', (e) => {
      e.stopPropagation();
      document.getElementById('analyse-menu').classList.remove('open');
      document.getElementById('analyse-trigger').classList.remove('open');
      const q = document.getElementById('search-input').value.trim().toUpperCase();
      if (INDEX_SYMBOL_MAP[q]) {
        // Indexes have no fundamentals — send to bull/bear instead
        runIndexBullBear(q);
      } else {
        doSearch();
      }
    });
    document.getElementById('menu-bullbear').addEventListener('click', (e) => {
      e.stopPropagation();
      openBullBearFromQuery(document.getElementById('search-input').value.trim());
    });
    document.getElementById('menu-technical').addEventListener('click', (e) => {
      e.stopPropagation();
      switchPage('technical');
    });
    document.getElementById('nexttop-btn').addEventListener('click', () => {
      switchPage('nexttop');
    });

    document.getElementById('overlay-ticker-btn').addEventListener('click', () => {
      toggleTickerOverlay();
    });

    // ── Cycle modals ──
    const modalOverlay = document.getElementById('cycle-modal-overlay');
    const modalTitle   = document.getElementById('cycle-modal-title');
    const modalBody    = document.getElementById('cycle-modal-body');

    function showCycleModal(title, rows, cls) {
      const accent = cls === 'bull' ? 'var(--bull)' : 'var(--bear)';
      const boxBg      = 'var(--surface)';
      const boxBorder  = 'var(--border)';
      const rowBg      = 'transparent';
      const rowBgAlt   = 'transparent';
      const labelColor = 'var(--label)';
      const textColor  = 'var(--text)';
      document.getElementById('cycle-modal-box').style.background = boxBg;
      document.getElementById('cycle-modal-box').style.borderColor = boxBorder;
      modalTitle.style.color = accent;
      modalTitle.textContent = title;
      modalBody.innerHTML = rows.map((r, i) =>
        `<tr style="border-bottom:1px solid ${boxBorder};background:${i % 2 === 0 ? rowBg : rowBgAlt}">
          <td style="padding:8px 10px;color:${labelColor}">${i + 1}</td>
          <td style="padding:8px 10px;color:${textColor}">${r.date}</td>
          <td style="padding:8px 10px;font-weight:700;color:${accent}">${r.index}</td>
        </tr>`
      ).join('');
      modalOverlay.style.display = 'flex';
    }

    document.getElementById('show-bull-tops').addEventListener('click', () => {
      showCycleModal('🐂 Bull Tops', [
        { date: '2000-11-23', index: '545.82' },
        { date: '2008-08-31', index: '1,175.38' },
        { date: '2016-07-27', index: '1,881.45' },
        { date: '2021-08-18', index: '3,198.60' },
      ], 'bull');
    });

    document.getElementById('show-bear-bottoms').addEventListener('click', () => {
      showCycleModal('🐻 Bear Bottoms', [
        { date: '2002-03-15', index: '186.22' },
        { date: '2012-03-29', index: '298.90' },
        { date: '2019-03-05', index: '1,098.95' },
        { date: '2022-09-25', index: '1,815.13' },
      ], 'bear');
    });

    document.getElementById('cycle-modal-close').addEventListener('click', () => {
      modalOverlay.style.display = 'none';
    });
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) modalOverlay.style.display = 'none';
    });
    // ── Date LTP lookup ──
    async function doLtpLookup() {
      const sym = lastSearchedSymbol;
      const dateVal = document.getElementById('ltp-date-input').value;
      const resultEl = document.getElementById('ltp-result');
      if (!sym) { resultEl.textContent = 'Search a stock first'; return; }
      if (!dateVal) { resultEl.textContent = 'Pick a date'; return; }
      resultEl.textContent = '⏳';
      try {
        const resp = await fetch(`http://localhost:5758/price?symbol=${encodeURIComponent(sym)}&date=${encodeURIComponent(dateVal)}`);
        const d = await resp.json();
        if (d.error) { resultEl.textContent = '❌ ' + d.error; return; }
        resultEl.innerHTML = `<span style="color:var(--accent)">${sym}</span> · Rs. ${Number(d.close).toLocaleString('en-IN', { maximumFractionDigits: 2 })} <span style="color:var(--text-3);font-weight:400">(${d.actual_date})</span>`;
      } catch (e) {
        resultEl.textContent = '❌ Server error';
      }
    }
    document.getElementById('ltp-lookup-btn').addEventListener('click', doLtpLookup);
    document.getElementById('ltp-date-input').addEventListener('keydown', e => { if (e.key === 'Enter') doLtpLookup(); });

    document.getElementById('buffett-link').addEventListener('click', (e) => {
      e.preventDefault();
      switchPage('buffett');
    });
    document.getElementById('fdrates-link').addEventListener('click', (e) => {
      e.preventDefault();
      switchPage('fdrates');
    });
    document.addEventListener('click', () => {
      document.getElementById('analyse-menu').classList.remove('open');
      document.getElementById('analyse-trigger').classList.remove('open');
    });

    // ── Theme ──
    let isDark = true;
    function toggleTheme() {
      isDark = !isDark;
      if (isDark) {
        document.documentElement.classList.remove('light');
      } else {
        document.documentElement.classList.add('light');
      }
      document.getElementById('theme-btn').textContent = isDark ? '☀️ Light Mode' : '🌙 Dark Mode';
      if (bbChart) { bbChart.destroy(); bbChart = null; buildChart(); }
    }
    document.getElementById('theme-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      toggleTheme();
    });

    document.getElementById('quit-btn').addEventListener('click', async (e) => {
      e.stopPropagation();
      const port = await findPort();
      if (!port) { alert('Server not running.'); return; }
      try { await fetch(`http://localhost:${port}/quit`); } catch(_) {}
      document.getElementById('quit-btn').textContent = '✓ Stopped';
      document.getElementById('quit-btn').disabled = true;
    });

    // ── Search ──
    document.getElementById('search-input').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

    // ── Init symbol from popup URL param ──
    const _urlSym = new URLSearchParams(window.location.search).get('symbol');
    if (_urlSym) {
      document.getElementById('search-input').value = _urlSym;
      lastSearchedSymbol = _urlSym;
      doSearch();
    }

    const BULL_CYCLES_DEF = [
      { num: 1, label: 'Bull 1', period: '~1994–2000', blank: true, reason: 'Pre-digital era',
        nepseStart: 100, nepseEnd: 545.82, nepseStartDate: '1994-01-13', nepseEndDate: '2000-11-23' },
      { num: 2, label: 'Bull 2', period: '2002–2008',  blank: true, reason: 'Historical data unavailable',
        nepseStart: 299.0, nepseEnd: 1175.38, nepseStartDate: '2002-03-15', nepseEndDate: '2008-08-31' },
      { num: 3, label: 'Bull 3', period: '2012–2016', start: '2012-03-29', end: '2016-07-27' },
      { num: 4, label: 'Bull 4', period: '2019–2021', start: '2019-03-05', end: '2021-08-18' },
      { num: 5, label: 'Bull 5 ★ Current', period: '2022–now', start: '2022-09-25', end: null, current: true },
    ];

    async function doBullSearch(symbol) {
      if (!symbol) return;
      const container = document.getElementById('bull-cycle-results');
      container.style.display = 'block';
      container.innerHTML = '<div style="color:var(--label);font-size:13px;padding:16px 0">⏳ Loading ' + symbol + ' across bull cycles...</div>';

      const port = await findPort();
      const tradingRange = await getTradingRange(symbol);
      const lastTradingDate = tradingRange.last_date || null;

      // Indexes have no IPO listing date — skip the fetch
      let listingDate = null;
      if (!INDEX_SYMBOL_MAP[symbol]) {
        try {
          if (port) {
            const r = await fetch(`http://localhost:${port}/listing_date?symbol=${symbol}`);
            const d = await r.json();
            if (d && d.listing_date) listingDate = d.listing_date;
          }
        } catch(_) {}
      }

      const fetchable = BULL_CYCLES_DEF.filter(c => !c.blank);

      const fetched = await Promise.all(fetchable.map(async cycle => {
        // Cycle ended before stock was listed — skip fetching, mark as not listed
        if (listingDate && cycle.end && cycle.end < listingDate) {
          return { num: cycle.num, data: { notListed: true, listingDate } };
        }
        if (lastTradingDate && cycle.start > lastTradingDate) {
          return { num: cycle.num, data: { notListed: true, listingDate: lastTradingDate } };
        }
        const payload = { symbol, investment: 100000, start_date: cycle.start };
        if (cycle.end) payload.end_date = cycle.end;
        try {
          if (port) {
            const resp = await fetch(`http://localhost:${port}/cagr`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
            return { num: cycle.num, data: await resp.json() };
          } else {
            const data = await new Promise(resolve => chrome.runtime.sendMessage({ action: 'cagrViaNative', payload }, resolve));
            return { num: cycle.num, data };
          }
        } catch(e) {
          return { num: cycle.num, data: { error: e.message } };
        }
      }));

      const dataMap = {};
      fetched.forEach(r => { dataMap[r.num] = r.data; });
      renderBullBoxes(symbol, dataMap, listingDate);

    }
    function renderBullBoxes(symbol, dataMap, listingDate) {
      const container = document.getElementById('bull-cycle-results');
      const boxes = BULL_CYCLES_DEF.map(cycle => {
        if (cycle.blank) {
          return `<div class="bull-box bull-box-blank">
            <div class="bull-box-title">${cycle.label}</div>
            <div class="bull-box-period">${cycle.period}</div>
            <div class="bull-box-na">—</div>
            <div class="bull-box-note">${cycle.reason}</div>
          </div>`;
        }
        const d = dataMap[cycle.num];
        // Stock didn't exist during this cycle
        if (d && d.notListed) {
          const mergedDate = d.listingDate ? d.listingDate : 'Unknown';
          return `<div class="bull-box bull-box-blank">
            <div class="bull-box-title">${cycle.label}</div>
            <div class="bull-box-period">${cycle.period}</div>
            <div class="bull-box-na">—</div>
            <div class="bull-box-note">Merged<br><span style="font-size:10px">Last traded: ${mergedDate}</span></div>
          </div>`;
        }
        if (!d || d.error) {
          const noDataForCycle = d?.error && d.error.includes('No price data');
          return `<div class="bull-box bull-box-blank">
            <div class="bull-box-title">${cycle.label}</div>
            <div class="bull-box-period">${cycle.period}</div>
            <div class="bull-box-na">—</div>
            <div class="bull-box-note">${noDataForCycle ? 'No data for this cycle' : (d?.error || 'No data')}</div>
          </div>`;
        }
        const ratio = d.todays_value / d.initial_investment;
        const multX = ratio >= 2 ? Math.round(ratio) + 'x' : ratio.toFixed(1) + 'x';
        const soFar = cycle.current ? ' so far' : '';
        const verb  = d.cagr_pct >= 0 ? 'grew' : 'fell';
        const cagrColor = d.cagr_pct >= 0 ? 'var(--accent)' : 'var(--down)';

        const isIndex = !!d.is_index;
        const boxId = `bull-perf-${cycle.num}`;
        const eventsHtml = (d.events && d.events.length > 0)
          ? d.events.map(ev => {
              let badge;
              if (ev.type === 'bonus') {
                badge = `<span class="badge badge-bonus">Bonus ${(ev.pct * 100).toFixed(0)}%</span>`;
              } else if (ev.type === 'right') {
                badge = `<span class="badge badge-right">Rights ${ev.ratio} @ Rs.${ev.issue_price}</span>`;
              } else {
                badge = `<span class="badge badge-cash">Cash ${(ev.pct * 100).toFixed(1)}%</span>`;
              }
              const cashCol = ev.type === 'cash' ? 'Rs. ' + fmt(ev.cash_rs) : '—';
              return `<tr>
                <td>${ev.date}</td>
                <td>${badge} <span class="ev-fy">${ev.fiscal_year || ''}</span></td>
                <td>${ev.units_after.toFixed(4)}</td>
                <td>${cashCol}</td>
              </tr>`;
            }).join('')
          : `<tr><td colspan="4" class="perf-no-events">No bonus / dividend events in this period</td></tr>`;

        return `<div class="bull-box">
          <div class="bull-box-title">${cycle.label}</div>
          <div class="bull-box-period">${d.start_date} → ${d.end_date}</div>
          <div class="bull-box-symbol">${symbol}</div>
          <div class="bull-box-cagr" style="color:${cagrColor}">${d.cagr_pct >= 0 ? '+' : ''}${d.cagr_pct.toFixed(1)}% CAGR</div>
          <div class="bull-box-duration">⏱ ${d.years.toFixed(1)} yrs</div>
          <div class="bull-box-multi">📈 Investment ${verb} ~${multX}${soFar}</div>
          <div class="bull-box-prices">${isIndex ? 'Index: ' : 'Rs.'}${fmt(d.start_price)} → ${isIndex ? '' : 'Rs.'}${fmt(d.ltp)}</div>

          ${isIndex ? '' : `<button class="perf-toggle-btn" data-perf-id="${boxId}">
            <span>▼ Performance Details</span>
          </button>

          <div class="perf-panel" id="${boxId}">
            <div class="perf-summary-grid">
              <div class="perf-summary-item">
                <span class="perf-label">Total Invested</span>
                <span class="perf-val">Rs. ${fmt(d.total_invested)}</span>
              </div>
              <div class="perf-summary-item">
                <span class="perf-label">Market Value</span>
                <span class="perf-val">Rs. ${fmt(d.market_value)}</span>
              </div>
              <div class="perf-summary-item">
                <span class="perf-label">Cash Dividends</span>
                <span class="perf-val perf-val-pos">Rs. ${fmt(d.total_cash_dividends)}</span>
              </div>
              <div class="perf-summary-item">
                <span class="perf-label">Total Value</span>
                <span class="perf-val ${d.todays_value >= d.total_invested ? 'perf-val-pos' : 'perf-val-neg'}">Rs. ${fmt(d.todays_value)}</span>
              </div>
              <div class="perf-summary-item">
                <span class="perf-label">Units Bought</span>
                <span class="perf-val">${d.units_bought.toFixed(4)} kitta</span>
              </div>
              <div class="perf-summary-item">
                <span class="perf-label">Units Today</span>
                <span class="perf-val perf-val-pos">${d.total_units_today.toFixed(4)} kitta</span>
              </div>
            </div>
            <div class="perf-formula">
              CAGR = (${fmt(d.todays_value)} ÷ ${fmt(d.total_invested)})<sup>1/${d.years}</sup> − 1
              = <span style="color:${cagrColor}">${d.cagr_pct >= 0 ? '+' : ''}${d.cagr_pct.toFixed(2)}%</span>
            </div>
            <div class="perf-events-label">Corporate Action Timeline</div>
            <div class="perf-table-wrap">
              <table class="perf-table">
                <thead><tr><th>Date</th><th>Event</th><th>Units After</th><th>Cash (Rs.)</th></tr></thead>
                <tbody>${eventsHtml}</tbody>
              </table>
            </div>
          </div>`}
        </div>`;
      }).join('');

      const listedStr = listingDate
        ? `<span style="font-size:11px;font-weight:500;color:var(--label);opacity:0.8;">🗓 Listed: ${listingDate}</span>`
        : '';
      container.innerHTML = `
        <div class="bull-cycle-header" style="display:flex;align-items:center;justify-content:space-between;">
          <span>📊 ${symbol} — Performance Across Bull Cycles</span>
          ${listedStr}
        </div>
        <div class="bull-boxes-grid" id="stock-bull-cards-row">${boxes}</div>`;

      // Compare to NEPSE button
      const hdr = container.querySelector('.bull-cycle-header');
      let btn = document.getElementById('compare-nepse-btn');
      if (!btn) {
        btn = document.createElement('button');
        btn.id = 'compare-nepse-btn';
        btn.style.cssText = 'background:transparent;border:1.5px solid var(--accent);color:var(--accent);border-radius:20px;padding:4px 14px;font-size:0.78rem;font-weight:600;letter-spacing:0.03em;cursor:pointer;opacity:0.85;transition:opacity 0.2s;';
        btn.onmouseenter = () => btn.style.opacity = 1;
        btn.onmouseleave = () => btn.style.opacity = 0.85;
        hdr.insertBefore(btn, hdr.lastElementChild);
      }
      btn.textContent = '📈 Compare to NEPSE';
      btn.onclick = () => toggleNepseComparison(symbol, dataMap);

      // Nepse row container
      let nepseRow = document.getElementById('nepse-comparison-row');
      if (!nepseRow) {
        nepseRow = document.createElement('div');
        nepseRow.id = 'nepse-comparison-row';
        nepseRow.style.cssText = 'display:none;margin-top:10px;';
        nepseRow.innerHTML = '<div style="font-size:11px;font-weight:700;color:var(--label);letter-spacing:0.08em;margin-bottom:8px;">NEPSE INDEX</div><div class="bull-boxes-grid" id="nepse-bull-cards-row"></div>';
        container.appendChild(nepseRow);
      } else {
        nepseRow.style.display = 'none';
        btn.textContent = '📈 Compare to NEPSE';
      }
    }

    async function toggleNepseComparison(symbol, dataMap) {
      const row = document.getElementById('nepse-comparison-row');
      const btn = document.getElementById('compare-nepse-btn');
      if (row.style.display !== 'none') {
        row.style.display = 'none';
        btn.textContent = '📈 Compare to NEPSE';
        return;
      }

      btn.textContent = '⏳ Loading…';
      btn.disabled = true;

      // Fetch NEPSE data for the same cycles
      const port = await findPort();
      const fetchable = BULL_CYCLES_DEF.filter(c => !c.blank);
      const fetched = await Promise.all(fetchable.map(async cycle => {
        try {
          const payload = { symbol: 'NEPSE', bull_num: cycle.num, start_date: cycle.start, end_date: cycle.end || null };
          let data;
          if (port) {
            const resp = await fetch(`http://localhost:${port}/cagr`, {
              method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
            });
            data = await resp.json();
          } else {
            data = await new Promise(resolve => chrome.runtime.sendMessage({ action: 'cagrViaNative', payload }, resolve));
          }
          return { num: cycle.num, data };
        } catch(e) {
          return { num: cycle.num, data: { error: e.message } };
        }
      }));

      const nepseMap = {};
      fetched.forEach(r => { nepseMap[r.num] = r.data; });

      const cardsRow = document.getElementById('nepse-bull-cards-row');
      cardsRow.innerHTML = BULL_CYCLES_DEF.map(cycle => {
        if (cycle.blank) {
          // Use hardcoded nepse prices if available
          if (cycle.nepseStart && cycle.nepseEnd) {
            const years = (new Date(cycle.nepseEndDate) - new Date(cycle.nepseStartDate)) / (1000*60*60*24*365.25);
            const cagr = (Math.pow(cycle.nepseEnd / cycle.nepseStart, 1/years) - 1) * 100;
            const ratio = cycle.nepseEnd / cycle.nepseStart;
            const multX = ratio >= 2 ? Math.round(ratio) + 'x' : ratio.toFixed(1) + 'x';
            const cagrColor = cagr >= 0 ? 'var(--accent)' : 'var(--down)';
            return `<div class="bull-box">
              <div class="bull-box-title">${cycle.label}</div>
              <div class="bull-box-period">${cycle.nepseStartDate} → ${cycle.nepseEndDate}</div>
              <div class="bull-box-symbol">NEPSE</div>
              <div class="bull-box-cagr" style="color:${cagrColor}">${cagr >= 0 ? '+' : ''}${cagr.toFixed(1)}% CAGR</div>
              <div class="bull-box-duration">⏱ ${years.toFixed(1)} yrs</div>
              <div class="bull-box-multi">📈 Index grew ~${multX}</div>
              <div class="bull-box-prices">Index: ${cycle.nepseStart} → ${cycle.nepseEnd}</div>
            </div>`;
          }
          return `<div class="bull-box bull-box-blank">
            <div class="bull-box-title">${cycle.label}</div>
            <div class="bull-box-period">${cycle.period}</div>
            <div class="bull-box-na">—</div>
            <div class="bull-box-note">${cycle.reason}</div>
          </div>`;
        }
        const d = nepseMap[cycle.num];
        if (!d || d.error) {
          const noDataForCycle = d?.error && d.error.includes('No price data');
          return `<div class="bull-box bull-box-blank">
            <div class="bull-box-title">${cycle.label}</div>
            <div class="bull-box-period">${cycle.period}</div>
            <div class="bull-box-na">—</div>
            <div class="bull-box-note">${noDataForCycle ? 'No data for this cycle' : (d?.error || 'No data')}</div>
          </div>`;
        }
        const cagrColor = d.cagr_pct >= 0 ? 'var(--accent)' : 'var(--down)';
        const ratio = d.todays_value / d.initial_investment;
        const multX = ratio >= 2 ? Math.round(ratio) + 'x' : ratio.toFixed(1) + 'x';
        const soFar = cycle.current ? ' so far' : '';
        const verb  = d.cagr_pct >= 0 ? 'grew' : 'fell';
        return `<div class="bull-box">
          <div class="bull-box-title">${cycle.label}</div>
          <div class="bull-box-period">${d.start_date} → ${d.end_date}</div>
          <div class="bull-box-symbol">NEPSE</div>
          <div class="bull-box-cagr" style="color:${cagrColor}">${d.cagr_pct >= 0 ? '+' : ''}${d.cagr_pct.toFixed(1)}% CAGR</div>
          <div class="bull-box-duration">⏱ ${d.years.toFixed(1)} yrs</div>
          <div class="bull-box-multi">📈 Index ${verb} ~${multX}${soFar}</div>
          <div class="bull-box-prices">Index: ${fmt(d.start_price)} → ${fmt(d.ltp)}</div>
        </div>`;
      }).join('');

      row.style.display = 'block';
      btn.textContent = '✕ Hide NEPSE';
      btn.disabled = false;
    }

    document.getElementById('bull-cycle-results').addEventListener('click', function(e) {
      const btn = e.target.closest('.perf-toggle-btn');
      if (!btn) return;
      const id = btn.dataset.perfId;
      const panel = document.getElementById(id);
      if (!panel) return;
      const isOpen = panel.classList.toggle('open');
      btn.classList.toggle('open', isOpen);
      btn.querySelector('span').textContent = isOpen ? '▲ Performance Details' : '▼ Performance Details';
    });

    async function resolveSymbol(query) {
      const port = await findPort();
      if (!port) return { error: 'Server not running.' };
      try {
        const resp = await fetch(`http://localhost:${port}/search?q=${encodeURIComponent(query)}&max_results=30`, { signal: AbortSignal.timeout(5000) });
        const data = await resp.json();
        if (data.error) return { error: data.error };
        return { results: data.results || [] };
      } catch(e) {
        return { error: e.message };
      }
    }

    async function resolveSymbolPage(query, offset, limit) {
      const port = await findPort();
      if (!port) return { error: 'Server not running.' };
      try {
        const resp = await fetch(`http://localhost:${port}/search?q=${encodeURIComponent(query)}&max_results=${limit}&offset=${offset}`, { signal: AbortSignal.timeout(5000) });
        const data = await resp.json();
        if (data.error) return { error: data.error };
        return { results: data.results || [] };
      } catch(e) {
        return { error: e.message };
      }
    }

    async function getTradingRange(symbol) {
      const port = await findPort();
      if (!port) return { first_date: null, last_date: null };
      try {
        const resp = await fetch(`http://localhost:${port}/trading_range?symbol=${encodeURIComponent(symbol)}`);
        const data = await resp.json();
        return data || { first_date: null, last_date: null };
      } catch(_) {
        return { first_date: null, last_date: null };
      }
    }

    async function resolveSymbolPage(query, offset, limit) {
      const port = await findPort();
      if (!port) return { error: 'Server not running.' };
      try {
        const resp = await fetch(`http://localhost:${port}/search?q=${encodeURIComponent(query)}&max_results=${limit}&offset=${offset}`);
        const data = await resp.json();
        if (data.error) return { error: data.error };
        return { results: data.results || [] };
      } catch(e) {
        return { error: e.message };
      }
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

    function localResolveSymbol(query) {
      const q = query.trim();
      const hit = LOCAL_NAME_ALIASES.find(item => item.pattern.test(q));
      return hit ? hit.symbol : null;
    }

    function localResolveCandidates(query) {
      const q = query.trim();
      const grouped = LOCAL_NAME_GROUPS.find(item => item.pattern.test(q));
      if (grouped) return grouped.items;
      return LOCAL_NAME_ALIASES
        .filter(item => item.pattern.test(q))
        .map(item => ({ symbol: item.symbol, name: item.symbol }));
    }

    function showSymbolPicker(candidates, onSelect) {
      const statusEl = document.getElementById('page-status');
      const list = candidates.map(c =>
        `<button class="picker-btn" data-symbol="${c.symbol}"><strong>${c.symbol}</strong> — ${c.name}</button>`
      ).join('');
      statusEl.innerHTML = `<div class="picker-wrap"><div class="picker-label">Multiple matches — pick one:</div>${list}</div>`;
      statusEl.querySelectorAll('.picker-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          statusEl.innerHTML = '';
          onSelect(btn.dataset.symbol);
        });
      });
    }

    function showPagedPicker(fetchPage, onSelect) {
      const statusEl = document.getElementById('page-status');
      let offset = 0;
      const pageSize = 10;

      async function render() {
        const { results, error } = await fetchPage(offset, pageSize);
        if (error) {
          statusEl.textContent = '❌ ' + error;
          return;
        }
        const list = results.map(c =>
          `<button class="picker-btn" data-symbol="${c.symbol}"><strong>${c.symbol}</strong> — ${c.name}</button>`
        ).join('');
        const moreBtn = results.length === pageSize ? `<button class="picker-btn picker-more-btn" data-more="1">Show 10 more</button>` : '';
        statusEl.innerHTML = `<div class="picker-wrap"><div class="picker-label">Multiple matches — pick one:</div>${list}${moreBtn}</div>`;
        statusEl.querySelectorAll('.picker-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            if (btn.dataset.more) {
              offset += pageSize;
              render();
              return;
            }
            statusEl.innerHTML = '';
            onSelect(btn.dataset.symbol);
          });
        });
      }

      render();
    }

    function showPagedPicker(fetchPage, onSelect) {
      const statusEl = document.getElementById('page-status');
      let offset = 0;
      const pageSize = 10;

      async function render() {
        const { results, error } = await fetchPage(offset, pageSize);
        if (error) {
          statusEl.textContent = '❌ ' + error;
          return;
        }
        const list = results.map(c =>
          `<button class="picker-btn" data-symbol="${c.symbol}"><strong>${c.symbol}</strong> — ${c.name}</button>`
        ).join('');
        const moreBtn = results.length === pageSize ? `<button class="picker-btn picker-more-btn" data-more="1">Show 10 more</button>` : '';
        statusEl.innerHTML = `<div class="picker-wrap"><div class="picker-label">Multiple matches — pick one:</div>${list}${moreBtn}</div>`;
        statusEl.querySelectorAll('.picker-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            if (btn.dataset.more) {
              offset += pageSize;
              render();
              return;
            }
            statusEl.innerHTML = '';
            onSelect(btn.dataset.symbol);
          });
        });
      }

      render();
    }

    async function resolveBullSymbol(query) {
      const localResults = localResolveCandidates(query);
      if (localResults.length > 1) return { results: localResults };
      if (localResults.length === 1) return { results: localResults };
      const { results, error } = await resolveSymbol(query);
      if (error) return { error };
      return { results: results || [] };
    }

    function showLtpWidget() {
      document.getElementById('date-ltp-wrap').classList.add('visible');
      document.getElementById('ltp-result').textContent = '';
    }

    async function runIndexBullBear(symbol) {
      lastSearchedSymbol = symbol;
      showLtpWidget();
      document.getElementById('search-input').value = symbol;
      document.getElementById('page-status').textContent = '';
      switchPage('bullbear');
      doBullSearch(symbol);
    }

    async function doSearch() {
      const query = document.getElementById('search-input').value.trim();
      if (!query) return;

      // Index tickers bypass fundamentals and go straight to bull/bear
      const upper = query.toUpperCase();
      if (INDEX_SYMBOL_MAP[upper]) {
        runIndexBullBear(upper);
        return;
      }

      document.getElementById('page-status').textContent = '⏳ Resolving...';
      document.getElementById('results-area').style.display = 'none';

      const { results, error } = await resolveSymbol(query);
      if (error) { document.getElementById('page-status').textContent = '❌ ' + error; return; }
      if (!results || results.length === 0) {
        const localResults = localResolveCandidates(query);
        if (localResults.length === 1) {
          runFundamentalsForSymbol(localResults[0].symbol);
          return;
        } else if (localResults.length > 1) {
          showPagedPicker(async (offset, limit) => {
            const page = localResults.slice(offset, offset + limit);
            return { results: page };
          }, sym => runFundamentalsForSymbol(sym));
          return;
        }
        document.getElementById('page-status').textContent = '❌ No company found for "' + query + '"';
        return;
      }

      if (results.length > 1) {
        showSymbolPicker(results, sym => runFundamentalsForSymbol(sym));
        return;
      }
      runFundamentalsForSymbol(results[0].symbol);
    }

    async function runFundamentalsForSymbol(symbol) {
      lastSearchedSymbol = symbol;
      showLtpWidget();
      document.getElementById('search-input').value = symbol;
      document.getElementById('page-status').textContent = '⏳ Fetching fundamentals...';
      document.getElementById('results-area').style.display = 'none';
      const port = await findPort();
      if (!port) {
        document.getElementById('page-status').textContent = '❌ Server not running. Restart engine from popup.';
        return;
      }
      let data;
      try {
        const resp = await fetch(`http://localhost:${port}/fundamentals?symbol=${encodeURIComponent(symbol)}`);
        data = await resp.json();
      } catch (e) {
        document.getElementById('page-status').textContent = '❌ ' + e.message;
        return;
      }
      if (!data || data.error) {
        document.getElementById('page-status').textContent = '❌ ' + (data && data.error || 'Error fetching fundamentals');
        return;
      }
      showFundamentals(data);
    }

    async function findPort() {
      for (let p = 5758; p <= 5768; p++) {
        try { const r = await fetch(`http://localhost:${p}/ping`, { signal: AbortSignal.timeout(300) }); if (r.ok) return p; } catch(_) {}
      }
      return null;
    }

    function fmt(n) { return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 }); }

    function fmtCompact(n) {
      if (n == null || isNaN(n)) return '—';
      const abs = Math.abs(n);
      if (abs >= 1e9) return (n / 1e9).toFixed(2) + ' Arba';
      if (abs >= 1e7) return (n / 1e7).toFixed(2) + ' Cr';
      if (abs >= 1e5) return (n / 1e5).toFixed(2) + ' Lakh';
      return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
    }

    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }

    function showFundamentals(d) {
      document.getElementById('page-status').textContent = '';
      document.getElementById('results-area').style.display = 'block';
      const merger = d.merger || (d.is_merged ? d : MERGED_COMPANIES[String(d.symbol || '').toUpperCase()] || null);
      const mergeStatus = d.merge_status || merger?.status || (d.is_merged ? 'closed' : null);
      const isClosedMerged = mergeStatus === 'closed' || (!!merger && !mergeStatus);
      const isSurvivor = mergeStatus === 'active_survivor';
      const isAcquisition = (d.event_type || merger?.event_type) === 'acquisition';
      const closedLabel = isAcquisition ? 'Acquired' : 'Merged';
      const closedPrep = isAcquisition ? 'Acquired by' : 'Merged to';

      // Hero
      const name = (d.company_name || d.symbol || '').replace(/\s*\([^)]*\)\s*$/, '').trim();
      setText('r-name', name);
      setText('r-symbol', d.symbol || '—');
      setText('r-sector', d.sector || 'NEPSE');
      setText('r-substext', [
        d.sector,
        d.shares_outstanding ? `${fmtCompact(d.shares_outstanding)} shares listed` : null,
        d.listing_date ? `Listed ${d.listing_date}` : null,
      ].filter(Boolean).join(' · ') || '—');

      // Logo: first 2 chars of ticker
      const logoEl = document.getElementById('r-logo');
      if (logoEl) logoEl.textContent = (d.symbol || '?').slice(0, 3);

      // Price
      setText('r-price', d.market_price != null ? fmt(d.market_price) : '—');
      const changeEl = document.getElementById('r-change');
      if (changeEl) {
        if (d.percent_change != null && !isNaN(d.percent_change)) {
          const up = d.percent_change >= 0;
          changeEl.textContent = (up ? '▲ +' : '▼ ') + d.percent_change.toFixed(2) + '%';
          changeEl.className = 'change ' + (up ? 'up' : 'down');
        } else {
          changeEl.textContent = '—';
          changeEl.className = 'change';
        }
      }
      setText('r-asof', d.last_traded_on ? `As of ${d.last_traded_on}` : '—');

      // Market status pill
      const pill = document.getElementById('r-mkt-pill');
      if (pill) {
        const isOpen = isMarketOpen();
        pill.classList.toggle('closed', !isOpen || isClosedMerged);
        setText('r-mkt-status', isClosedMerged ? closedLabel : (isSurvivor ? 'Survivor' : (isOpen ? 'Market open' : 'Market closed')));
      }

      // Quick stats
      let dayRange = '—';
      if (d.latest_day && d.latest_day.high && d.latest_day.low) {
        dayRange = `${fmt(d.latest_day.low)} – ${fmt(d.latest_day.high)}`;
      }
      setText('r-day-range', isClosedMerged ? '—' : dayRange);
      setText('r-52w-range', (d.high_52w && d.low_52w)
        ? `${fmt(d.low_52w)} – ${fmt(d.high_52w)}`
        : '—');
      setText('r-avg-vol', isClosedMerged ? '—' : (d.avg_volume_30d != null
        ? Number(d.avg_volume_30d).toLocaleString('en-IN', { maximumFractionDigits: 0 })
        : '—'));
      setText('r-1y-yield', isClosedMerged ? '—' : (d.year_yield_pct != null ? d.year_yield_pct.toFixed(2) + '%' : '—'));

      // FY meta header
      setText('r-fy-meta', isClosedMerged ? `${closedLabel} company` : (isSurvivor ? 'Surviving company' : (d.eps_fy ? `FY ${d.eps_fy}` : 'Latest data')));

      // Key metrics cards
      setText('r-mkt-cap', isClosedMerged ? closedLabel : (d.market_cap != null ? 'Rs. ' + fmtCompact(d.market_cap) : '—'));
      setText('r-mkt-cap-sub', d.shares_outstanding != null
        ? `${fmtCompact(d.shares_outstanding)} shares × Rs. ${fmt(d.market_price || 0)}`
        : '');

      const paidUp = d.shares_outstanding != null ? d.shares_outstanding * 100 : null;
      setText('r-paid-up', isClosedMerged ? closedLabel : (paidUp != null ? 'Rs. ' + fmtCompact(paidUp) : '—'));
      setText('r-paid-up-sub', isClosedMerged ? `${closedLabel} company` : (d.shares_outstanding != null
        ? `${fmtCompact(d.shares_outstanding)} shares · Rs. 100 face value`
        : ''));

      setText('r-pe', isClosedMerged ? '—' : (d.pe_ratio != null ? d.pe_ratio.toFixed(2) + '×' : '—'));
      setText('r-pe-sub', isClosedMerged ? `${closedLabel} company` : (d.pbv != null ? `P/B ${d.pbv.toFixed(2)}×` : ''));

      setText('r-eps', isClosedMerged ? '—' : (d.eps != null ? 'Rs. ' + d.eps.toFixed(2) : '—'));
      setText('r-eps-sub', isClosedMerged ? `${closedLabel} company` : (d.eps_fy ? `FY ${d.eps_fy}` : ''));

      setText('r-bvps', isClosedMerged ? '—' : (d.book_value != null ? 'Rs. ' + d.book_value.toFixed(2) : '—'));
      setText('r-bvps-sub', isClosedMerged ? `${closedLabel} company` : (d.pbv != null ? `Price-to-Book ${d.pbv.toFixed(2)}×` : ''));

      setText('r-listing', d.listing_date || '—');
      let listingSub = '';
      if (d.listing_date) {
        const yrs = (new Date() - new Date(d.listing_date)) / (1000 * 60 * 60 * 24 * 365.25);
        if (!isNaN(yrs) && yrs > 0) listingSub = `${yrs.toFixed(1)} years on NEPSE`;
      }
      if (isClosedMerged && (d.merged_date || merger.merged_date)) listingSub = `${closedLabel} on ${d.merged_date || merger.merged_date}`;
      if (isSurvivor && (d.merged_date || merger.merged_date)) listingSub = `Survived merger on ${d.merged_date || merger.merged_date}`;
      setText('r-listing-sub', listingSub);

      const mergeBanner = document.getElementById('r-merge-banner');
      if (mergeBanner) {
        if (isClosedMerged) {
          const survivorName = d.merged_to_name || merger.merged_to_name || d.merged_to || merger.merged_to || null;
          // Final survivor after walking multi-step merger chain (e.g. BOK -> BOKL -> GBIME).
          const hasChain = Array.isArray(d.merger_chain) && d.merger_chain.length > 1;
          const finalName = d.final_survivor_name || null;
          const finalSym = d.final_survivor_symbol || null;
          const showFinal = hasChain && finalSym && finalSym !== d.merged_to;
          const mergedSub = [
            d.listing_date ? `Listed <strong>${d.listing_date}</strong>` : null,
            (d.merged_date || merger.merged_date) ? `${closedLabel} <strong>${d.merged_date || merger.merged_date}</strong>` : null,
            survivorName ? `${closedPrep} <strong>${survivorName}</strong>${d.merged_to && d.merged_to !== survivorName ? ` (${d.merged_to})` : ''}` : null,
            showFinal ? `Now part of <strong>${finalName || finalSym}</strong> (${finalSym})${d.final_survivor_date ? ` since <strong>${d.final_survivor_date}</strong>` : ''}` : null
          ].filter(Boolean).join(' · ');
          const title = document.getElementById('r-merge-title');
          const sub = document.getElementById('r-merge-sub');
          if (title) title.textContent = d.merged_note || merger.note || (isAcquisition ? 'This company was acquired and is no longer actively trading.' : 'This company has been merged and is no longer actively trading.');
          if (sub) sub.innerHTML = mergedSub;
          mergeBanner.classList.add('show');
        } else if (isSurvivor) {
          const title = document.getElementById('r-merge-title');
          const sub = document.getElementById('r-merge-sub');
          if (title) title.textContent = d.merged_note || merger.note || 'This company survived a merger and remains active.';
          if (sub) sub.innerHTML = [
            d.merged_date || merger.merged_date ? `Merger date <strong>${d.merged_date || merger.merged_date}</strong>` : null,
            d.merged_from_name || merger.merged_from_name || d.merged_from || merger.merged_from ? `Merged from <strong>${d.merged_from_name || merger.merged_from_name || d.merged_from || merger.merged_from}</strong>` : null,
            d.surviving_name || merger.surviving_name ? `Now operating as <strong>${d.surviving_name || merger.surviving_name}</strong>` : null,
          ].filter(Boolean).join(' · ');
          mergeBanner.classList.add('show');
        } else {
          mergeBanner.classList.remove('show');
        }
      }

      if (isClosedMerged) {
        setText('r-price', closedLabel);
        const changeEl = document.getElementById('r-change');
        if (changeEl) {
          changeEl.textContent = 'Closed';
          changeEl.className = 'change down';
        }
        setText('r-asof', d.merged_date || merger.merged_date ? `${closedLabel} on ${d.merged_date || merger.merged_date}` : closedLabel);
        const dayRange = document.getElementById('r-day-range');
        const w52Range = document.getElementById('r-52w-range');
        const avgVol = document.getElementById('r-avg-vol');
        const yYield = document.getElementById('r-1y-yield');
        if (dayRange) dayRange.textContent = '—';
        if (w52Range) w52Range.textContent = '—';
        if (avgVol) avgVol.textContent = '—';
        if (yYield) yYield.textContent = '—';
      } else if (isSurvivor) {
        const changeEl = document.getElementById('r-change');
        if (changeEl) {
          changeEl.textContent = 'Active survivor';
          changeEl.className = 'change up';
        }
      }

      // Shareholding donut
      renderShareholdingDonut(d);

      // Footer
      setText('r-scraped-at', d.scraped_at ? d.scraped_at.replace('T', ' ') : '—');
      const srcLink = document.getElementById('r-source-link');
      if (srcLink && d.symbol) {
        srcLink.href = `https://merolagani.com/CompanyDetail.aspx?symbol=${d.symbol}`;
      }
    }

    function renderShareholdingDonut(d) {
      const hasData = d.promoter_pct != null && d.public_pct != null;
      const promoterPct = hasData ? d.promoter_pct : 0;
      const publicPct = hasData ? d.public_pct : 0;

      // Center text shows promoter %
      setText('r-donut-center', hasData ? promoterPct.toFixed(1) + '%' : '—');

      // SVG donut arcs (circumference = 100 since r=15.915)
      const promoterCircle = document.getElementById('r-donut-promoter');
      const publicCircle = document.getElementById('r-donut-public');
      if (promoterCircle) {
        promoterCircle.setAttribute('stroke-dasharray', `${promoterPct} ${100 - promoterPct}`);
        promoterCircle.setAttribute('stroke-dashoffset', '25');
      }
      if (publicCircle) {
        publicCircle.setAttribute('stroke-dasharray', `${publicPct} ${100 - publicPct}`);
        publicCircle.setAttribute('stroke-dashoffset', String(25 - promoterPct));
      }

      // Legend
      setText('r-promoter-pct', hasData ? promoterPct.toFixed(2) + '%' : '—');
      setText('r-public-pct', hasData ? publicPct.toFixed(2) + '%' : '—');
      setText('r-promoter-shares', d.promoter_shares != null
        ? Number(d.promoter_shares).toLocaleString('en-IN')
        : '—');
      setText('r-public-shares', d.public_shares != null
        ? Number(d.public_shares).toLocaleString('en-IN')
        : '—');

      // Segmented bar
      const segP = document.getElementById('r-seg-promoter');
      const segPub = document.getElementById('r-seg-public');
      if (segP) segP.style.width = promoterPct + '%';
      if (segPub) segPub.style.width = publicPct + '%';
      setText('r-seg-note', hasData
        ? `Promoter ${promoterPct.toFixed(1)}% · Public ${publicPct.toFixed(1)}%`
        : 'Shareholding data unavailable');
    }

    function isMarketOpen() {
      // NEPSE trading: Sun–Thu 11:00–15:00 NPT (UTC+5:45). Closed Fri/Sat.
      const now = new Date();
      const nptMs = now.getTime() + (now.getTimezoneOffset() + 345) * 60 * 1000;
      const npt = new Date(nptMs);
      const day = npt.getUTCDay(); // 0=Sun, 5=Fri, 6=Sat
      if (day === 5 || day === 6) return false;
      const hh = npt.getUTCHours();
      const mm = npt.getUTCMinutes();
      const mins = hh * 60 + mm;
      return mins >= 11 * 60 && mins <= 15 * 60;
    }

    // ── Bull & Bear Chart ──
    let bbChart = null;

    // Estimated data 1994–2000 (no official daily records; approximate based on known start 100pts Jan 1994)
    const estLabels = ["1994-01-13","1994-07-01","1995-01-01","1995-07-01","1996-01-01","1996-07-01","1997-01-01","1997-07-01","1998-01-01","1998-07-01","1999-01-01","1999-07-01","2000-01-01","2000-07-01"];
    const estValues = [100,116,134,152,175,215,248,285,315,332,342,350,358,348];

    const chartLabels = ["2000-11-23", "2001-07-10", "2002-03-15", "2002-08-26", "2003-01-24", "2004-04-01", "2004-07-06", "2005-05-04", "2006-05-15", "2006-08-03", "2007-07-16", "2007-12-17", "2008-08-31", "2009-01-21", "2009-07-20", "2010-04-28", "2010-07-18", "2011-01-31", "2011-02-28", "2011-03-31", "2011-04-28", "2011-05-31", "2011-06-30", "2011-07-31", "2011-08-30", "2011-09-29", "2011-10-31", "2011-11-28", "2011-12-29", "2012-01-31", "2012-02-29", "2012-03-29", "2012-04-30", "2012-05-31", "2012-06-28", "2012-07-31", "2012-08-30", "2012-09-30", "2012-10-31", "2012-11-29", "2012-12-31", "2013-01-31", "2013-02-28", "2013-03-31", "2013-04-30", "2013-05-30", "2013-06-30", "2013-07-31", "2013-08-29", "2013-09-30", "2013-10-31", "2013-11-28", "2013-12-31", "2014-01-29", "2014-02-26", "2014-03-31", "2014-04-30", "2014-05-28", "2014-06-30", "2014-07-31", "2014-08-31", "2014-09-30", "2014-10-30", "2014-11-30", "2014-12-31", "2015-01-29", "2015-02-26", "2015-03-31", "2015-04-23", "2015-05-31", "2015-06-30", "2015-07-30", "2015-08-31", "2015-09-30", "2015-10-29", "2015-11-30", "2015-12-31", "2016-01-31", "2016-02-29", "2016-03-31", "2016-04-28", "2016-05-31", "2016-06-30", "2016-07-27", "2016-07-31", "2016-08-31", "2016-09-29", "2016-10-27", "2016-11-30", "2016-12-29", "2017-01-31", "2017-02-28", "2017-03-30", "2017-04-30", "2017-05-31", "2017-06-28", "2017-07-31", "2017-08-31", "2017-09-26", "2017-10-31", "2017-11-30", "2017-12-31", "2018-01-31", "2018-02-28", "2018-03-29", "2018-04-29", "2018-05-31", "2018-06-28", "2018-07-31", "2018-08-30", "2018-09-30", "2018-10-31", "2018-11-29", "2018-12-31", "2019-01-31", "2019-02-27", "2019-03-05", "2019-03-31", "2019-04-30", "2019-05-30", "2019-06-30", "2019-07-31", "2019-08-29", "2019-09-30", "2019-10-31", "2019-11-28", "2019-12-31", "2020-01-30", "2020-02-27", "2020-03-22", "2020-05-13", "2020-06-30", "2020-07-30", "2020-08-31", "2020-09-30", "2020-10-29", "2020-11-30", "2020-12-31", "2021-01-31", "2021-02-28", "2021-03-31", "2021-04-29", "2021-05-31", "2021-06-30", "2021-07-29", "2021-08-18", "2021-08-31", "2021-09-30", "2021-10-31", "2021-11-30", "2021-12-29", "2022-01-31", "2022-02-28", "2022-03-31", "2022-04-28", "2022-05-31", "2022-06-30", "2022-07-31", "2022-08-31", "2022-09-25", "2022-09-29", "2022-10-31", "2022-11-30", "2022-12-29", "2023-01-31", "2023-02-28", "2023-03-30", "2023-04-30", "2023-05-31", "2023-06-28", "2023-07-31", "2023-08-30", "2023-09-27", "2023-10-31", "2023-11-30", "2023-12-28", "2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30", "2024-05-30", "2024-06-30", "2024-07-31", "2024-08-15", "2024-08-29", "2024-09-30", "2024-10-30", "2024-11-28", "2024-12-31", "2025-01-28", "2025-02-27", "2025-03-30", "2025-04-30", "2025-05-28", "2025-06-30", "2025-07-27", "2025-07-31", "2025-08-31", "2025-09-28", "2025-10-30", "2025-11-30", "2025-12-31", "2026-01-29", "2026-02-26", "2026-03-31", "2026-04-30", "2026-05-06"];
    const chartValues = [545.82, 322.74, 186.22, 230.01, 198.44, 195.14, 227.83, 298.78, 388.49, 355.6, 683.95, 1064.09, 1175.38, 609.46, 739.02, 405.45, 468.53, 410.57, 391.66, 365.0, 348.0, 337.0, 337.0, 359.0, 340.0, 331.0, 330.0, 323.0, 316.0, 316.0, 315.0, 299.0, 405.0, 374.0, 377.0, 401.0, 406.0, 415.0, 451.0, 489.0, 534.0, 511.0, 542.0, 511.0, 501.0, 500.0, 493.0, 548.0, 551.0, 542.0, 579.0, 644.0, 771.0, 781.0, 826.0, 792.0, 823.0, 867.0, 946.0, 1066.0, 953.0, 938.0, 930.0, 857.0, 902.0, 987.0, 979.0, 946.0, 938.0, 872.0, 949.0, 1028.0, 1200.0, 1181.28, 1092.04, 1034.12, 1151.38, 1220.7, 1283.94, 1355.48, 1464.91, 1532.12, 1723.23, 1881.45, 1862.76, 1797.45, 1753.38, 1759.71, 1608.33, 1443.38, 1326.6, 1299.29, 1587.64, 1650.78, 1608.11, 1563.81, 1652.69, 1580.03, 1549.46, 1533.53, 1537.67, 1390.58, 1404.49, 1345.99, 1220.29, 1349.01, 1307.66, 1198.54, 1191.47, 1181.69, 1256.71, 1221.46, 1148.36, 1188.19, 1161.63, 1105.53, 1098.95, 1143.09, 1298.6, 1319.47, 1244.89, 1265.57, 1196.41, 1135.56, 1146.17, 1112.79, 1166.03, 1325.38, 1632.17, 1251.45, 1201.57, 1260.75, 1439.06, 1484.99, 1550.43, 1645.67, 1997.05, 2087.27, 2370.54, 2474.39, 2619.03, 2611.1, 2782.68, 2823.87, 3079.83, 3198.6, 2975.84, 2633.42, 2837.61, 2628.37, 2524.5, 2872.05, 2610.58, 2544.31, 2356.17, 2137.92, 2037.64, 2195.1, 1973.38, 1815.13, 1853.76, 1874.88, 1949.85, 2029.03, 2111.68, 2019.93, 1908.55, 1870.65, 1849.79, 2150.99, 2106.18, 1990.59, 2004.3, 1864.4, 1858.53, 2068.9, 2097.93, 1972.09, 2018.33, 2006.28, 2069.53, 2037.09, 2760.9, 3000.81, 2749.57, 2508.86, 2677.62, 2748.05, 2576.5, 2657.77, 2815.04, 2693.12, 2623.83, 2693.06, 2631.48, 3002.00, 2922.63, 2749.83, 2663.51, 2600.38, 2649.52, 2633.76, 2714.05, 2654.93, 2851.09, 2738.72, 2711.22];

    // Key market turning points (all cycles)
    const bullTops = [
      { date: "2000-11-23", value: 545.82,   label: "Bull 1 Top\n546" },
      { date: "2008-08-31", value: 1175.38,  label: "Bull 2 Top\n1,175" },
      { date: "2016-07-27", value: 1881.45,  label: "Bull 3 Top\n1,881" },
      { date: "2021-08-18", value: 3198.60,  label: "Bull 4 Top\n3,199" },
      { date: "2024-08-15", value: 3000.81,  label: "Bull 5 Peak\n3,001" },
      { date: "2025-07-27", value: 3002.00,  label: "Bull 5 Peak\n3,002" },
    ];
    const bearBottoms = [
      { date: "2002-03-15", value: 186.22,  label: "Bear 1\n186" },
      { date: "2012-03-29", value: 299.0,   label: "Bear 2\n299" },
      { date: "2019-03-05", value: 1098.95, label: "Bear 3\n1,099" },
      { date: "2022-09-25", value: 1815.13, label: "Bear 4\n1,815" },
    ];

    // Bull cycle date ranges for background shading
    const bullCycles = [
      { start: "1994-01-13", end: "2000-11-23", label: "Bull 1", color: "rgba(78,205,196,0.13)" },
      { start: "2002-03-15", end: "2008-08-31", label: "Bull 2", color: "rgba(102,187,106,0.13)" },
      { start: "2012-03-29", end: "2016-07-31", label: "Bull 3", color: "rgba(255,193,7,0.11)"   },
      { start: "2019-03-05", end: "2021-08-18", label: "Bull 4", color: "rgba(171,71,188,0.13)"  },
      { start: "2022-09-25", end: "2099-01-01", label: "Bull 5", color: "rgba(78,205,196,0.09)"  },
    ];

    const bullCyclePlugin = {
      id: 'bullCycles',
      beforeDraw(chart) {
        const { ctx, scales: { x, y }, chartArea } = chart;
        const labels = chart.data.labels;
        bullCycles.forEach(cycle => {
          // Find nearest label indices
          let si = labels.findIndex(l => l >= cycle.start);
          let ei = labels.findIndex(l => l >= cycle.end);
          if (si === -1) si = 0;
          if (ei === -1) ei = labels.length - 1;
          if (si > ei) return;
          const x0 = x.getPixelForValue(si);
          const x1 = x.getPixelForValue(ei);
          ctx.save();
          ctx.fillStyle = cycle.color;
          ctx.fillRect(x0, chartArea.top, x1 - x0, chartArea.height);
          // Label at top
          ctx.fillStyle = isDark ? 'rgba(205,217,229,0.55)' : 'rgba(7,54,66,0.45)';
          ctx.font = 'bold 11px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(cycle.label, (x0 + x1) / 2, chartArea.top + 16);
          ctx.restore();
        });
      }
    };

    function buildChart() {
      if (bbChart) { bbChart.destroy(); bbChart = null; }
      const lineColor = isDark ? '#5b9cff' : '#2a6fdb';
      const estColor  = isDark ? 'rgba(91,156,255,0.5)' : 'rgba(42,111,219,0.5)';
      const gridColor = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)';
      const textColor = isDark ? '#7a9bb5' : '#657b83';

      // Combined labels: estimated (pre-2000) + actual
      const allLabels = [...estLabels, ...chartLabels];
      // Estimated dataset: values for est period, null for actual
      const estData   = [...estValues, ...chartLabels.map(() => null)];
      // Actual dataset: null for est period, values for actual
      const actualData = [...estLabels.map(() => null), ...chartValues];

      const bullPointData = allLabels.map((l, i) => bullTops.find(b => b.date === l) ? actualData[i] : null);
      const bearPointData = allLabels.map((l, i) => bearBottoms.find(b => b.date === l) ? actualData[i] : null);

      bbChart = new Chart(document.getElementById('bb-chart'), {
        type: 'line',
        plugins: [bullCyclePlugin],
        data: {
          labels: allLabels,
          datasets: [
            {
              label: 'NEPSE (estimated)',
              data: estData,
              borderColor: estColor,
              borderWidth: 2,
              borderDash: [6, 4],
              pointRadius: 0,
              pointHoverRadius: 3,
              fill: false,
              tension: 0.4,
              spanGaps: false,
            },
            {
              label: 'NEPSE Index',
              data: actualData,
              borderColor: lineColor,
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
              fill: true,
              backgroundColor: isDark ? 'rgba(78,205,196,0.04)' : 'rgba(42,161,152,0.04)',
              tension: 0.3,
              spanGaps: false,
            },
            {
              label: 'Bull Top',
              data: bullPointData,
              borderColor: 'transparent',
              backgroundColor: isDark ? '#2ecc71' : '#0a8a4a',
              pointRadius: 8,
              pointStyle: 'triangle',
              pointHoverRadius: 10,
              showLine: false,
            },
            {
              label: 'Bear Bottom',
              data: bearPointData,
              borderColor: 'transparent',
              backgroundColor: isDark ? '#ff5a5a' : '#c63b3b',
              pointRadius: 8,
              pointStyle: 'triangle',
              rotation: 180,
              pointHoverRadius: 10,
              showLine: false,
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: ctx => ctx[0].label,
                label: ctx => {
                  if (ctx.datasetIndex === 0 && ctx.parsed.y) return ' NEPSE (est.): ' + ctx.parsed.y.toLocaleString();
                  if (ctx.datasetIndex === 1 && ctx.parsed.y) return ' NEPSE: ' + ctx.parsed.y.toLocaleString();
                  if (ctx.datasetIndex === 2 && ctx.parsed.y) return ' 🐂 Bull Top: ' + ctx.parsed.y.toLocaleString();
                  if (ctx.datasetIndex === 3 && ctx.parsed.y) return ' 🐻 Bear Bottom: ' + ctx.parsed.y.toLocaleString();
                  if (ctx.dataset.label === 'Ticker' && ctx.parsed.y) return ' 📈 ' + ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString();
                  return null;
                },
                filter: item => item.parsed.y !== null
              }
            }
          },
          scales: {
            x: {
              ticks: {
                color: textColor,
                maxTicksLimit: 14,
                maxRotation: 0,
                callback: (val, idx) => {
                  const d = allLabels[idx];
                  return d ? d.substring(0, 7) : '';
                }
              },
              grid: { color: gridColor }
            },
            y: {
              ticks: { color: textColor, callback: v => v.toLocaleString() },
              grid: { color: gridColor }
            }
          }
        }
      });
    }

    // ── Current-ticker overlay on the bull/bear chart ──
    const TICKER_OVERLAY_LABEL = 'Ticker';
    const TICKER_OVERLAY_COLOR = '#e67e22';

    async function toggleTickerOverlay() {
      if (!bbChart) return;
      const btn = document.getElementById('overlay-ticker-btn');
      const existingIdx = bbChart.data.datasets.findIndex(d => d.label === TICKER_OVERLAY_LABEL);

      // Toggle off if already shown
      if (existingIdx !== -1) {
        bbChart.data.datasets.splice(existingIdx, 1);
        if (bbChart.options.scales.yTicker) delete bbChart.options.scales.yTicker;
        bbChart.update();
        btn.style.background = 'transparent';
        btn.style.color = TICKER_OVERLAY_COLOR;
        btn.textContent = '📈 Overlay current ticker';
        return;
      }

      const sym = lastSearchedSymbol;
      if (!sym) { alert('Search a ticker first, then overlay it.'); return; }

      btn.textContent = '⏳ Loading…';
      try {
        const port = await findPort();
        if (!port) throw new Error('Server not running');
        const resp = await fetch(`http://localhost:${port}/series?symbol=${encodeURIComponent(sym)}&adjusted=1`, { signal: AbortSignal.timeout(8000) });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        const points = data.points || [];
        if (!points.length) throw new Error('No price data');

        // Map ticker close onto the chart's existing labels (last close on/before each label date)
        const labels = bbChart.data.labels;
        let pi = 0;
        const mapped = labels.map(lbl => {
          while (pi < points.length && points[pi].date <= lbl) pi++;
          return pi > 0 ? points[pi - 1].close : null;
        });

        bbChart.options.scales.yTicker = {
          position: 'right',
          ticks: { color: TICKER_OVERLAY_COLOR, callback: v => v.toLocaleString() },
          grid: { drawOnChartArea: false },
          title: { display: true, text: `${sym} adj. (bonus+div)`, color: TICKER_OVERLAY_COLOR },
        };
        bbChart.data.datasets.push({
          label: TICKER_OVERLAY_LABEL,
          data: mapped,
          borderColor: TICKER_OVERLAY_COLOR,
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          fill: false,
          tension: 0.3,
          spanGaps: true,
          yAxisID: 'yTicker',
        });
        bbChart.update();
        btn.style.background = TICKER_OVERLAY_COLOR;
        btn.style.color = '#fff';
        btn.textContent = `✕ Remove ${sym}`;
      } catch (err) {
        btn.textContent = '📈 Overlay current ticker';
        alert(`Could not overlay ticker: ${err.message}`);
      }
    }

    // ── FD interest-rate overlay chart ──
    let fdChart = null;

    async function fetchInterestRates() {
      try {
        const port = await findPort();
        if (!port) return [];
        const resp = await fetch(`http://localhost:${port}/interest_rates`, { signal: AbortSignal.timeout(5000) });
        if (!resp.ok) return [];
        const data = await resp.json();
        return Array.isArray(data.rates) ? data.rates : [];
      } catch (_) {
        return [];
      }
    }

    async function buildFdChart() {
      if (fdChart) { fdChart.destroy(); fdChart = null; }
      const lineColor = isDark ? '#5b9cff' : '#2a6fdb';
      const estColor  = isDark ? 'rgba(91,156,255,0.5)' : 'rgba(42,111,219,0.5)';
      const fdColor   = isDark ? '#f0a500' : '#e07b39';
      const gridColor = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)';
      const textColor = isDark ? '#7a9bb5' : '#657b83';

      const allLabels = [...estLabels, ...chartLabels];
      const estData    = [...estValues, ...chartLabels.map(() => null)];
      const actualData = [...estLabels.map(() => null), ...chartValues];

      // Map each FD rate onto the nearest chart label index (forward-fill axis).
      const rates = await fetchInterestRates();
      const fdData = allLabels.map(() => null);
      rates.forEach(r => {
        if (!r.date) return;
        let idx = allLabels.findIndex(l => l >= r.date);
        if (idx === -1) idx = allLabels.length - 1;
        fdData[idx] = r.rate;
      });

      const noteEl = document.getElementById('fd-rates-note');
      if (rates.length === 0 && noteEl) {
        noteEl.textContent = '⚠️ No interest-rate data available (server offline or empty dataset).';
      }

      fdChart = new Chart(document.getElementById('fd-chart'), {
        type: 'line',
        plugins: [bullCyclePlugin],
        data: {
          labels: allLabels,
          datasets: [
            {
              label: 'NEPSE Index', data: actualData, borderColor: lineColor,
              borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, fill: true,
              backgroundColor: isDark ? 'rgba(78,205,196,0.04)' : 'rgba(42,161,152,0.04)',
              tension: 0.3, spanGaps: false, yAxisID: 'y',
            },
            {
              label: 'FD / Deposit Rate (%)', data: fdData, borderColor: fdColor,
              backgroundColor: 'transparent', borderWidth: 2,
              pointRadius: 0, pointHoverRadius: 4,
              tension: 0.3, spanGaps: true, yAxisID: 'y1',
            },
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: true, labels: { color: textColor, usePointStyle: true, boxWidth: 8 } },
            tooltip: {
              callbacks: {
                title: ctx => ctx[0].label,
                label: ctx => {
                  if (ctx.parsed.y == null) return null;
                  if (ctx.datasetIndex === 0) return ' NEPSE: ' + ctx.parsed.y.toLocaleString();
                  if (ctx.datasetIndex === 1) return ' Deposit rate: ' + ctx.parsed.y + '%';
                  return null;
                },
                filter: item => item.parsed.y !== null
              }
            }
          },
          scales: {
            x: {
              ticks: {
                color: textColor, maxTicksLimit: 14, maxRotation: 0,
                callback: (val, idx) => { const d = allLabels[idx]; return d ? d.substring(0, 7) : ''; }
              },
              grid: { color: gridColor }
            },
            y: {
              position: 'left',
              ticks: { color: textColor, callback: v => v.toLocaleString() },
              grid: { color: gridColor },
              title: { display: true, text: 'NEPSE Index', color: textColor }
            },
            y1: {
              position: 'right',
              ticks: { color: fdColor, callback: v => v + '%' },
              grid: { drawOnChartArea: false },
              title: { display: true, text: 'Deposit Rate %', color: fdColor },
              suggestedMin: 0, suggestedMax: 14,
            }
          }
        }
      });
    }


        // ── CAGR page period toggle ──
    let cagrUseYears = true;
    document.getElementById('cagr-years-btn').onclick = () => {
      cagrUseYears = true;
      document.getElementById('cagr-years-btn').classList.add('active');
      document.getElementById('cagr-date-btn').classList.remove('active');
      document.getElementById('cagr-years').style.display = '';
      document.getElementById('cagr-date-section').style.display = 'none';
    };
    document.getElementById('cagr-date-btn').onclick = () => {
      cagrUseYears = false;
      document.getElementById('cagr-date-btn').classList.add('active');
      document.getElementById('cagr-years-btn').classList.remove('active');
      document.getElementById('cagr-years').style.display = 'none';
      document.getElementById('cagr-date-section').style.display = 'block';
    };
    document.getElementById('cagr-end-clear').onclick = () => {
      document.getElementById('cagr-end-date').value = '';
    };

    // ── CAGR calculate ──
    document.getElementById('cagr-btn').onclick = doCagr;
    document.getElementById('cagr-symbol').addEventListener('keydown', e => { if (e.key === 'Enter') doCagr(); });

    async function doCagr() {
      const query = document.getElementById('cagr-symbol').value.trim();
      if (!query) return;
      document.getElementById('cagr-status').textContent = '⏳ Resolving...';
      document.getElementById('cagr-results-area').style.display = 'none';

      const { results, error } = await resolveSymbol(query);
      if (error) { document.getElementById('cagr-status').textContent = '❌ ' + error; return; }
      if (!results || results.length === 0) {
        const localResults = localResolveCandidates(query);
        if (localResults.length === 1) {
          runCagrCalc(localResults[0].symbol);
          return;
        } else if (localResults.length > 1) {
          const statusEl = document.getElementById('cagr-status');
          const list = localResults.map(c =>
            `<button class="picker-btn" data-symbol="${c.symbol}"><strong>${c.symbol}</strong> — ${c.name}</button>`
          ).join('');
          statusEl.innerHTML = `<div class="picker-wrap"><div class="picker-label">Multiple matches — pick one:</div>${list}</div>`;
          statusEl.querySelectorAll('.picker-btn').forEach(btn => {
            btn.addEventListener('click', () => { statusEl.innerHTML = ''; runCagrCalc(btn.dataset.symbol); });
          });
          return;
        }
        document.getElementById('cagr-status').textContent = '❌ No company found for "' + query + '"';
        return;
      }

      if (results.length > 1) {
        const statusEl = document.getElementById('cagr-status');
        const list = results.map(c =>
          `<button class="picker-btn" data-symbol="${c.symbol}"><strong>${c.symbol}</strong> — ${c.name}</button>`
        ).join('');
        statusEl.innerHTML = `<div class="picker-wrap"><div class="picker-label">Multiple matches — pick one:</div>${list}</div>`;
        statusEl.querySelectorAll('.picker-btn').forEach(btn => {
          btn.addEventListener('click', () => { statusEl.innerHTML = ''; runCagrCalc(btn.dataset.symbol); });
        });
        return;
      }
      runCagrCalc(results[0].symbol);
    }

    async function runCagrCalc(symbol) {
      document.getElementById('cagr-symbol').value = symbol;
      const investment = parseFloat(document.getElementById('cagr-invest').value) || 100000;
      const payload = { symbol, investment };
      if (cagrUseYears) {
        payload.years = parseFloat(document.getElementById('cagr-years').value) || 5;
      } else {
        payload.start_date = document.getElementById('cagr-date').value;
        const endDateVal = document.getElementById('cagr-end-date').value;
        if (endDateVal) payload.end_date = endDateVal;
      }

      document.getElementById('cagr-status').textContent = '⏳ Calculating...';
      document.getElementById('cagr-results-area').style.display = 'none';

      let port = await findPort();
      let data;
      if (port) {
        try {
          const resp = await fetch(`http://localhost:${port}/cagr`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
          data = await resp.json();
        } catch(e) { document.getElementById('cagr-status').textContent = '❌ ' + e.message; return; }
      } else {
        document.getElementById('cagr-status').textContent = '⚙️ Starting engine...';
        data = await new Promise(resolve => { chrome.runtime.sendMessage({ action: 'cagrViaNative', payload }, resolve); });
      }
      if (!data || data.error) { document.getElementById('cagr-status').textContent = '❌ ' + (data?.error || 'Error'); return; }
      showCagrResults(data);
    }

    function showCagrResults(d) {
      document.getElementById('cagr-status').textContent = '';
      document.getElementById('cagr-results-area').style.display = 'block';
      document.getElementById('cr-symbol').textContent = d.symbol;
      const el = document.getElementById('cr-cagr');
      el.textContent = (d.cagr_pct >= 0 ? '+' : '') + d.cagr_pct.toFixed(2) + '%';
      el.className = 'cagr-hero-value ' + (d.cagr_pct >= 0 ? 'pos' : 'neg');
      document.getElementById('cr-meta').textContent = `${d.start_date} → ${d.end_date}  (${d.years} years)`;
      document.getElementById('cr-start-price').textContent = 'Rs. ' + fmt(d.start_price);
      document.getElementById('cr-ltp').textContent         = 'Rs. ' + fmt(d.ltp);
      document.getElementById('cr-units').textContent       = d.total_units_today + ' kitta';
      document.getElementById('cr-market').textContent      = 'Rs. ' + fmt(d.market_value);
      document.getElementById('cr-divs').textContent        = 'Rs. ' + fmt(d.total_cash_dividends);
      document.getElementById('cr-today').textContent       = 'Rs. ' + fmt(d.todays_value);
      document.getElementById('cr-invest').textContent      = 'Rs. ' + fmt(d.initial_investment);
      document.getElementById('cr-years').textContent       = d.years + ' yrs';
      const tbody = document.getElementById('cr-events');
      tbody.innerHTML = '';
      if (d.events && d.events.length > 0) {
        d.events.forEach(ev => {
          const tr = document.createElement('tr');
          const badge = ev.type === 'bonus'
            ? `<span class="badge badge-bonus">Bonus ${(ev.pct*100).toFixed(0)}%</span>`
            : `<span class="badge badge-cash">Cash ${(ev.pct*100).toFixed(1)}%</span>`;
          tr.innerHTML = `<td>${ev.date}</td><td>${badge}</td><td>${ev.fiscal_year || '—'}</td><td>${ev.units_after.toFixed(4)}</td><td>${ev.type === 'cash' ? 'Rs. ' + fmt(ev.cash_rs) : '—'}</td>`;
          tbody.appendChild(tr);
        });
      } else {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--label);padding:16px">No events in this period</td></tr>';
      }
    }

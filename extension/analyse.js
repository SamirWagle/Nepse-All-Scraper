    // ── Page switching ──
    const backDestination = { buffett: 'nexttop', nexttop: 'bullbear' };
    let lastSearchedSymbol = null;
    function switchPage(name) {
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      document.getElementById('page-' + name).classList.add('active');
      document.getElementById('analyse-menu').classList.remove('open');
      document.getElementById('analyse-trigger').classList.remove('open');
      document.getElementById('back-btn').style.display = name === 'analyse' ? 'none' : 'inline-block';
      if (name === 'bullbear') {
        buildChart();
        const sym = lastSearchedSymbol || document.getElementById('search-input').value.trim().toUpperCase();
        if (sym) doBullSearch(sym);
      }
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
      doSearch();
    });
    document.getElementById('menu-bullbear').addEventListener('click', (e) => {
      e.stopPropagation();
      switchPage('bullbear');
    });
    document.getElementById('menu-cagr').addEventListener('click', (e) => {
      e.stopPropagation();
      switchPage('cagr');
    });
    document.getElementById('nexttop-btn').addEventListener('click', () => {
      switchPage('nexttop');
    });

    // ── Cycle modals ──
    const modalOverlay = document.getElementById('cycle-modal-overlay');
    const modalTitle   = document.getElementById('cycle-modal-title');
    const modalBody    = document.getElementById('cycle-modal-body');

    function showCycleModal(title, rows, cls) {
      const accent = cls === 'bull' ? '#4ecdc4' : '#ff6b6b';
      const isLight = document.documentElement.classList.contains('light');
      const boxBg      = isLight ? '#1a3a2a' : 'var(--card)';
      const boxBorder  = isLight ? '#2d5a3d' : 'var(--border)';
      const labelColor = isLight ? '#7ab898' : 'var(--label)';
      const textColor  = isLight ? '#e0ede6' : 'var(--text)';
      document.getElementById('cycle-modal-box').style.background = boxBg;
      document.getElementById('cycle-modal-box').style.borderColor = boxBorder;
      modalTitle.style.color = accent;
      modalTitle.textContent = title;
      modalBody.innerHTML = rows.map((r, i) =>
        `<tr style="border-bottom:1px solid ${boxBorder}">
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
    document.getElementById('buffett-link').addEventListener('click', (e) => {
      e.preventDefault();
      switchPage('buffett');
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
      { num: 1, label: 'Bull 1', period: '~1994–2000', blank: true, reason: 'Pre-digital era' },
      { num: 2, label: 'Bull 2', period: '2002–2008',  blank: true, reason: 'Historical data unavailable' },
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

      // Fetch listing date first so we can skip cycles that ended before the stock existed
      let listingDate = null;
      try {
        const probe = { symbol, investment: 100000, start_date: '1994-01-01' };
        let probeData;
        if (port) {
          const r = await fetch(`http://localhost:${port}/cagr`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(probe),
          });
          probeData = await r.json();
        } else {
          probeData = await new Promise(resolve => chrome.runtime.sendMessage({ action: 'cagrViaNative', payload: probe }, resolve));
        }
        if (probeData && !probeData.error) listingDate = probeData.start_date;
      } catch(_) {}

      const fetchable = BULL_CYCLES_DEF.filter(c => !c.blank);

      const fetched = await Promise.all(fetchable.map(async cycle => {
        // Cycle ended before stock was listed — skip fetching, mark as not listed
        if (listingDate && cycle.end && cycle.end < listingDate) {
          return { num: cycle.num, data: { notListed: true, listingDate } };
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
          return `<div class="bull-box bull-box-blank">
            <div class="bull-box-title">${cycle.label}</div>
            <div class="bull-box-period">${cycle.period}</div>
            <div class="bull-box-na">—</div>
            <div class="bull-box-note">Not listed yet<br><span style="font-size:10px">Listed: ${d.listingDate}</span></div>
          </div>`;
        }
        if (!d || d.error) {
          return `<div class="bull-box bull-box-blank">
            <div class="bull-box-title">${cycle.label}</div>
            <div class="bull-box-period">${cycle.period}</div>
            <div class="bull-box-na">❌</div>
            <div class="bull-box-note">${d?.error || 'No data'}</div>
          </div>`;
        }
        const ratio = d.todays_value / d.initial_investment;
        const multX = ratio >= 2 ? Math.round(ratio) + 'x' : ratio.toFixed(1) + 'x';
        const soFar = cycle.current ? ' so far' : '';
        const verb  = d.cagr_pct >= 0 ? 'grew' : 'fell';
        const cagrColor = d.cagr_pct >= 0 ? 'var(--accent)' : '#ff6b6b';

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
          <div class="bull-box-prices">Rs.${fmt(d.start_price)} → Rs.${fmt(d.ltp)}</div>

          <button class="perf-toggle-btn" data-perf-id="${boxId}">
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
          </div>
        </div>`;
      }).join('');

      container.innerHTML = `
        <div class="bull-cycle-header">📊 ${symbol} — Performance Across Bull Cycles</div>
        <div class="bull-boxes-grid">${boxes}</div>`;
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

    async function doSearch() {
      const symbol = document.getElementById('search-input').value.trim().toUpperCase();
      if (!symbol) return;
      lastSearchedSymbol = symbol;
      const payload = { symbol, investment: 100000, years: 5 };
      document.getElementById('page-status').textContent = '⏳ Calculating...';
      document.getElementById('results-area').style.display = 'none';
      let port = await findPort();
      let data;
      if (port) {
        try {
          const resp = await fetch(`http://localhost:${port}/cagr`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
          data = await resp.json();
        } catch(e) { document.getElementById('page-status').textContent = '❌ ' + e.message; return; }
      } else {
        document.getElementById('page-status').textContent = '⚙️ Starting engine...';
        data = await new Promise(resolve => { chrome.runtime.sendMessage({ action: 'cagrViaNative', payload }, resolve); });
      }
      if (!data || data.error) { document.getElementById('page-status').textContent = '❌ ' + (data?.error || 'Error'); return; }
      showResults(data);
    }

    async function findPort() {
      for (let p = 5758; p <= 5768; p++) {
        try { const r = await fetch(`http://localhost:${p}/ping`, { signal: AbortSignal.timeout(300) }); if (r.ok) return p; } catch(_) {}
      }
      return null;
    }

    function fmt(n) { return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 }); }

    function showResults(d) {
      document.getElementById('page-status').textContent = '';
      document.getElementById('results-area').style.display = 'block';
      document.getElementById('r-symbol').textContent = d.symbol;
      const cagrEl = document.getElementById('r-cagr');
      cagrEl.textContent = (d.cagr_pct >= 0 ? '+' : '') + d.cagr_pct.toFixed(2) + '%';
      cagrEl.className = 'cagr-hero-value ' + (d.cagr_pct >= 0 ? 'pos' : 'neg');
      document.getElementById('r-meta').textContent = `${d.start_date} → ${d.end_date}  (${d.years} years)`;
      document.getElementById('r-start-price').textContent = 'Rs. ' + fmt(d.start_price);
      document.getElementById('r-ltp').textContent         = 'Rs. ' + fmt(d.ltp);
      document.getElementById('r-units').textContent       = d.total_units_today + ' kitta';
      document.getElementById('r-market').textContent      = 'Rs. ' + fmt(d.market_value);
      document.getElementById('r-divs').textContent        = 'Rs. ' + fmt(d.total_cash_dividends);
      document.getElementById('r-today').textContent       = 'Rs. ' + fmt(d.todays_value);
      document.getElementById('r-invest').textContent      = 'Rs. ' + fmt(d.initial_investment);
      document.getElementById('r-years').textContent       = d.years + ' yrs';
      const tbody = document.getElementById('r-events');
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

    // ── Bull & Bear Chart ──
    let bbChart = null;

    // Estimated data 1994–2000 (no official daily records; approximate based on known start 100pts Jan 1994)
    const estLabels = ["1994-01-13","1994-07-01","1995-01-01","1995-07-01","1996-01-01","1996-07-01","1997-01-01","1997-07-01","1998-01-01","1998-07-01","1999-01-01","1999-07-01","2000-01-01","2000-07-01"];
    const estValues = [100,116,134,152,175,215,248,285,315,332,342,350,358,348];

    const chartLabels = ["2000-11-23", "2001-07-10", "2002-03-15", "2002-08-26", "2003-01-24", "2004-04-01", "2004-07-06", "2005-05-04", "2006-05-15", "2006-08-03", "2007-07-16", "2007-12-17", "2008-08-31", "2009-01-21", "2009-07-20", "2010-04-28", "2010-07-18", "2011-01-31", "2011-02-28", "2011-03-31", "2011-04-28", "2011-05-31", "2011-06-30", "2011-07-31", "2011-08-30", "2011-09-29", "2011-10-31", "2011-11-28", "2011-12-29", "2012-01-31", "2012-02-29", "2012-03-29", "2012-04-30", "2012-05-31", "2012-06-28", "2012-07-31", "2012-08-30", "2012-09-30", "2012-10-31", "2012-11-29", "2012-12-31", "2013-01-31", "2013-02-28", "2013-03-31", "2013-04-30", "2013-05-30", "2013-06-30", "2013-07-31", "2013-08-29", "2013-09-30", "2013-10-31", "2013-11-28", "2013-12-31", "2014-01-29", "2014-02-26", "2014-03-31", "2014-04-30", "2014-05-28", "2014-06-30", "2014-07-31", "2014-08-31", "2014-09-30", "2014-10-30", "2014-11-30", "2014-12-31", "2015-01-29", "2015-02-26", "2015-03-31", "2015-04-23", "2015-05-31", "2015-06-30", "2015-07-30", "2015-08-31", "2015-09-30", "2015-10-29", "2015-11-30", "2015-12-31", "2016-01-31", "2016-02-29", "2016-03-31", "2016-04-28", "2016-05-31", "2016-06-30", "2016-07-27", "2016-07-31", "2016-08-31", "2016-09-29", "2016-10-27", "2016-11-30", "2016-12-29", "2017-01-31", "2017-02-28", "2017-03-30", "2017-04-30", "2017-05-31", "2017-06-28", "2017-07-31", "2017-08-31", "2017-09-26", "2017-10-31", "2017-11-30", "2017-12-31", "2018-01-31", "2018-02-28", "2018-03-29", "2018-04-29", "2018-05-31", "2018-06-28", "2018-07-31", "2018-08-30", "2018-09-30", "2018-10-31", "2018-11-29", "2018-12-31", "2019-01-31", "2019-02-27", "2019-03-05", "2019-03-31", "2019-04-30", "2019-05-30", "2019-06-30", "2019-07-31", "2019-08-29", "2019-09-30", "2019-10-31", "2019-11-28", "2019-12-31", "2020-01-30", "2020-02-27", "2020-03-22", "2020-05-13", "2020-06-30", "2020-07-30", "2020-08-31", "2020-09-30", "2020-10-29", "2020-11-30", "2020-12-31", "2021-01-31", "2021-02-28", "2021-03-31", "2021-04-29", "2021-05-31", "2021-06-30", "2021-07-29", "2021-08-18", "2021-08-31", "2021-09-30", "2021-10-31", "2021-11-30", "2021-12-29", "2022-01-31", "2022-02-28", "2022-03-31", "2022-04-28", "2022-05-31", "2022-06-30", "2022-07-31", "2022-08-31", "2022-09-25", "2022-09-29", "2022-10-31", "2022-11-30", "2022-12-29", "2023-01-31", "2023-02-28", "2023-03-30", "2023-04-30", "2023-05-31", "2023-06-28", "2023-07-31", "2023-08-30", "2023-09-27", "2023-10-31", "2023-11-30", "2023-12-28", "2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30", "2024-05-30", "2024-06-30", "2024-07-31", "2024-08-29", "2024-09-30", "2024-10-30", "2024-11-28", "2024-12-31", "2025-01-28", "2025-02-27", "2025-03-30", "2025-04-30", "2025-05-28", "2025-06-30", "2025-07-31", "2025-08-31", "2025-09-28", "2025-10-30", "2025-11-30", "2025-12-31", "2026-01-29", "2026-02-26", "2026-03-31", "2026-04-30", "2026-05-06"];
    const chartValues = [545.82, 322.74, 186.22, 230.01, 198.44, 195.14, 227.83, 298.78, 388.49, 355.6, 683.95, 1064.09, 1175.38, 609.46, 739.02, 405.45, 468.53, 410.57, 391.66, 365.0, 348.0, 337.0, 337.0, 359.0, 340.0, 331.0, 330.0, 323.0, 316.0, 316.0, 315.0, 299.0, 405.0, 374.0, 377.0, 401.0, 406.0, 415.0, 451.0, 489.0, 534.0, 511.0, 542.0, 511.0, 501.0, 500.0, 493.0, 548.0, 551.0, 542.0, 579.0, 644.0, 771.0, 781.0, 826.0, 792.0, 823.0, 867.0, 946.0, 1066.0, 953.0, 938.0, 930.0, 857.0, 902.0, 987.0, 979.0, 946.0, 938.0, 872.0, 949.0, 1028.0, 1200.0, 1181.28, 1092.04, 1034.12, 1151.38, 1220.7, 1283.94, 1355.48, 1464.91, 1532.12, 1723.23, 1881.45, 1862.76, 1797.45, 1753.38, 1759.71, 1608.33, 1443.38, 1326.6, 1299.29, 1587.64, 1650.78, 1608.11, 1563.81, 1652.69, 1580.03, 1549.46, 1533.53, 1537.67, 1390.58, 1404.49, 1345.99, 1220.29, 1349.01, 1307.66, 1198.54, 1191.47, 1181.69, 1256.71, 1221.46, 1148.36, 1188.19, 1161.63, 1105.53, 1098.95, 1143.09, 1298.6, 1319.47, 1244.89, 1265.57, 1196.41, 1135.56, 1146.17, 1112.79, 1166.03, 1325.38, 1632.17, 1251.45, 1201.57, 1260.75, 1439.06, 1484.99, 1550.43, 1645.67, 1997.05, 2087.27, 2370.54, 2474.39, 2619.03, 2611.1, 2782.68, 2823.87, 3079.83, 3198.6, 2975.84, 2633.42, 2837.61, 2628.37, 2524.5, 2872.05, 2610.58, 2544.31, 2356.17, 2137.92, 2037.64, 2195.1, 1973.38, 1815.13, 1853.76, 1874.88, 1949.85, 2029.03, 2111.68, 2019.93, 1908.55, 1870.65, 1849.79, 2150.99, 2106.18, 1990.59, 2004.3, 1864.4, 1858.53, 2068.9, 2097.93, 1972.09, 2018.33, 2006.28, 2069.53, 2037.09, 2760.9, 2749.57, 2508.86, 2677.62, 2748.05, 2576.5, 2657.77, 2815.04, 2693.12, 2623.83, 2693.06, 2631.48, 2922.63, 2749.83, 2663.51, 2600.38, 2649.52, 2633.76, 2714.05, 2654.93, 2851.09, 2738.72, 2711.22];

    // Key market turning points (all cycles)
    const bullTops = [
      { date: "2000-11-23", value: 545.82,   label: "Bull 1 Top\n546" },
      { date: "2008-08-31", value: 1175.38,  label: "Bull 2 Top\n1,175" },
      { date: "2016-07-27", value: 1881.45,  label: "Bull 3 Top\n1,881" },
      { date: "2021-08-18", value: 3198.60,  label: "Bull 4 Top\n3,199" },
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
      const lineColor = isDark ? '#4ecdc4' : '#2aa198';
      const estColor  = isDark ? 'rgba(78,205,196,0.5)' : 'rgba(42,161,152,0.5)';
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
              backgroundColor: isDark ? '#4ecdc4' : '#2aa198',
              pointRadius: 8,
              pointStyle: 'triangle',
              pointHoverRadius: 10,
              showLine: false,
            },
            {
              label: 'Bear Bottom',
              data: bearPointData,
              borderColor: 'transparent',
              backgroundColor: isDark ? '#ff6b6b' : '#dc322f',
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


        // ── CAGR page period toggle ──
    let cagrUseYears = true;
    document.getElementById('cagr-years-btn').onclick = () => {
      cagrUseYears = true;
      document.getElementById('cagr-years-btn').classList.add('active');
      document.getElementById('cagr-date-btn').classList.remove('active');
      document.getElementById('cagr-years').style.display = '';
      document.getElementById('cagr-date').style.display = 'none';
    };
    document.getElementById('cagr-date-btn').onclick = () => {
      cagrUseYears = false;
      document.getElementById('cagr-date-btn').classList.add('active');
      document.getElementById('cagr-years-btn').classList.remove('active');
      document.getElementById('cagr-years').style.display = 'none';
      document.getElementById('cagr-date').style.display = '';
    };

    // ── CAGR calculate ──
    document.getElementById('cagr-btn').onclick = doCagr;
    document.getElementById('cagr-symbol').addEventListener('keydown', e => { if (e.key === 'Enter') doCagr(); });

    async function doCagr() {
      const symbol = document.getElementById('cagr-symbol').value.trim().toUpperCase();
      if (!symbol) return;
      const investment = parseFloat(document.getElementById('cagr-invest').value) || 100000;
      const payload = { symbol, investment };
      if (cagrUseYears) payload.years = parseFloat(document.getElementById('cagr-years').value) || 5;
      else payload.start_date = document.getElementById('cagr-date').value;

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

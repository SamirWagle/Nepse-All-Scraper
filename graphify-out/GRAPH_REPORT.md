# Graph Report - Nepse-CAGR  (2026-07-04)

## Corpus Check
- 40 files · ~241,685 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1408 nodes · 3814 edges · 61 communities (55 shown, 6 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 103 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `adeccdf5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]

## God Nodes (most connected - your core abstractions)
1. `js()` - 343 edges
2. `update()` - 110 edges
3. `ns()` - 73 edges
4. `an()` - 73 edges
5. `no` - 50 edges
6. `n()` - 47 edges
7. `draw()` - 47 edges
8. `constructor()` - 43 edges
9. `va` - 39 edges
10. `updateElements()` - 38 edges

## Surprising Connections (you probably didn't know these)
- `Handler` --uses--> `ShareHubListingDateScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/listing_date.py
- `Handler` --uses--> `MerolaganiFundamentalsScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/fundamentals.py
- `Walk the merger chain to the terminal surviving entity still trading.      Many` --uses--> `ShareHubListingDateScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/listing_date.py
- `Walk the merger chain to the terminal surviving entity still trading.      Many` --uses--> `MerolaganiFundamentalsScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/fundamentals.py
- `Return companies matching q by exact ticker, ticker prefix, or name substring.` --uses--> `ShareHubListingDateScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/listing_date.py

## Communities (61 total, 6 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (32): a(), aa(), As(), b(), bo, configure(), determineDataLimits(), fn (+24 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (21): addBox(), addElements(), bt, ce(), constructor(), cs, de, dt() (+13 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (62): FloorsheetScraper, _auto_detect_data_dir(), clean_dataframe(), get_latest_date_in_csv(), _print_row(), prompt_for_date(), query_index(), index_history.py ---------------- Scrapes historical NEPSE index / sub-index dat (+54 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (23): beforeLayout(), buildLookupTable(), buildTicks(), ei(), En, Fo(), _generate(), getDecimalForValue() (+15 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (28): beforeDatasetDraw(), beforeDatasetsDraw(), dataset(), es(), generateLabels(), gi(), index(), Io (+20 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (23): _make_session(), MergerRecord, _name_is_matchable(), _normalize_company_name_key(), _parse_company_info_table(), ShareSansar merger announcement scraper.  This scrapes ShareSansar's merger/acqu, Keep already-saved values intact and only fill gaps from newer data., Pull title from <h1>/<title> and body from the article container only.         F (+15 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (41): actual_stock_window(), analyse_cycle(), analyse_from_listing(), build_analysis_rows(), _clean_company_name(), default_output_filename(), get_cycle(), get_stock_name() (+33 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (9): an(), destroy(), initialize(), p(), re, reset(), te(), u() (+1 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (15): be(), ct(), ds(), fs(), ge(), ls, me(), ms() (+7 more)

### Community 9 - "Community 9"
Cohesion: 0.09
Nodes (19): DailyScraperManager, Run the daily update:           - Refresh company ID mapping (catches new IPOs), Run the daily update:           - Refresh company ID mapping (catches new IPOs), Manages daily scraping tasks for priority companies (company_list.json):       -, Manages daily scraping tasks for priority companies (company_list.json):       -, Load the priority company list from company_list.json., Load the priority company list from company_list.json., Return symbols that already have a prices.csv. (+11 more)

### Community 10 - "Community 10"
Cohesion: 0.06
Nodes (34): backDestination, bearBottoms, BTC_BOTTOMS, BTC_BULL_CYCLES, BTC_CYCLE_BOTTOMS, BTC_FORWARD_RETURNS, BTC_TOPS, btn (+26 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (16): Bi(), ee, gt(), it(), jt(), kt(), le, mt() (+8 more)

### Community 12 - "Community 12"
Cohesion: 0.1
Nodes (26): BaseHTTPRequestHandler, calculate_cagr(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+18 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (8): afterDatasetsUpdate(), c(), di(), h(), jn, onClick(), qn(), update()

### Community 14 - "Community 14"
Cohesion: 0.11
Nodes (24): backfill(), _download(), _fetch_latest_xlsx_url(), InterestRateScraper, _merge(), parse_deposit_series(), _period_to_date(), Bank interest-rate scraper (Nepal) — NRB monthly statistics, authoritative.  Sou (+16 more)

### Community 15 - "Community 15"
Cohesion: 0.1
Nodes (6): afterUpdate(), beforeUpdate(), d(), kn(), Ue(), w()

### Community 16 - "Community 16"
Cohesion: 0.09
Nodes (13): at(), bn, cn(), dn(), e(), et(), i, on() (+5 more)

### Community 17 - "Community 17"
Cohesion: 0.07
Nodes (29): code:block1 (scraper/), code:block10 (date, sn, contract_no, stock_symbol, buyer, seller, quantity), code:json ({), code:bash (python scraper/run_daily.py --full-scrape), code:bash (git add data/), code:block2 (dividends     → data/company-wise/{SYMBOL}/dividend.csv), code:bash (pip install requests beautifulsoup4), code:bash (# All three) (+21 more)

### Community 18 - "Community 18"
Cohesion: 0.15
Nodes (10): _(), ba(), ft(), oi(), Si(), to(), ut(), x() (+2 more)

### Community 19 - "Community 19"
Cohesion: 0.08
Nodes (21): showResults(), analyseBtn, calcBtn, dateInput, dateWrap, findEnginePort(), fmt(), handleResult() (+13 more)

### Community 20 - "Community 20"
Cohesion: 0.11
Nodes (15): _calculateBarIndexPixels(), _calculateBarValuePixels(), getLabelAndValue(), getLabelForValue(), getPixelForTick(), getPixelForValue(), _getRuler(), _getStackCount() (+7 more)

### Community 21 - "Community 21"
Cohesion: 0.13
Nodes (23): ask_bonus_period(), get_price_for_date(), load_dividends(), load_prices(), load_symbol(), main(), normalise(), parse_date() (+15 more)

### Community 22 - "Community 22"
Cohesion: 0.14
Nodes (14): Return earliest date string from data/company-wise/{SYMBOL}/prices.csv, or None., Fetch listing date from ShareHubNepal. Returns YYYY-MM-DD or None., Fetch listing date from Sharepaati as fallback.         Page uses <dt>Listing Da, Scrapes listing dates from ShareHubNepal company pages:         https://sharehub, Scrape listing dates for a list of symbols.          :param symbols: list of sto, Read all unique symbols from prices.csv and scrape their listing dates., Look up a single symbol in ipo_listings.csv.         Returns listing_date string, Return dict of symbol -> listing_date already in ipo_listings.csv. (+6 more)

### Community 23 - "Community 23"
Cohesion: 0.18
Nodes (12): afterDraw(), ai(), draw(), ea(), ie, je(), ke(), qe() (+4 more)

### Community 24 - "Community 24"
Cohesion: 0.18
Nodes (5): gs(), ks(), Us(), Xs(), y

### Community 25 - "Community 25"
Cohesion: 0.14
Nodes (15): ao(), co(), Do(), g(), getCenterPoint(), ho(), Hs, inRange() (+7 more)

### Community 26 - "Community 26"
Cohesion: 0.18
Nodes (10): da(), fa(), ga(), ha, la(), oa(), pa(), ra() (+2 more)

### Community 27 - "Community 27"
Cohesion: 0.19
Nodes (5): ca(), eo(), getBasePixel(), lo(), sa()

### Community 28 - "Community 28"
Cohesion: 0.16
Nodes (17): _extract_fy(), _fetch_shareholding(), _parse_nepali_fy(), _parse_number(), _parse_range(), Merolagani fundamentals scraper.  Scrapes per-company fundamentals from:     htt, Append current EPS to eps_history.csv when this fiscal year is new.      File co, Accumulate yearly financial snapshots to financial_history.csv.      Columns: fi (+9 more)

### Community 29 - "Community 29"
Cohesion: 0.14
Nodes (16): MerolaganiFundamentalsScraper, Scrape per-company fundamentals from merolagani.com., Return fundamentals dict for symbol. Uses cache when fresh., Scrape per-company fundamentals from merolagani.com., Return fundamentals dict for symbol. Uses cache when fresh., Scrape per-company fundamentals from merolagani.com., Return fundamentals dict for symbol. Uses cache when fresh., _build_events() (+8 more)

### Community 30 - "Community 30"
Cohesion: 0.16
Nodes (18): calculate_cagr(), get_all_symbols(), get_cagr(), get_company_name(), load_company_names(), load_dividends(), load_prices(), load_right_shares() (+10 more)

### Community 31 - "Community 31"
Cohesion: 0.18
Nodes (16): calculate_cagr(), get_all_symbols(), get_cagr(), get_company_name(), load_company_names(), load_dividends(), load_prices(), load_right_shares() (+8 more)

### Community 32 - "Community 32"
Cohesion: 0.18
Nodes (15): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+7 more)

### Community 33 - "Community 33"
Cohesion: 0.12
Nodes (15): code:block1 (~/CodingProjects/Nepse-CAGR/), code:bash (cp nepse_cagr_server.py ~/CodingProjects/Nepse-CAGR/), code:bash (chmod +x ~/CodingProjects/Nepse-CAGR/nepse_host_wrapper.sh), code:json ("allowed_origins": [), code:bash (cp ~/CodingProjects/Nepse-CAGR/com.nepse.cagr.json \), Folder Structure, NEPSE CAGR Extension — Setup Instructions, Notes (+7 more)

### Community 34 - "Community 34"
Cohesion: 0.29
Nodes (13): _auto_detect_data_dir(), clean_dataframe(), get_latest_date_in_csv(), main(), _print_row(), prompt_for_date(), query_index(), index_history.py ---------------- Scrapes historical NEPSE index / sub-index dat (+5 more)

### Community 35 - "Community 35"
Cohesion: 0.25
Nodes (4): Ae(), ci(), fi, zi()

### Community 36 - "Community 36"
Cohesion: 0.29
Nodes (12): compute_window_end(), divider(), get_first_trading_date(), get_price_on_date(), get_stock_name(), main(), parse_window(), prompt_yn() (+4 more)

### Community 37 - "Community 37"
Cohesion: 0.24
Nodes (12): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+4 more)

### Community 38 - "Community 38"
Cohesion: 0.22
Nodes (12): fetch_operation_date(), get_prices_first_date(), load_ipo_listings(), load_missing_symbols(), backfill_merged_listing_dates.py  Backfills ipo_listings.csv with listing dates, Return the earliest date from data/company-wise/{SYMBOL}/prices.csv.     Note: t, Return dict symbol → listing_date from ipo_listings.csv., Write sorted symbol → date dict back to ipo_listings.csv. (+4 more)

### Community 39 - "Community 39"
Cohesion: 0.19
Nodes (7): beforeDraw(), getRange(), hi(), li(), ni(), ri(), ui()

### Community 40 - "Community 40"
Cohesion: 0.21
Nodes (11): doBullSearch(), doLtpLookup(), getTradingRange(), renderBullBoxes(), resolveSymbolPage(), toggleNepseComparison(), toggleTickerOverlay(), esc() (+3 more)

### Community 41 - "Community 41"
Cohesion: 0.24
Nodes (12): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+4 more)

### Community 42 - "Community 42"
Cohesion: 0.15
Nodes (12): code:markdown (# Nepse-CAGR), code:block10, code:block2, code:block3, code:block4, code:block5, code:block6, code:block7 (+4 more)

### Community 44 - "Community 44"
Cohesion: 0.32
Nodes (3): bs, hn(), updateElements()

### Community 45 - "Community 45"
Cohesion: 0.24
Nodes (10): buildChart(), buildFdChart(), fetchInterestRates(), openBullBearFromQuery(), runIndexBullBear(), showLtpWidget(), showPagedPicker(), switchPage() (+2 more)

### Community 46 - "Community 46"
Cohesion: 0.4
Nodes (10): doCagr(), doSearch(), findPort(), localResolveCandidates(), resolveBullSymbol(), resolveSymbol(), runCagrCalc(), runFundamentalsForSymbol() (+2 more)

### Community 47 - "Community 47"
Cohesion: 0.31
Nodes (3): gn, ki(), so()

### Community 48 - "Community 48"
Cohesion: 0.28
Nodes (9): fmt(), fmtCompact(), isMarketOpen(), renderShareholdingDonut(), setText(), showCagrResults(), showFundamentals(), fmt() (+1 more)

### Community 49 - "Community 49"
Cohesion: 0.36
Nodes (7): fetch_yahoo_rows(), main(), merge_rows(), Scrape full BTC-USD daily history from Yahoo Finance into data/btc/history.csv., Return [(iso_date, close), ...] from Yahoo's chart API., Seed rows before Yahoo coverage + Yahoo rows, deduped by date, sorted., write_csv()

### Community 50 - "Community 50"
Cohesion: 0.43
Nodes (7): classify(), first_trade_date(), load_ipo_listings(), main(), parse_date(), audit_listing_dates.py  Cross-checks ipo_listings.csv against the first trading, Read company-wise/{SYMBOL}/prices.csv and return earliest date or None.

### Community 51 - "Community 51"
Cohesion: 0.46
Nodes (7): import_csv(), import_json(), load_registry(), main(), merge_entry(), normalize_entry(), Preserve existing values and only fill in missing fields from incoming data.

### Community 52 - "Community 52"
Cohesion: 0.29
Nodes (3): get_first_trading_date(), main(), Return the earliest date in prices.csv for this symbol.

### Community 53 - "Community 53"
Cohesion: 0.29
Nodes (6): May 21, 2026, May 22, 2026, May 23, 2026, May 24, 2026, Memory Context, [Nepse-CAGR] recent context, 2026-05-24 2:26pm GMT+5:45

### Community 54 - "Community 54"
Cohesion: 0.67
Nodes (3): get_company_name(), main(), Scrape the company name from sharesansar.com/company/<symbol>.

## Knowledge Gaps
- **255 isolated node(s):** `NEPSE Stock CAGR Calculator ============================ Uses data from: https:/`, `Load right-share.csv for the given symbol.     Columns: ratio, total_units, issu`, `Calculate total return and CAGR for a NEPSE stock over a date window.      Corpo`, `Importable function. Returns a dict with full breakdown + cagr_pct.      Example`, `NEPSE Stock CAGR Calculator ============================ Uses data from: https:/` (+250 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `js()` connect `Community 4` to `Community 0`, `Community 1`, `Community 3`, `Community 7`, `Community 8`, `Community 11`, `Community 13`, `Community 15`, `Community 16`, `Community 18`, `Community 20`, `Community 23`, `Community 24`, `Community 25`, `Community 26`, `Community 27`, `Community 35`, `Community 39`, `Community 43`, `Community 44`, `Community 47`?**
  _High betweenness centrality (0.293) - this node is a cross-community bridge._
- **Why does `main()` connect `Community 2` to `Community 9`, `Community 12`, `Community 46`, `Community 52`, `Community 22`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `init()` connect `Community 3` to `Community 0`, `Community 2`, `Community 35`, `Community 4`, `Community 6`, `Community 9`, `Community 18`, `Community 52`, `Community 24`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **What connects `NEPSE Stock CAGR Calculator ============================ Uses data from: https:/`, `Load right-share.csv for the given symbol.     Columns: ratio, total_units, issu`, `Calculate total return and CAGR for a NEPSE stock over a date window.      Corpo` to the rest of the system?**
  _255 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
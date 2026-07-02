# Graph Report - Nepse-CAGR  (2026-07-02)

## Corpus Check
- 34 files · ~374,004 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1308 nodes · 3709 edges · 31 communities detected
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 102 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

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
- `calculate_cagr()` --calls--> `main()`  [EXTRACTED]
  nepse_cagr.py → scraper/run_daily.py
- `Handler` --uses--> `ShareHubListingDateScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/listing_date.py
- `Handler` --uses--> `MerolaganiFundamentalsScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/fundamentals.py
- `Walk the merger chain to the terminal surviving entity still trading.      Many` --uses--> `ShareHubListingDateScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/listing_date.py
- `Walk the merger chain to the terminal surviving entity still trading.      Many` --uses--> `MerolaganiFundamentalsScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/fundamentals.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.03
Nodes (99): _(), Ae(), afterUpdate(), ao(), As(), at(), b(), beforeUpdate() (+91 more)

### Community 1 - "Community 1"
Cohesion: 0.03
Nodes (94): get_first_trading_date(), main(), Return the earliest date in prices.csv for this symbol., BaseHTTPRequestHandler, DailyScraperManager, DailySummaryUpdater, Updates daily stock price data for all companies using ShareSansar's Today Price, Updates daily stock price data for all companies using ShareSansar's Today Price (+86 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (98): Read the latest (most recent) date already saved in prices.csv.         Returns, backDestination, bearBottoms, buildBtcChart(), buildChart(), buildFdChart(), bullCyclePlugin, bullCycles (+90 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (33): a(), aa(), beforeLayout(), bo, buildTicks(), determineDataLimits(), ei(), En (+25 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (22): addBox(), addElements(), bn, bt, constructor(), cs, de, dn() (+14 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (16): afterDatasetsUpdate(), afterEvent(), an(), cn(), destroy(), f(), generateLabels(), initialize() (+8 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (19): bs, configure(), fn, go(), l(), ls, ns(), oa() (+11 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (16): ca(), _calculateBarIndexPixels(), _calculateBarValuePixels(), eo(), getBasePixel(), getPixelForValue(), _getRuler(), _getStackCount() (+8 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (22): afterDraw(), ai(), ba(), draw(), ea(), ee, ft(), gn (+14 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (45): FloorsheetScraper, append_to_csv(), ensure_dir(), get_csrf_and_company_id(), _get_floorsheet_hidden(), load_priority_companies(), main(), _make_full_dt_params() (+37 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (26): _make_session(), MergerRecord, _name_is_matchable(), _normalize_company_name_key(), _parse_company_info_table(), ShareSansar merger announcement scraper.  This scrapes ShareSansar's merger/acqu, Keep already-saved values intact and only fill gaps from newer data., Pull title from <h1>/<title> and body from the article container only.         F (+18 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (22): beforeDatasetDraw(), beforeDatasetsDraw(), beforeDraw(), da(), fa(), ga(), gt(), ha (+14 more)

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (30): actual_stock_window(), analyse_cycle(), analyse_from_listing(), build_analysis_rows(), _clean_company_name(), default_output_filename(), get_cycle(), get_stock_name() (+22 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (24): backfill(), _download(), _fetch_latest_xlsx_url(), InterestRateScraper, _merge(), parse_deposit_series(), _period_to_date(), Bank interest-rate scraper (Nepal) — NRB monthly statistics, authoritative.  Sou (+16 more)

### Community 14 - "Community 14"
Cohesion: 0.14
Nodes (12): be(), ct(), ds(), fs(), ge(), me(), ms(), pe() (+4 more)

### Community 15 - "Community 15"
Cohesion: 0.13
Nodes (23): ask_bonus_period(), get_price_for_date(), load_dividends(), load_prices(), load_symbol(), main(), normalise(), parse_date() (+15 more)

### Community 16 - "Community 16"
Cohesion: 0.16
Nodes (18): calculate_cagr(), get_all_symbols(), get_cagr(), get_company_name(), load_company_names(), load_dividends(), load_prices(), load_right_shares() (+10 more)

### Community 17 - "Community 17"
Cohesion: 0.18
Nodes (16): calculate_cagr(), get_all_symbols(), get_cagr(), get_company_name(), load_company_names(), load_dividends(), load_prices(), load_right_shares() (+8 more)

### Community 18 - "Community 18"
Cohesion: 0.18
Nodes (15): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+7 more)

### Community 19 - "Community 19"
Cohesion: 0.29
Nodes (13): _auto_detect_data_dir(), clean_dataframe(), get_latest_date_in_csv(), main(), _print_row(), prompt_for_date(), query_index(), index_history.py ---------------- Scrapes historical NEPSE index / sub-index dat (+5 more)

### Community 20 - "Community 20"
Cohesion: 0.29
Nodes (12): compute_window_end(), divider(), get_first_trading_date(), get_price_on_date(), get_stock_name(), main(), parse_window(), prompt_yn() (+4 more)

### Community 21 - "Community 21"
Cohesion: 0.24
Nodes (12): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+4 more)

### Community 22 - "Community 22"
Cohesion: 0.22
Nodes (12): fetch_operation_date(), get_prices_first_date(), load_ipo_listings(), load_missing_symbols(), backfill_merged_listing_dates.py  Backfills ipo_listings.csv with listing dates, Return the earliest date from data/company-wise/{SYMBOL}/prices.csv.     Note: t, Return dict symbol → listing_date from ipo_listings.csv., Write sorted symbol → date dict back to ipo_listings.csv. (+4 more)

### Community 23 - "Community 23"
Cohesion: 0.24
Nodes (12): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+4 more)

### Community 24 - "Community 24"
Cohesion: 0.46
Nodes (7): import_csv(), import_json(), load_registry(), main(), merge_entry(), normalize_entry(), Preserve existing values and only fill in missing fields from incoming data.

### Community 25 - "Community 25"
Cohesion: 0.43
Nodes (7): classify(), first_trade_date(), load_ipo_listings(), main(), parse_date(), audit_listing_dates.py  Cross-checks ipo_listings.csv against the first trading, Read company-wise/{SYMBOL}/prices.csv and return earliest date or None.

### Community 26 - "Community 26"
Cohesion: 0.67
Nodes (3): get_company_name(), main(), Scrape the company name from sharesansar.com/company/<symbol>.

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (1): run_index_history.py -------------------- CLI entry point for scraping NEPSE ind

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): A company name is safe to substring-match only when long enough and         most

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): Read the ShareSansar company-page info table into {Key: Value}.          Field n

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Split a ShareSansar 'companies' cell into individual company names.          Nam

## Knowledge Gaps
- **193 isolated node(s):** `NEPSE Stock CAGR Calculator ============================ Uses data from: https:/`, `Load right-share.csv for the given symbol.     Columns: ratio, total_units, issu`, `Calculate total return and CAGR for a NEPSE stock over a date window.      Corpo`, `Importable function. Returns a dict with full breakdown + cagr_pct.      Example`, `NEPSE Stock CAGR Calculator ============================ Uses data from: https:/` (+188 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 27`** (2 nodes): `run_index_history.py -------------------- CLI entry point for scraping NEPSE ind`, `run_index_history.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `A company name is safe to substring-match only when long enough and         most`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `Read the ShareSansar company-page info table into {Key: Value}.          Field n`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Split a ShareSansar 'companies' cell into individual company names.          Nam`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `js()` connect `Community 0` to `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 11`, `Community 14`?**
  _High betweenness centrality (0.311) - this node is a cross-community bridge._
- **Why does `main()` connect `Community 2` to `Community 1`, `Community 9`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Why does `init()` connect `Community 1` to `Community 0`, `Community 3`, `Community 6`, `Community 8`, `Community 9`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **What connects `NEPSE Stock CAGR Calculator ============================ Uses data from: https:/`, `Load right-share.csv for the given symbol.     Columns: ratio, total_units, issu`, `Calculate total return and CAGR for a NEPSE stock over a date window.      Corpo` to the rest of the system?**
  _193 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.03 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.03 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.03 - nodes in this community are weakly interconnected._
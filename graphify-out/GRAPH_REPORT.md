# Graph Report - Nepse-CAGR  (2026-08-10)

## Corpus Check
- 57 files · ~386,757 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1873 nodes · 4570 edges · 92 communities (82 shown, 10 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 131 edges (avg confidence: 0.71)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d93615f8`
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
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]

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
- `main()` --calls--> `_auto_detect_data_dir()`  [EXTRACTED]
  scraper/run_daily.py → index_history.py
- `_market_traded_today()` --calls--> `_newest_price_date()`  [INFERRED]
  scraper/run_daily.py → scripts/data_freshness.py
- `Return first and last available trading dates for a company, if present.` --uses--> `ShareHubListingDateScraper`  [INFERRED]
  nepse_cagr_server.py → scraper/core/listing_date.py

## Communities (92 total, 10 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (75): add_indicators(), adx(), all_tickers(), _archive_path(), atr(), _avg_concurrent(), buy_hold_net(), cmd_backtest() (+67 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (39): addBox(), be(), ce(), dataset(), ee, et(), generateLabels(), getRange() (+31 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (55): _apply_eps_fallback(), _apply_hydro_capacity(), _extract_fy(), _fetch_chukul_paid_up_capital(), _fetch_nepsealpha_paid_up_capital(), _fetch_shareholding(), _fetch_sharesansar_shares(), _firecrawl_markdown() (+47 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (23): beforeLayout(), bo, buildLookupTable(), buildTicks(), En, _generate(), getDecimalForValue(), getLabelForValue() (+15 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (33): _make_session(), MergerRecord, _name_is_matchable(), _normalize_company_name_key(), _parse_company_info_table(), ShareSansar merger announcement scraper.  This scrapes ShareSansar's merger/acqu, Keep already-saved values intact and only fill gaps from newer data., Pull title from <h1>/<title> and body from the article container only.         F (+25 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (20): bn, bt, cn(), constructor(), dn(), dt(), e(), ei() (+12 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (49): _archive_path(), _build_date(), cmd_scan(), dedupe(), _extract_published(), _feed_entry_date(), fetch_ansuinvest(), fetch_facebook_pages() (+41 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (18): ao(), co(), Do(), eo(), getCenterPoint(), ho(), Hs, inRange() (+10 more)

### Community 8 - "Community 8"
Cohesion: 0.1
Nodes (19): beforeDatasetDraw(), beforeDatasetsDraw(), bs, c(), da(), di(), fa(), ga() (+11 more)

### Community 9 - "Community 9"
Cohesion: 0.05
Nodes (38): backDestination, bearBottoms, BTC_BOTTOMS, BTC_BULL_CYCLES, BTC_CYCLE_BOTTOMS, BTC_FORWARD_RETURNS, BTC_TOPS, btn (+30 more)

### Community 10 - "Community 10"
Cohesion: 0.11
Nodes (26): ca(), _calculateBarIndexPixels(), _calculateBarValuePixels(), fn, Fo(), getBasePixel(), getLabelAndValue(), getPixelForTick() (+18 more)

### Community 11 - "Community 11"
Cohesion: 0.09
Nodes (14): gt(), ha, it(), kt(), mt(), pt(), qt(), _t() (+6 more)

### Community 12 - "Community 12"
Cohesion: 0.12
Nodes (9): afterDraw(), ai(), an(), beforeDraw(), draw(), re, size(), ti() (+1 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (5): addElements(), de, ia(), qs(), tn

### Community 14 - "Community 14"
Cohesion: 0.09
Nodes (23): _clean_date(), Return earliest date string from data/company-wise/{SYMBOL}/prices.csv, or None., Fetch listing date from ShareHubNepal. Returns YYYY-MM-DD or None., Return earliest date string from data/company-wise/{SYMBOL}/prices.csv, or None., Fetch listing date from ShareHubNepal. Returns YYYY-MM-DD or None., Fetch listing date from Sharepaati as fallback.         Page uses <dt>Listing Da, Fetch listing date from Sharepaati as fallback.         Page uses <dt>Listing Da, Scrapes listing dates from ShareHubNepal company pages:         https://sharehub (+15 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (3): As(), ns(), updateRangeFromParsed()

### Community 16 - "Community 16"
Cohesion: 0.13
Nodes (30): actual_stock_window(), analyse_cycle(), analyse_from_listing(), build_analysis_rows(), _clean_company_name(), default_output_filename(), get_cycle(), get_stock_name() (+22 more)

### Community 17 - "Community 17"
Cohesion: 0.11
Nodes (24): backfill(), _download(), _fetch_latest_xlsx_url(), InterestRateScraper, _merge(), parse_deposit_series(), _period_to_date(), Bank interest-rate scraper (Nepal) — NRB monthly statistics, authoritative.  Sou (+16 more)

### Community 18 - "Community 18"
Cohesion: 0.13
Nodes (6): Ae(), gn, ks(), so(), Us(), Xs()

### Community 19 - "Community 19"
Cohesion: 0.07
Nodes (29): code:block1 (scraper/), code:block10 (date, sn, contract_no, stock_symbol, buyer, seller, quantity), code:json ({), code:bash (python scraper/run_daily.py --full-scrape), code:bash (git add data/), code:block2 (dividends     → data/company-wise/{SYMBOL}/dividend.csv), code:bash (pip install requests beautifulsoup4), code:bash (# All three) (+21 more)

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (9): a(), determineDataLimits(), _getStackIndex(), _getStacks(), getValueForPixel(), ko, r(), xo (+1 more)

### Community 21 - "Community 21"
Cohesion: 0.08
Nodes (21): showResults(), analyseBtn, calcBtn, dateInput, dateWrap, findEnginePort(), fmt(), handleResult() (+13 more)

### Community 22 - "Community 22"
Cohesion: 0.19
Nodes (10): ba(), ea(), ft(), gs(), ki(), oi(), Si(), ut() (+2 more)

### Community 23 - "Community 23"
Cohesion: 0.12
Nodes (11): FPDF, Shared styled PDF builder for investor-persona analysis reports.  Used by all in, Design A: editorial serif, gold rule, italic subtitle., Design B: bold sans, card-grid identity., Design C: two-column-flavoured serif, black rule., Small italic grey methodology/source note., One checklist/criterion item - card (b) or ruled row (a/c)., Core Helvetica/Times fonts only support latin-1 - downgrade common     Unicode p (+3 more)

### Community 24 - "Community 24"
Cohesion: 0.11
Nodes (22): calculate_cagr(), get_cagr(), load_dividends(), load_index_prices(), load_prices(), load_right_shares(), main(), nearest_price() (+14 more)

### Community 25 - "Community 25"
Cohesion: 0.09
Nodes (23): _apply_dismissed_to_report(), calculate_index_cagr(), get_merger_info(), _last_scheduled_news_run(), _load_companies(), _load_merger_meta(), Return companies matching q by exact ticker, ticker prefix, or name substring., Walk the merger chain to the terminal surviving entity still trading.      Many (+15 more)

### Community 26 - "Community 26"
Cohesion: 0.13
Nodes (24): fetch_registry(), fetch_traded_symbols(), find_renames(), _load_json(), merge_registry(), parse_registry(), Return new (mapping, names) dicts with missing symbols added, renames applied., Return new (mapping, names) dicts with missing symbols added, renames applied. (+16 more)

### Community 27 - "Community 27"
Cohesion: 0.15
Nodes (7): cs, fe(), k(), nn(), os(), pi(), sn

### Community 28 - "Community 28"
Cohesion: 0.15
Nodes (22): _check(), cmd_alerts(), cmd_close(), cmd_list(), cmd_open(), cmd_selftest(), cmd_test_telegram(), cmd_watch() (+14 more)

### Community 29 - "Community 29"
Cohesion: 0.14
Nodes (12): BaseHTTPRequestHandler, Handler, _last_news_scan(), _load_dismissed_news_urls(), Hide a digest item once read, or put it back.          Reversible by design, whi, Hide a digest item once read, or put it back.          Reversible by design, whi, Hide a digest item once read, or put it back.          Reversible by design, whi, Remove one archived digest and its snapshot row. Irreversible. (+4 more)

### Community 30 - "Community 30"
Cohesion: 0.13
Nodes (4): afterUpdate(), d(), Ue(), w()

### Community 31 - "Community 31"
Cohesion: 0.13
Nodes (23): ask_bonus_period(), get_price_for_date(), load_dividends(), load_prices(), load_symbol(), main(), normalise(), parse_date() (+15 more)

### Community 32 - "Community 32"
Cohesion: 0.14
Nodes (23): collect(), _last_date_in_column(), _mtime_date(), _newest_floorsheet_date(), _newest_mtime(), _newest_price_date(), _oldest_index_date(), _parse() (+15 more)

### Community 33 - "Community 33"
Cohesion: 0.12
Nodes (21): calculate_cagr(), get_all_symbols(), get_cagr(), get_company_name(), load_company_names(), load_dividends(), load_prices(), load_right_shares() (+13 more)

### Community 34 - "Community 34"
Cohesion: 0.12
Nodes (12): DailyScraperManager, Manages daily scraping tasks for priority companies (company_list.json):       -, Manages daily scraping tasks for priority companies (company_list.json):       -, Load the priority company list from company_list.json., Load the priority company list from company_list.json., Load every symbol known to the ShareSansar mapping, including merged/delisted co, Load every symbol known to the ShareSansar mapping, including merged/delisted co, Parse a table row into a dict (+4 more)

### Community 35 - "Community 35"
Cohesion: 0.16
Nodes (8): ct(), fs(), ge(), ms(), rs, we(), ws, ys()

### Community 36 - "Community 36"
Cohesion: 0.13
Nodes (10): Bi(), ci(), ds(), fi, jt(), ls, pe(), te() (+2 more)

### Community 37 - "Community 37"
Cohesion: 0.18
Nodes (3): aa(), afterDatasetsUpdate(), jn

### Community 38 - "Community 38"
Cohesion: 0.13
Nodes (20): ensure_dir(), _make_full_dt_params(), make_session(), overwrite_csv(), _post_ajax(), Write/overwrite a CSV with the given rows., Write/overwrite a CSV atomically via temp file + rename., Build full DataTables POST params for ShareSansar AJAX endpoints. (+12 more)

### Community 39 - "Community 39"
Cohesion: 0.16
Nodes (18): calculate_cagr(), get_all_symbols(), get_cagr(), get_company_name(), load_company_names(), load_dividends(), load_prices(), load_right_shares() (+10 more)

### Community 40 - "Community 40"
Cohesion: 0.13
Nodes (18): MerolaganiFundamentalsScraper, Scrape per-company fundamentals from merolagani.com., Scrape per-company fundamentals from merolagani.com., Scrape per-company fundamentals from merolagani.com., Scrape per-company fundamentals from merolagani.com., Scrape per-company fundamentals from merolagani.com., _build_events(), calculate_cagr() (+10 more)

### Community 41 - "Community 41"
Cohesion: 0.17
Nodes (13): _firecrawl_keys(), _firecrawl_markdown(), NepseAlphaQuarterlyScraper, _parse_plain_pct(), _parse_quarterly_table(), _parse_row(), NepseAlpha quarterly fundamentals scraper (earnings growth + ROE trend).  Scrape, Scrape per-company quarterly earnings/ROE trend from nepsealpha.com. (+5 more)

### Community 42 - "Community 42"
Cohesion: 0.16
Nodes (18): absolutiseReportLinks(), buildChart(), buildFdChart(), doBullSearch(), fetchInterestRates(), fileToBase64(), getTradingRange(), runKarmaSignal() (+10 more)

### Community 43 - "Community 43"
Cohesion: 0.19
Nodes (8): beforeUpdate(), configure(), es(), initialize(), is(), reset(), s(), ss()

### Community 44 - "Community 44"
Cohesion: 0.21
Nodes (17): doCagr(), doSearch(), findPort(), localResolveCandidates(), openBullBearFromQuery(), resolveBullSymbol(), resolveSymbol(), resolveSymbolPage() (+9 more)

### Community 45 - "Community 45"
Cohesion: 0.21
Nodes (15): ensure_engine_running(), find_port(), main(), post_to_engine(), read_message(), send_message(), start_engine(), main() (+7 more)

### Community 46 - "Community 46"
Cohesion: 0.23
Nodes (15): _auto_detect_data_dir(), clean_dataframe(), get_latest_date_in_csv(), main(), _print_row(), prompt_for_date(), query_index(), index_history.py ---------------- Scrapes historical NEPSE index / sub-index dat (+7 more)

### Community 47 - "Community 47"
Cohesion: 0.15
Nodes (14): doLtpLookup(), fmt(), fmtCompact(), isMarketOpen(), renderBullBoxes(), renderShareholdingDonut(), setText(), showFundamentals() (+6 more)

### Community 48 - "Community 48"
Cohesion: 0.17
Nodes (6): at(), destroy(), lt(), rt(), stop(), vs()

### Community 49 - "Community 49"
Cohesion: 0.18
Nodes (15): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+7 more)

### Community 50 - "Community 50"
Cohesion: 0.12
Nodes (15): code:block1 (~/CodingProjects/Nepse-CAGR/), code:bash (cp nepse_cagr_server.py ~/CodingProjects/Nepse-CAGR/), code:bash (chmod +x ~/CodingProjects/Nepse-CAGR/nepse_host_wrapper.sh), code:json ("allowed_origins": [), code:bash (cp ~/CodingProjects/Nepse-CAGR/com.nepse.cagr.json \), Folder Structure, NEPSE CAGR Extension — Setup Instructions, Notes (+7 more)

### Community 51 - "Community 51"
Cohesion: 0.25
Nodes (3): afterEvent(), f(), va

### Community 52 - "Community 52"
Cohesion: 0.21
Nodes (13): Read the latest (most recent) date already saved in prices.csv.         Returns, _auto_detect_data_dir(), clean_dataframe(), get_latest_date_in_csv(), _print_row(), prompt_for_date(), query_index(), index_history.py ---------------- Scrapes historical NEPSE index / sub-index dat (+5 more)

### Community 53 - "Community 53"
Cohesion: 0.18
Nodes (10): Run the daily update:           - Refresh company ID mapping (catches new IPOs), Run the daily update:           - Refresh company ID mapping (catches new IPOs), Run the daily update:           - Refresh company ID mapping (catches new IPOs), Return symbols that already have a prices.csv., Scrape / update prices.csv for the given symbols., Return symbols that already have a prices.csv., Return symbols that already have a prices.csv., Scrape / update prices.csv for the given symbols. (+2 more)

### Community 54 - "Community 54"
Cohesion: 0.25
Nodes (12): _(), b(), g(), h(), ii(), m(), o(), p() (+4 more)

### Community 55 - "Community 55"
Cohesion: 0.29
Nodes (12): compute_window_end(), divider(), get_first_trading_date(), get_price_on_date(), get_stock_name(), main(), parse_window(), prompt_yn() (+4 more)

### Community 56 - "Community 56"
Cohesion: 0.24
Nodes (12): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+4 more)

### Community 57 - "Community 57"
Cohesion: 0.22
Nodes (12): fetch_operation_date(), get_prices_first_date(), load_ipo_listings(), load_missing_symbols(), backfill_merged_listing_dates.py  Backfills ipo_listings.csv with listing dates, Return the earliest date from data/company-wise/{SYMBOL}/prices.csv.     Note: t, Return dict symbol → listing_date from ipo_listings.csv., Write sorted symbol → date dict back to ipo_listings.csv. (+4 more)

### Community 58 - "Community 58"
Cohesion: 0.22
Nodes (8): ChukulCapacityScraper, _fetch_company_website(), _parse_capacity(), _parse_capacity_from_text(), Hydropower installed-capacity (MW) scraper.  Primary source — the "Capacity (MW), Best-effort MW extraction from freeform company-website text., Return a likely company website URL via ShareSansar, or None.      Prefers the ", Scrape installed capacity (MW) for hydropower companies from Chukul.

### Community 59 - "Community 59"
Cohesion: 0.24
Nodes (12): calculate_cagr(), get_all_symbols(), get_cagr(), load_dividends(), load_prices(), load_right_shares(), main(), nearest_price() (+4 more)

### Community 60 - "Community 60"
Cohesion: 0.15
Nodes (12): code:markdown (# Nepse-CAGR), code:block10, code:block2, code:block3, code:block4, code:block5, code:block6, code:block7 (+4 more)

### Community 61 - "Community 61"
Cohesion: 0.35
Nodes (11): bs_end_year_to_ad(), current_price(), historical_pe_series(), load_eps_history(), load_prices(), nearest_price(), present_pe(), 076-077 -> mid-July 2020 (BS end year 077 -> AD 2020). (+3 more)

### Community 62 - "Community 62"
Cohesion: 0.27
Nodes (11): load_priority_companies(), main(), run_github_actions.py ===================== Daily scraper designed for GitHub Ac, Scrape dividends for every company-wise dir that has prices.csv but no dividend., Return list of symbols from company_list.json., Return list of symbols from company_list.json., run_backfill_missing(), run_dividends() (+3 more)

### Community 63 - "Community 63"
Cohesion: 0.36
Nodes (10): dedupe(), fetch_facebook_pages(), fetch_merolagani(), fetch_reddit(), fetch_sharesansar(), main(), _matches_keywords(), Scrape latest news headlines from Merolagani's news listing page. (+2 more)

### Community 64 - "Community 64"
Cohesion: 0.22
Nodes (5): FloorsheetScraper, _get_floorsheet_hidden(), Scrape today's full floorsheet from merolagani. Returns list of records., Scrape today's full floorsheet from merolagani. Returns list of records., scrape_floorsheet()

### Community 65 - "Community 65"
Cohesion: 0.2
Nodes (10): build_adjusted_series(), get_company_trading_range(), Return first and last available trading dates for a company, if present., Return first and last available trading dates for a company, if present., Return first and last available trading dates for a company, if present., Return first and last available trading dates for a company, if present., Bonus/right/cash-adjusted wealth-index series for a company.      Returns a list, Return first and last available trading dates for a company, if present. (+2 more)

### Community 66 - "Community 66"
Cohesion: 0.2
Nodes (9): code:bash (pip install requests beautifulsoup4 --break-system-packages), code:bash (python3 nepse_news_digest.py --hours 24), Customizing, Install, Known fragility, NEPSE News Digest — n8n Setup, On Facebook groups, Run standalone (+1 more)

### Community 67 - "Community 67"
Cohesion: 0.36
Nodes (7): classify(), is_equity(), _normalise(), Classify a NEPSE listing by instrument type.  ShareSansar's registry mixes ordin, Return the instrument type for a listing's display name., True for ordinary shares — the only instruments the analyser handles., _self_check()

### Community 68 - "Community 68"
Cohesion: 0.46
Nodes (7): import_csv(), import_json(), load_registry(), main(), merge_entry(), normalize_entry(), Preserve existing values and only fill in missing fields from incoming data.

### Community 69 - "Community 69"
Cohesion: 0.36
Nodes (7): fetch_yahoo_rows(), main(), merge_rows(), Scrape full BTC-USD daily history from Yahoo Finance into data/btc/history.csv., Return [(iso_date, close), ...] from Yahoo's chart API., Seed rows before Yahoo coverage + Yahoo rows, deduped by date, sorted., write_csv()

### Community 70 - "Community 70"
Cohesion: 0.43
Nodes (7): classify(), first_trade_date(), load_ipo_listings(), main(), parse_date(), audit_listing_dates.py  Cross-checks ipo_listings.csv against the first trading, Read company-wise/{SYMBOL}/prices.csv and return earliest date or None.

### Community 71 - "Community 71"
Cohesion: 0.25
Nodes (5): DailySummaryUpdater, Updates daily stock price data for all companies using ShareSansar's Today Price, Updates daily stock price data for all companies using ShareSansar's Today Price, Fetch today's data and update all company CSVs, Fetch today's data and update all company CSVs

### Community 72 - "Community 72"
Cohesion: 0.38
Nodes (4): Append new records to company CSV file, avoiding duplicates.         Saves to da, load_registry_entries(), load_registry_symbols(), main()

### Community 73 - "Community 73"
Cohesion: 0.52
Nodes (6): analyse(), demo(), load_closes(), rsi(), sma(), support_resistance()

### Community 74 - "Community 74"
Cohesion: 0.29
Nodes (6): May 21, 2026, May 22, 2026, May 23, 2026, May 24, 2026, Memory Context, [Nepse-CAGR] recent context, 2026-05-24 2:26pm GMT+5:45

### Community 75 - "Community 75"
Cohesion: 0.33
Nodes (6): _load_interest_rates(), Read data/interest_rates/fd_rates.csv → {"rates": [...]}.      Each row: {date,, Read data/interest_rates/fd_rates.csv → {"rates": [...]}.      Each row: {date,, Read data/interest_rates/fd_rates.csv → {"rates": [...]}.      Each row: {date,, Read data/interest_rates/fd_rates.csv → {"rates": [...]}.      Each row: {date,, Read data/interest_rates/fd_rates.csv → {"rates": [...]}.      Each row: {date,

### Community 76 - "Community 76"
Cohesion: 0.67
Nodes (3): get_first_trading_date(), main(), Return the earliest date in prices.csv for this symbol.

### Community 77 - "Community 77"
Cohesion: 0.67
Nodes (3): get_company_name(), main(), Scrape the company name from sharesansar.com/company/<symbol>.

### Community 78 - "Community 78"
Cohesion: 0.67
Nodes (3): append_to_csv(), Append rows to CSV, writing header if file is new., Append rows to CSV, writing header if file is new.

### Community 79 - "Community 79"
Cohesion: 0.67
Nodes (3): Return a set of values from key_col in an existing CSV., Return a set of values from key_col in an existing CSV., read_existing_set()

### Community 80 - "Community 80"
Cohesion: 0.67
Nodes (3): get_csrf_and_company_id(), Using an existing session, visit the company page to get cookies + CSRF token +, Using an existing session, visit the company page to get cookies + CSRF token +

## Knowledge Gaps
- **476 isolated node(s):** `Classify a NEPSE listing by instrument type.  ShareSansar's registry mixes ordin`, `Return the instrument type for a listing's display name.`, `True for ordinary shares — the only instruments the analyser handles.`, `NEPSE Stock CAGR Calculator ============================ Uses data from: https:/`, `Resolve a user-typed symbol to either a company ticker or a sector index.     Re` (+471 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `js()` connect `Community 1` to `Community 3`, `Community 5`, `Community 7`, `Community 8`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 15`, `Community 18`, `Community 20`, `Community 22`, `Community 27`, `Community 30`, `Community 35`, `Community 36`, `Community 37`, `Community 43`, `Community 48`, `Community 51`, `Community 54`?**
  _High betweenness centrality (0.252) - this node is a cross-community bridge._
- **Why does `main()` connect `Community 45` to `Community 34`, `Community 44`, `Community 14`, `Community 52`, `Community 24`, `Community 29`, `Community 62`?**
  _High betweenness centrality (0.099) - this node is a cross-community bridge._
- **Why does `bn` connect `Community 5` to `Community 1`, `Community 8`, `Community 10`, `Community 12`, `Community 28`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **What connects `Classify a NEPSE listing by instrument type.  ShareSansar's registry mixes ordin`, `Return the instrument type for a listing's display name.`, `True for ordinary shares — the only instruments the analyser handles.` to the rest of the system?**
  _476 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.04 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
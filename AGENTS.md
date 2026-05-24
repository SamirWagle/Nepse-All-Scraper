<claude-mem-context>
# Memory Context

# [Nepse-CAGR] recent context, 2026-05-22 11:08pm GMT+5:45

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 39 obs (12,511t read) | 517,472t work | 98% savings

### May 21, 2026
493 8:30p 🟣 NEPSE App Search: Company Name Input Support Requested
494 8:31p 🔵 Nepse-CAGR Extension: Search Input Only Handles Uppercase Ticker Symbols
495 " 🔵 Full Scope of Name-to-Ticker Fix: Multiple Search Inputs Across Two Files
496 " 🔵 Backend Server Endpoints Confirmed: No Search/Resolve Endpoint Exists
497 8:32p 🟣 Server-Side Company Search Functions Added to nepse_cagr_server.py
498 " 🟣 GET /search Endpoint Added to nepse_cagr_server.py
499 " 🔵 analyse.html Search Input Has Ticker-Only Placeholder; URL Param Init Auto-Triggers Search
500 8:33p 🟣 analyse.js doSearch Refactored: Name Resolution + Disambiguation Picker Added
501 " 🟣 Disambiguation Picker CSS Added to analyse.html
502 " 🔵 Both Search Inputs Still Show Ticker-Only Placeholder Text
503 8:34p 🔵 CAGR Page doCagr() Still Uses Raw Uppercase Input — Name Resolution Not Yet Applied
504 " 🟣 CAGR Page doCagr() Refactored: Name Resolution Now Applied to Second Search Input
S296 NEPSE CAGR Chrome extension: add company name search with disambiguation picker (May 21 at 8:34 PM)
S295 Add company name search to NEPSE CAGR Chrome extension — inputs accept full names, show disambiguation picker for multiple matches (May 21 at 8:34 PM)
S297 NEPSE CAGR extension: company name search + disambiguation picker — feature complete, committed, merged to main (May 21 at 8:34 PM)
S298 NEPSE CAGR Chrome extension: accept company names in search boxes, show disambiguation picker for multiple matches (May 21 at 8:36 PM)
S299 NEPSE CAGR extension: company name search — fix Bull & Bear page to resolve names before doBullSearch (May 21 at 8:36 PM)
S300 NEPSE CAGR extension: company name search feature — fully complete and committed to main (May 21 at 8:41 PM)
505 9:48p 🔵 Input Box Rejects Company Names, Accepts Only Tickers
506 " 🔴 search_companies() Gained Normalized Name Matching
507 9:49p 🟣 Paged Company Search Picker Merged to Main
508 " 🔵 Sharesansar Contains Delisted/Merged Company Data
### May 22, 2026
509 6:47a 🟣 Daily Scraper Fixed to Use Full Company Mapping
511 6:52a 🔵 Merged/Older Companies Missing from Extension Name Lookup Files
510 8:44a 🔵 Daily Scraper Architecture: Incremental + Dedup Logic
512 12:49p 🔵 fetch_company_names.py Only Reads company_list.json, Skips Merged Companies
513 12:50p 🔴 fetch_company_names.py Fixed to Source from Full Company Mapping
514 1:55p 🔵 Server search_companies() Reads companies.csv, Not company_names.json
515 1:56p 🔴 Server _load_companies() Patched to Merge All Three Data Sources
517 " 🔵 HAMA Price History Confirmed: 639 Records from 2012 to 2016
518 " 🔵 Extension Bull Cycle Logic Handles Missing Data for Delisted Companies via Error Message Check
516 " 🔵 company_names.json Now Contains Merged Company Names After Re-run
519 2:00p 🟣 New /trading_range Endpoint Added to Server
520 " 🟣 Extension Uses /trading_range to Skip Post-Delisting Bull Cycles
521 " 🔵 apply_patch Failing on analyse.js Due to Whitespace Mismatch
522 2:01p 🟣 analyse.js Fully Patched: getTradingRange + Post-Delisting Guard Applied
523 " 🔵 /trading_range Route Already Present in Server — Duplicate Patch Attempt Rejected
524 " 🔴 Bull Cycle Box Label Fixed: "Not listed yet" → "Merged / Last traded"
525 " 🔵 Git Status Shows Full Scope of --all-companies Scrape: Hundreds of New Company Directories
526 2:02p 🔵 CAGR Dropdown Removal — Element Locations Identified
527 9:39p 🟣 CAGR Calculator Removed from Nav Dropdown
529 " 🔵 Git State: Ahead 49, CAGR Removal Unstaged on Main
528 9:40p 🔴 CAGR Dropdown Removal Verified Complete
530 9:41p ✅ Branch Created for CAGR Dropdown Removal Commit
531 " ✅ Checked Out `codex-remove-cagr-dropdown` Branch

Access 517k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
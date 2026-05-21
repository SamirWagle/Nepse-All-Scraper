<claude-mem-context>
# Memory Context

# [Nepse-CAGR] recent context, 2026-05-21 10:37pm GMT+5:45

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 14 obs (4,412t read) | 324,910t work | 99% savings

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

Access 325k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
<div align="center">

# 📈 NEPSE All Scraper

**A free, open-source data pipeline for the Nepal Stock Exchange.**  
Automatically scrapes prices, dividends, right shares, and floorsheet data  
for **365 listed companies** — committed to this repo every weekday via GitHub Actions.

[![Daily Scraper](https://github.com/SamirWagle/Nepse-All-Scraper/actions/workflows/daily_scraper.yml/badge.svg)](https://github.com/SamirWagle/Nepse-All-Scraper/actions/workflows/daily_scraper.yml)
![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![Data Source](https://img.shields.io/badge/Source-ShareSansar%20%7C%20Merolagani-orange)
![License](https://img.shields.io/badge/License-Educational-green)
![Companies](https://img.shields.io/badge/Companies-365-purple)

</div>

---

## 📦 What's Inside

> This repo is **data-first**. Every weekday after NEPSE closes, GitHub Actions scrapes the latest data and commits it directly back to the `data/` folder. No database, no server — just flat CSV files you can plug into anything.

| Data | Where | Updated |
|---|---|---|
| OHLC price history | `data/company-wise/{SYMBOL}/prices.csv` | Locally (run once) |
| Dividend history | `data/company-wise/{SYMBOL}/dividend.csv` | Every weekday ✅ |
| Right share history | `data/company-wise/{SYMBOL}/right-share.csv` | Every weekday ✅ |
| Full daily floorsheet | `data/floorsheet_YYYY-MM-DD.csv` + `.json` | Every weekday ✅ |

---

## �️ Repository Layout

```
Nepse-All-Scraper/
│
├── .github/
│   └── workflows/
│       └── daily_scraper.yml      # GitHub Actions — runs every weekday at 6:30 PM NPT
│
├── data/
│   ├── company_list.json          # 365 priority company symbols
│   ├── company_id_mapping.json    # Symbol → ShareSansar internal ID
│   ├── floorsheet_YYYY-MM-DD.csv  # Daily floorsheet (all trades)
│   ├── floorsheet_YYYY-MM-DD.json # Same data as JSON
│   └── company-wise/
│       └── {SYMBOL}/
│           ├── prices.csv         # Full OHLC price history
│           ├── dividend.csv       # Dividend history
│           └── right-share.csv    # Right share history
│
└── scraper/
    ├── run_github_actions.py      # ← GitHub Actions entry point
    ├── run_daily.py               # ← Local price scraper CLI
    └── core/
        ├── daily.py               # Orchestrates price scraping
        ├── daily_prices.py        # Daily price summary updater
        ├── floorsheet.py          # Floorsheet scraper (merolagani.com)
        └── history.py             # OHLC price history scraper
```

---

## 🤖 Automation — GitHub Actions

The workflow [`.github/workflows/daily_scraper.yml`](.github/workflows/daily_scraper.yml) runs automatically **every weekday (Mon–Fri) at 6:30 PM Nepal time** (12:45 UTC), right after NEPSE closes.

```
┌─────────────────────────────────────────────────────┐
│              GitHub Actions — Daily Run              │
├─────────────┬───────────────────────────────────────┤
│  Dividends  │  Updates dividend.csv (all 365)        │
│ Right Shares│  Updates right-share.csv (all 365)     │
│  Floorsheet │  Full day's trades from merolagani.com │
│  Commit     │  git push → data/ auto-updated in repo │
└─────────────┴───────────────────────────────────────┘
```

**Trigger manually**: `GitHub → Actions → Daily Scraper → Run workflow`

---

## ⚡ Quickstart

### Prerequisites
```bash
pip install requests beautifulsoup4
```

### Run the same scrape as GitHub Actions (dividends + right shares + floorsheet)
```bash
# All three in one go
python scraper/run_github_actions.py

# Or individually
python scraper/run_github_actions.py --dividends
python scraper/run_github_actions.py --right-shares
python scraper/run_github_actions.py --floorsheet

# Test floorsheet with limited pages (faster)
python scraper/run_github_actions.py --floorsheet --max-pages 3
```

### Scrape full OHLC price history (local only, first-time)
```bash
# Full history for all 365 companies — takes ~2-4 hours on first run
python scraper/run_daily.py --full-scrape

# Incremental — only fetches newer records than what's already in prices.csv
python scraper/run_daily.py --incremental

# Only process newly listed companies (new IPOs)
python scraper/run_daily.py --new-only
```

> **Why are prices local-only?**  
> Price scraping needs the existing `prices.csv` files to know where to stop (incremental logic). Run it locally once, push the data, then automation handles daily updates.

---

## � Data Formats

<details>
<summary><strong>prices.csv</strong></summary>

```
date, open, high, low, ltp, percent_change, qty, turnover
2024-01-15, 1200, 1250, 1190, 1240, +1.5%, 3400, 4216000
```

</details>

<details>
<summary><strong>dividend.csv</strong></summary>

```
fiscal_year, bonus_share, cash_dividend, total_dividend, book_closure_date
2079/80, 10%, 5%, 15%, 2023-12-01
```

</details>

<details>
<summary><strong>right-share.csv</strong></summary>

```
ratio, total_units, issue_price, opening_date, closing_date, status, issue_manager
1:1, 5000000, 100, 2023-11-01, 2023-11-15, Closed, XYZ Capital
```

</details>

<details>
<summary><strong>floorsheet_YYYY-MM-DD.csv</strong></summary>

```
date, sn, contract_no, stock_symbol, buyer, seller, quantity, rate, amount
2024-01-15, 1, 100012345, ADBL, 21, 42, 500, 1240, 620000
```

</details>

---

## ⚙️ How Incremental Scraping Works

```
prices.csv                    ShareSansar AJAX
─────────────                 ──────────────────
Latest date: 2024-01-10  →   Stop fetching when
                              record date ≤ 2024-01-10

Result: Only 1-2 pages fetched instead of 70+
```

`history.py` reads the most recent date from the existing `prices.csv`, passes it as a `stop_date` to the paginator, and halts the moment it hits older data. This makes daily updates take seconds instead of hours.

---

## 🚀 First-Time Setup

```bash
# 1. Clone the repo
git clone https://github.com/SamirWagle/Nepse-All-Scraper.git
cd Nepse-All-Scraper

# 2. Install dependencies
pip install requests beautifulsoup4

# 3. Run the full price history scrape (one-time, takes 2-4 hours)
python scraper/run_daily.py --full-scrape

# 4. Push everything to the repo
git add data/
git commit -m "chore: initial data load"
git push
```

From that point on, GitHub Actions handles everything automatically every weekday. ✅

---

## 🗺️ Roadmap

- [x] **Phase 1** — NEPSE Scraper (prices, dividends, right shares, floorsheet)
- [x] **Phase 2** — GitHub Actions automation + incremental updates
- [ ] **Phase 3** — Frontend / API layer

Want to help build Phase 3? **PRs are welcome.**

---

## ⚠️ Disclaimer

> This project is for **educational purposes only**.  
> Data is sourced from publicly available websites (ShareSansar, Merolagani).  
> Not financial advice. Do your own research before making investment decisions.

---

<div align="center">

Made with ❤️ for the Nepali investor community

</div>
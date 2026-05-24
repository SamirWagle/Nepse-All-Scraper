# Nepsy Scraper

Scrapes NEPSE market data from ShareSansar and Merolagani for 337 priority companies.
All data is stored as CSV files in `data/` and auto-committed by GitHub Actions.

---

## 📂 File Structure

```
scraper/
├── run_github_actions.py   # GitHub Actions entry point (dividends, right shares, floorsheet, mergers)
├── run_daily.py            # Local price update CLI
└── core/
    ├── daily.py            # Orchestrates price scraping
    ├── daily_prices.py     # Daily price summary updater
    ├── floorsheet.py       # Daily floorsheet scraper (merolagani.com)
    ├── mergers.py          # ShareSansar merger registry scraper
    └── history.py          # OHLC price history scraper (incremental)
```

---

## 🤖 GitHub Actions (Automated Daily)

Runs every **weekday at 6:30 PM Nepal time** via `.github/workflows/daily_scraper.yml`.

```
dividends     → data/company-wise/{SYMBOL}/dividend.csv
right-shares  → data/company-wise/{SYMBOL}/right-share.csv
floorsheet    → data/floorsheet_YYYY-MM-DD.csv + .json
mergers       → data/company_mergers.json
```

All output is committed and pushed back to the repo automatically.

---

## 🛠️ Usage

### Install

```bash
pip install requests beautifulsoup4
```

### GitHub Actions script (dividends + right shares + floorsheet + mergers)

```bash
# All three
python scraper/run_github_actions.py

# Individual
python scraper/run_github_actions.py --dividends
python scraper/run_github_actions.py --right-shares
python scraper/run_github_actions.py --floorsheet
python scraper/run_github_actions.py --mergers

# Test floorsheet with limited pages
python scraper/run_github_actions.py --floorsheet --max-pages 3
```

### Price history (run locally)

```bash
# Incremental update — only fetches records newer than what's in prices.csv
python scraper/run_daily.py --incremental

# Full scrape — downloads complete history for all companies (~2-4 hours first time)
python scraper/run_daily.py --full-scrape

# Only process new companies (new IPOs/listings)
python scraper/run_daily.py --new-only
```

---

## 📊 Output Format

### `data/company-wise/{SYMBOL}/prices.csv`
```
date, open, high, low, ltp, percent_change, qty, turnover
```

### `data/company-wise/{SYMBOL}/dividend.csv`
```
fiscal_year, bonus_share, cash_dividend, total_dividend, book_closure_date
```

### `data/company-wise/{SYMBOL}/right-share.csv`
```
ratio, total_units, issue_price, opening_date, closing_date, status, issue_manager
```

### `data/floorsheet_YYYY-MM-DD.csv`
```
date, sn, contract_no, stock_symbol, buyer, seller, quantity, rate, amount
```

### `data/company_mergers.json`
```json
{
  "version": 1,
  "entries": {
    "HAMA": {
      "status": "closed",
      "merged_date": "2016-09-04",
      "merged_into": "CBL",
      "surviving_symbol": "HBL"
    }
  }
}
```

---

## ⚙️ How Incremental Price Scraping Works

`history.py` reads the latest date from `prices.csv`, then passes it as a `stop_date` to the AJAX paginator. The moment it encounters a record older than `stop_date`, it stops fetching — so a daily update fetches only 1-2 pages instead of 70+ pages.

---

## 📝 First-Time Setup

1. Run full price scrape locally (once):
   ```bash
   python scraper/run_daily.py --full-scrape
   ```
2. Commit all data to the repo:
   ```bash
   git add data/
   git commit -m "chore: initial data load"
   git push
   ```
3. GitHub Actions will keep everything updated automatically from then on.

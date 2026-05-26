"""
backfill_merged_listing_dates.py

Backfills ipo_listings.csv with listing dates for merged/delisted companies
that are in company_mergers.json but missing from ipo_listings.csv.

Strategy per symbol (in order):
  1. ShareSansar company page → "Operation Date" field
  2. prices.csv first row date (earliest price data available)
  3. Skip (no data found)

Usage:
    python3 -m scraper.backfill_merged_listing_dates
    python3 -m scraper.backfill_merged_listing_dates --dry-run
"""

import argparse
import csv
import json
import logging
import random
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATA_DIR       = Path(__file__).resolve().parent.parent / "data"
MERGERS_PATH   = DATA_DIR / "company_mergers.json"
LISTINGS_PATH  = DATA_DIR / "ipo_listings.csv"
COMPANY_DIR    = DATA_DIR / "company-wise"

SHARESANSAR_BASE = "https://www.sharesansar.com/company"
REQUEST_HEADERS  = {"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36"}
REQUEST_TIMEOUT  = 15
SLEEP_MIN, SLEEP_MAX = 0.8, 1.5


# ── Helpers ────────────────────────────────────────────────────────────────

def load_ipo_listings():
    """Return dict symbol → listing_date from ipo_listings.csv."""
    if not LISTINGS_PATH.exists():
        return {}
    with open(LISTINGS_PATH, newline='') as f:
        return {r['symbol']: r['listing_date'] for r in csv.DictReader(f) if r.get('symbol')}


def save_ipo_listings(data: dict):
    """Write sorted symbol → date dict back to ipo_listings.csv."""
    records = [{'symbol': s, 'listing_date': d} for s, d in sorted(data.items())]
    with open(LISTINGS_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['symbol', 'listing_date'])
        writer.writeheader()
        writer.writerows(records)
    logger.info(f"Saved {len(records)} records to ipo_listings.csv")


def load_missing_symbols(existing: dict):
    """Return list of symbols in company_mergers.json but absent from ipo_listings."""
    with open(MERGERS_PATH) as f:
        mergers = json.load(f)
    entries = mergers.get('entries', {})
    return sorted(sym for sym in entries if sym not in existing)


def fetch_operation_date(symbol: str):
    """
    Scrape ShareSansar company page for 'Operation Date'.
    Returns YYYY-MM-DD string or None.
    """
    url = f"{SHARESANSAR_BASE}/{symbol.lower()}"
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning(f"  {symbol}: ShareSansar HTTP {r.status_code}")
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        for td in soup.find_all('td'):
            if td.get_text(strip=True) == 'Operation Date':
                nxt = td.find_next_sibling('td')
                if nxt:
                    val = nxt.get_text(strip=True)
                    if val:
                        return val
        logger.warning(f"  {symbol}: 'Operation Date' not found on ShareSansar")
        return None
    except Exception as e:
        logger.error(f"  {symbol}: ShareSansar error — {e}")
        return None


def get_prices_first_date(symbol: str):
    """
    Return the earliest date from data/company-wise/{SYMBOL}/prices.csv.
    Note: this is earliest price data (~2011 for most), not actual IPO date.
    """
    prices_path = COMPANY_DIR / symbol / "prices.csv"
    if not prices_path.exists():
        return None
    try:
        with open(prices_path, newline='') as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
        dates = [r.get('date', '') for r in rows if r.get('date')]
        if not dates:
            return None
        return min(dates)
    except Exception as e:
        logger.error(f"  {symbol}: prices.csv read error — {e}")
        return None


# ── Main ───────────────────────────────────────────────────────────────────

def run(dry_run=False):
    existing = load_ipo_listings()
    logger.info(f"Current ipo_listings.csv: {len(existing)} symbols")

    missing = load_missing_symbols(existing)
    logger.info(f"Missing merged symbols: {len(missing)}")

    results = {}  # symbol → {date, source}
    skipped = []

    for i, symbol in enumerate(missing, 1):
        logger.info(f"[{i}/{len(missing)}] {symbol}")

        # Strategy 1: ShareSansar Operation Date
        date = fetch_operation_date(symbol)
        source = "sharesansar_operation_date"

        # Strategy 2: prices.csv first row
        if not date:
            date = get_prices_first_date(symbol)
            source = "prices_csv_first_date"

        if date:
            results[symbol] = {'date': date, 'source': source}
            logger.info(f"  -> {date} (via {source})")
        else:
            skipped.append(symbol)
            logger.warning(f"  -> no date found, skipped")

        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info(f"Found dates: {len(results)}")
    logger.info(f"Skipped (no data): {len(skipped)}")
    if skipped:
        logger.info(f"Skipped symbols: {skipped}")

    if dry_run:
        logger.info("[DRY RUN] No changes written.")
        for sym, info in results.items():
            print(f"  {sym}: {info['date']} ({info['source']})")
        return

    # Write to ipo_listings.csv
    updated = {**existing, **{sym: info['date'] for sym, info in results.items()}}
    save_ipo_listings(updated)
    logger.info(f"ipo_listings.csv updated: {len(updated)} total symbols")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill listing dates for merged companies")
    parser.add_argument('--dry-run', action='store_true', help="Print results without writing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

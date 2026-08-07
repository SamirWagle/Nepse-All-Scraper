import requests
from bs4 import BeautifulSoup
import csv
import re
import time
import logging
import random
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _clean_date(value):
    """Return a real YYYY-MM-DD string, or None for a source's 'no data' filler.

    ShareHubNepal renders an unknown listing date as "-". That is truthy, so it
    suppressed the Sharepaati fallback and then got written to ipo_listings.csv
    as if it were a date.
    """
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    return text


class ShareHubListingDateScraper:
    """
    Scrapes listing dates from ShareHubNepal company pages:
        https://sharehubnepal.com/company/{SYMBOL}

    Falls back to Sharepaati if ShareHubNepal does not have the date:
        https://sharepaati.com/company/{SYMBOL}

    Saves results to:
        data/ipo_listings.csv

    CSV columns: symbol, listing_date
    """

    BASE_URL = "https://sharehubnepal.com/company"
    SHAREPAATI_BASE_URL = "https://sharepaati.com/company"
    OUTPUT_FILE = "ipo_listings.csv"
    FIELDNAMES = ["symbol", "listing_date"]

    def __init__(self):
        self.data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self.output_path = self.data_dir / self.OUTPUT_FILE

    # ------------------------------------------------------------------
    # CSV helpers
    # ------------------------------------------------------------------

    def _load_existing(self):
        """Return dict of symbol -> listing_date already in ipo_listings.csv."""
        if not self.output_path.exists():
            return {}
        try:
            with open(self.output_path, newline='') as f:
                reader = csv.DictReader(f)
                return {row['symbol']: row['listing_date'] for row in reader if row.get('symbol')}
        except Exception as e:
            logger.warning(f"Could not read existing ipo_listings.csv: {e}")
            return {}

    def _save_records(self, records):
        """
        Write records to ipo_listings.csv (full overwrite with merged data).
        records: list of {'symbol': ..., 'listing_date': ...}
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.output_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()
                writer.writerows(records)
            logger.info(f"[OK] Saved {len(records)} records to ipo_listings.csv.")
        except Exception as e:
            logger.error(f"Failed to write ipo_listings.csv: {e}")

    # ------------------------------------------------------------------
    # Per-symbol fetch
    # ------------------------------------------------------------------

    def fetch_listing_date(self, symbol):
        """
        Fetch listing date for a single symbol.
        Tries ShareHubNepal first, falls back to Sharepaati.
        Cross-checks against prices.csv first trading date — if the scraped date
        is AFTER the first observed trade, it's wrong (impossible to trade before
        listing), so we override with the first-trade date and log a warning.
        Returns date string (YYYY-MM-DD) or None if not found.
        """
        scraped = _clean_date(self._fetch_from_sharehub(symbol))
        if not scraped:
            logger.info(f"  {symbol}: ShareHubNepal miss — trying Sharepaati")
            scraped = _clean_date(self._fetch_from_sharepaati(symbol))

        if not scraped:
            # Both sources blank. For a recent listing the first observed trade
            # IS the listing date, and it always beats storing a placeholder.
            first_trade = self._first_trade_date(symbol)
            if first_trade:
                logger.info(f"  {symbol}: no source date — using first trade {first_trade}")
                return first_trade
            return None

        # Cross-check against prices.csv first row (ground truth)
        first_trade = self._first_trade_date(symbol)
        if first_trade and scraped > first_trade:
            logger.warning(
                f"  {symbol}: scraped listing_date {scraped} > first_trade {first_trade} "
                f"— scraper source has wrong data. Overriding with first_trade."
            )
            return first_trade

        return scraped

    def _first_trade_date(self, symbol):
        """Return earliest date string from data/company-wise/{SYMBOL}/prices.csv, or None."""
        prices_path = self.data_dir / "company-wise" / symbol / "prices.csv"
        if not prices_path.exists():
            return None
        earliest = None
        try:
            with open(prices_path, newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    d = row.get('date')
                    if d and (earliest is None or d < earliest):
                        earliest = d
        except Exception as e:
            logger.warning(f"  {symbol}: could not read prices.csv for cross-check: {e}")
            return None
        return earliest

    def _fetch_from_sharehub(self, symbol):
        """Fetch listing date from ShareHubNepal. Returns YYYY-MM-DD or None."""
        url = f"{self.BASE_URL}/{symbol}"
        try:
            r = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36"},
                timeout=20
            )
            if r.status_code != 200:
                logger.warning(f"  {symbol}: ShareHubNepal HTTP {r.status_code}")
                return None

            soup = BeautifulSoup(r.text, 'html.parser')
            for el in soup.find_all(string='Listing Date'):
                row = el.parent.parent  # <tr>
                tds = row.find_all('td')
                if len(tds) >= 2:
                    date = tds[1].get_text(strip=True)
                    if date:
                        return date
            logger.warning(f"  {symbol}: 'Listing Date' not found on ShareHubNepal")
            return None

        except Exception as e:
            logger.error(f"  {symbol} (ShareHubNepal): {e}")
            return None

    def _fetch_from_sharepaati(self, symbol):
        """
        Fetch listing date from Sharepaati as fallback.
        Page uses <dt>Listing Date:</dt><dd>YYYY-MM-DD</dd> structure.
        Returns YYYY-MM-DD or None.
        """
        url = f"{self.SHAREPAATI_BASE_URL}/{symbol}"
        try:
            r = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36"},
                timeout=20
            )
            if r.status_code != 200:
                logger.warning(f"  {symbol}: Sharepaati HTTP {r.status_code}")
                return None

            soup = BeautifulSoup(r.text, 'html.parser')
            for dt in soup.find_all('dt'):
                if 'Listing Date' in dt.get_text():
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        date = dd.get_text(strip=True)
                        if date:
                            return date
            logger.warning(f"  {symbol}: 'Listing Date' not found on Sharepaati")
            return None

        except Exception as e:
            logger.error(f"  {symbol} (Sharepaati): {e}")
            return None

    # ------------------------------------------------------------------
    # Main scrape
    # ------------------------------------------------------------------

    def scrape_symbols(self, symbols, skip_existing=True):
        """
        Scrape listing dates for a list of symbols.

        :param symbols: list of stock symbol strings
        :param skip_existing: skip symbols already in ipo_listings.csv
        :returns: dict of symbol -> listing_date for newly fetched symbols
        """
        existing = self._load_existing()
        logger.info(f"Already have {len(existing)} symbols in ipo_listings.csv.")

        # A failed lookup is stored as "-", and treating that as "already have
        # it" made the failure permanent — SOHL stayed blank because the only
        # attempt to resolve it came back empty. Retry those placeholders.
        resolved = {s for s, d in existing.items() if str(d).strip() not in ("", "-")}
        to_fetch = [s for s in symbols if s not in resolved] if skip_existing else symbols
        logger.info(f"Fetching {len(to_fetch)} symbols...")

        newly_fetched = {}
        for i, symbol in enumerate(to_fetch, 1):
            logger.info(f"  [{i}/{len(to_fetch)}] {symbol}")
            date = self.fetch_listing_date(symbol)
            if date:
                newly_fetched[symbol] = date
                logger.info(f"    -> {date}")
            else:
                logger.warning(f"    -> not found")
            time.sleep(random.uniform(0.5, 1.2))  # polite delay

        # Merge and save
        merged = {**existing, **newly_fetched}
        records = [{'symbol': s, 'listing_date': d} for s, d in sorted(merged.items())]
        self._save_records(records)

        logger.info(f"[DONE] {len(newly_fetched)} new, {len(existing)} existing, {len(merged)} total.")
        return newly_fetched

    def scrape_from_prices_csv(self, prices_csv_path, skip_existing=True):
        """
        Read all unique symbols from prices.csv and scrape their listing dates.
        """
        prices_path = Path(prices_csv_path)
        if not prices_path.exists():
            logger.error(f"prices.csv not found at {prices_path}")
            return {}

        symbols = set()
        with open(prices_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                s = row.get('symbol') or row.get('Symbol') or row.get('ticker')
                if s:
                    symbols.add(s.strip().upper())

        logger.info(f"Found {len(symbols)} unique symbols in prices.csv.")
        return self.scrape_symbols(sorted(symbols), skip_existing=skip_existing)

    def get(self, symbol):
        """
        Look up a single symbol in ipo_listings.csv.
        Returns listing_date string or None.
        """
        existing = self._load_existing()
        return existing.get(symbol.upper())


if __name__ == "__main__":
    import sys
    scraper = ShareHubListingDateScraper()

    if len(sys.argv) > 1:
        # Single symbol lookup/fetch
        symbol = sys.argv[1].upper()
        date = scraper.fetch_listing_date(symbol)
        print(f"{symbol}: {date}")
    else:
        # Full scrape from prices.csv
        prices_csv = Path(__file__).resolve().parent.parent.parent / "data" / "prices.csv"
        scraper.scrape_from_prices_csv(prices_csv)

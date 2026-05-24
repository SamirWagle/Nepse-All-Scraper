import fcntl
import logging
import argparse
import sys
import time
import json
from pathlib import Path

LOCK_FILE = "/tmp/nepse_daily_scraper.lock"

from .history import ShareSansarHistoryScraper
from .listing_date import ShareHubListingDateScraper
from .mergers import run_merger_scrape

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).resolve().parent / "daily_scraper.log")
    ]
)
logger = logging.getLogger(__name__)


class DailyScraperManager:
    """
    Manages daily scraping tasks for priority companies (company_list.json):
      - Price history updates via ShareSansar (history.py)
      - IPO listing dates via ShareSansar (ipo_listing.py)
    """

    def __init__(self, base_dir="data"):
        self.price_scraper = ShareSansarHistoryScraper()
        self.ipo_scraper = ShareHubListingDateScraper()

        self.data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self.company_wise_dir = self.data_dir / "company-wise"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_priority_companies(self):
        """Load the priority company list from company_list.json."""
        list_path = self.data_dir / "company_list.json"
        if not list_path.exists():
            logger.warning("company_list.json not found — falling back to all mapped companies.")
            mapping = self.price_scraper._load_company_id_map(force_update=True)
            return set(mapping.keys())

        with open(list_path) as f:
            return set(json.load(f))

    def get_all_companies(self):
        """Load every symbol known to the ShareSansar mapping, including merged/delisted companies."""
        mapping_path = self.data_dir / "company_id_mapping.json"
        if not mapping_path.exists():
            logger.warning("company_id_mapping.json not found — falling back to priority list.")
            return self.get_priority_companies()
        with open(mapping_path) as f:
            mapping = json.load(f)
        return set(mapping.keys())

    def get_existing_companies(self):
        """Return symbols that already have a prices.csv."""
        if not self.company_wise_dir.exists():
            return set()
        return {
            d.name for d in self.company_wise_dir.iterdir()
            if d.is_dir() and (d / "prices.csv").exists()
        }

    # ------------------------------------------------------------------
    # Price scraping
    # ------------------------------------------------------------------

    def _update_prices(self, symbols, force_full=False):
        """Scrape / update prices.csv for the given symbols."""
        existing = self.get_existing_companies()
        new_companies = symbols - existing
        existing_priority = symbols & existing
        failed_count = 0

        logger.info(f"Prices — new: {len(new_companies)}, existing: {len(existing_priority)}")

        # New companies: full history
        for i, sym in enumerate(sorted(new_companies), 1):
            try:
                logger.info(f"  [NEW {i}/{len(new_companies)}] Full price scrape: {sym}")
                records = self.price_scraper.scrape_company_history(sym)
                if records:
                    self.price_scraper.update_company_csv(sym, records)
                    logger.info(f"    Saved {len(records)} records")
                else:
                    logger.warning(f"    No data found for {sym}")
            except Exception as e:
                logger.error(f"    Failed {sym}: {e}")
                failed_count += 1
            time.sleep(1)

        # Existing companies: incremental (stop early once we hit known dates)
        for i, sym in enumerate(sorted(existing_priority), 1):
            try:
                stop_date = self.price_scraper.get_latest_date(sym)
                logger.info(f"  [UPD {i}/{len(existing_priority)}] Prices: {sym} (newest: {stop_date})")
                records = self.price_scraper.scrape_company_history(sym, stop_date=stop_date)
                if records:
                    self.price_scraper.update_company_csv(sym, records)
                    logger.info(f"    +{len(records)} records")
                else:
                    logger.info(f"    No new data")
            except Exception as e:
                logger.error(f"    Failed {sym}: {e}")
                failed_count += 1
            time.sleep(1)

        return failed_count


    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_daily_update(self, check_new_only=False, force_full=False, priority_only=True, update_mergers=True):
        """
        Run the daily update:
          - Refresh company ID mapping (catches new IPOs)
          - Update prices for priority companies
          - Update IPO listing dates
          - Update merger registry

        :param check_new_only: Only scrape NEW companies (prices), skip existing.
        :param force_full:     Force full re-scrape of prices.
        :param priority_only:  Use company_list.json filter (always True in practice).
        """
        lock_fh = open(LOCK_FILE, 'w')
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.error("Another instance is already running (lock held on %s). Exiting.", LOCK_FILE)
            lock_fh.close()
            sys.exit(1)

        try:
            self._run_daily_update_inner(check_new_only=check_new_only, force_full=force_full, priority_only=priority_only)
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
            lock_fh.close()

    def _run_daily_update_inner(self, check_new_only=False, force_full=False, priority_only=True):
        logger.info("=== Daily Update Started ===")

        target = self.get_priority_companies() if priority_only else self.get_all_companies()
        logger.info(f"Priority companies: {len(target)}")

        if not check_new_only:
            logger.info("--- Updating prices ---")
            failed_count = self._update_prices(target, force_full=force_full)
        else:
            logger.info("--- New companies only (prices) ---")
            existing = self.get_existing_companies()
            new_only = target - existing
            failed_count = self._update_prices(new_only, force_full=False)

        # Incrementally update IPO listing dates (fast: stops on first known symbol)
        logger.info("--- Updating IPO listing dates ---")
        try:
            self.ipo_scraper.scrape_symbols(target, skip_existing=True)
        except Exception as e:
            logger.error(f"IPO listing scrape failed: {e}")
            failed_count += 1

        if update_mergers:
            # Refresh merger registry from ShareSansar
            logger.info("--- Updating merger registry ---")
            try:
                run_merger_scrape()
            except Exception as e:
                logger.error(f"Merger registry scrape failed: {e}")
                failed_count += 1

        logger.info("=== Daily Update Completed ===")
        if failed_count > 0:
            logger.error(f"{failed_count} company/companies failed — exiting with code 1")
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShareSansar Daily Scraper (prices)")
    parser.add_argument("--new-only", action="store_true", help="Only scrape new companies (prices)")
    parser.add_argument("--full-scrape", action="store_true", help="Force full price re-scrape")
    args = parser.parse_args()

    manager = DailyScraperManager()
    manager.run_daily_update(
        check_new_only=args.new_only,
        force_full=args.full_scrape,
    )


import logging
import argparse
import time
import json
from pathlib import Path

from .history import ShareSansarHistoryScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("daily_scraper.log")
    ]
)
logger = logging.getLogger(__name__)


class DailyScraperManager:
    """
    Manages daily scraping tasks for priority companies (company_list.json):
      - Price history updates via ShareSansar (history.py)
    """

    def __init__(self, base_dir="data"):
        self.price_scraper = ShareSansarHistoryScraper()

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
            time.sleep(1)


    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_daily_update(self, check_new_only=False, force_full=False, priority_only=True):
        """
        Run the daily update:
          - Refresh company ID mapping (catches new IPOs)
          - Update prices for priority companies

        :param check_new_only: Only scrape NEW companies (prices), skip existing.
        :param force_full:     Force full re-scrape of prices.
        :param priority_only:  Use company_list.json filter (always True in practice).
        """
        logger.info("=== Daily Update Started ===")

        target = self.get_priority_companies()
        logger.info(f"Priority companies: {len(target)}")

        if not check_new_only:
            logger.info("--- Updating prices ---")
            self._update_prices(target, force_full=force_full)
        else:
            logger.info("--- New companies only (prices) ---")
            existing = self.get_existing_companies()
            new_only = target - existing
            self._update_prices(new_only, force_full=False)

        logger.info("=== Daily Update Completed ===")


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

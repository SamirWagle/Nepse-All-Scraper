
import sys
import os
import argparse

# Ensure scraper package is importable
# Add the 'scraper' directory to Python path if not already there
sys.path.append(os.getcwd())

from core.daily import DailyScraperManager

def main():
    parser = argparse.ArgumentParser(description="ShareSansar Daily Scraper")
    
    # Modes
    parser.add_argument("--new-only", action="store_true", help="Only check for and scrape new companies. Does not update existing ones.")
    parser.add_argument("--full-scrape", action="store_true", help="Force full scraping of all existing companies (slow)")
    parser.add_argument("--incremental", action="store_true", default=True, help="Default mode: Check existing companies for NEW updates only (fast)")
    parser.add_argument("--all-companies", action="store_true", help="Scrape ALL companies found, ignoring the priority list.")
    parser.add_argument("--skip-mergers", action="store_true", help="Skip refreshing the merger registry during the daily run.")
    parser.add_argument("--skip-index", action="store_true", help="Skip the NEPSE index/sub-index history scrape.")
    parser.add_argument("--skip-alerts", action="store_true", help="Skip the Karma position-alarm check.")

    args = parser.parse_args()
    
    manager = DailyScraperManager()
    
    priority_only = not args.all_companies
    
    if args.new_only:
        print("Running NEW COMPANY detection only...")
        manager.run_daily_update(check_new_only=True, priority_only=priority_only, update_mergers=not args.skip_mergers)
    elif args.full_scrape:
        print("Running FULL SCRAPE for companies...")
        manager.run_daily_update(force_full=True, priority_only=priority_only, update_mergers=not args.skip_mergers)
    else:
        print("Running STANDARD DAILY UPDATE (New Companies + Incremental Updates)...")
        manager.run_daily_update(force_full=False, priority_only=priority_only, update_mergers=not args.skip_mergers)

    # Sync listing dates for any new symbols not yet in ipo_listings.csv
    print("\nChecking for new symbols missing listing dates...")
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scraper.core.listing_date import ShareHubListingDateScraper
    listing_scraper = ShareHubListingDateScraper()
    company_wise = Path(__file__).parent.parent / "data" / "company-wise"
    symbols = sorted([p.name for p in company_wise.iterdir() if p.is_dir()])
    listing_scraper.scrape_symbols(symbols, skip_existing=True)

    # Index history and position alarms run last because both depend on the
    # fresh company prices scraped above. The index scrape was previously not
    # wired in at all, which is why data/index/*/history.csv went stale.
    repo = Path(__file__).parent.parent
    if not args.skip_index:
        run_step("index history", [sys.executable, str(repo / "scraper" / "index_history.py"), "--all"])
    if not args.skip_alerts:
        run_step("karma alerts", [sys.executable, str(repo / "scripts" / "karma_alerts.py"), "watch"])


def run_step(name: str, cmd: list) -> None:
    """Run a follow-on step without letting its failure kill the rest of the run.

    A failure here is logged loudly rather than raised: yesterday's data plus a
    visible warning beats aborting the daily job, and the alarm step reports
    staleness on its own rather than giving a false all-clear.
    """
    import subprocess

    print(f"\n=== {name} ===", flush=True)
    try:
        result = subprocess.run(cmd, timeout=1800)
        if result.returncode != 0:
            print(f"WARNING: {name} exited {result.returncode}. Data may be stale.")
    except subprocess.TimeoutExpired:
        print(f"WARNING: {name} timed out after 30 min. Data may be stale.")
    except Exception as exc:
        print(f"WARNING: {name} failed: {exc}. Data may be stale.")


if __name__ == "__main__":
    main()

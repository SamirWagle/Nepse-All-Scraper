
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
    
    args = parser.parse_args()
    
    manager = DailyScraperManager()
    
    priority_only = not args.all_companies
    
    if args.new_only:
        print("Running NEW COMPANY detection only...")
        manager.run_daily_update(check_new_only=True, priority_only=priority_only)
    elif args.full_scrape:
        print("Running FULL SCRAPE for companies...")
        manager.run_daily_update(force_full=True, priority_only=priority_only)
    else:
        print("Running STANDARD DAILY UPDATE (New Companies + Incremental Updates)...")
        manager.run_daily_update(force_full=False, priority_only=priority_only)

if __name__ == "__main__":
    main()

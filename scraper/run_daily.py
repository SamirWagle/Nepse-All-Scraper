
import sys
import os
import argparse
from pathlib import Path

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
    parser.add_argument("--skip-floorsheet", action="store_true", help="Skip today's floorsheet scrape.")
    parser.add_argument("--skip-corporate-actions", action="store_true", help="(default) Skip the dividend and right-share scrapes.")
    parser.add_argument("--with-corporate-actions", action="store_true", help="Also re-crawl dividends and right shares (slow — hours; weekly job).")

    args = parser.parse_args()

    lock = _acquire_lock()
    if lock is None:
        print("Another daily run is already in progress — exiting.")
        return

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

    # Floorsheet used to run only in GitHub Actions. That workflow stopped
    # committing on 2026-05-09 and nobody noticed for three months, so the
    # local cron owns it now — the CI step is a harmless duplicate if it runs.
    #
    # The scraper stamps every row with today's date rather than the trade date
    # on the page, so running it when the market was closed files yesterday's
    # trades under today. Only run it on a day that actually traded.
    if not args.skip_floorsheet:
        if _market_traded_today(repo):
            run_step("floorsheet", [sys.executable, str(repo / "scraper" / "run_github_actions.py"), "--floorsheet"])
        else:
            print("\n=== floorsheet ===\nSkipped: no trades recorded for today (market closed).")

    # Dividends and right shares were CI-only too, so they died with the
    # workflow on 2026-05-09 alongside the floorsheet. Same treatment.
    #
    # These re-crawl EVERY company's full dividend/right-share history — data
    # that changes a few times a year — and took 8h29m on 2026-08-31 alone.
    # Nightly was never the right cadence, so they're opt-in now and run from a
    # separate weekly job. Prices, index and floorsheet stay nightly.
    runner = str(repo / "scraper" / "run_github_actions.py")
    if args.with_corporate_actions:
        run_step("dividends", [sys.executable, runner, "--dividends"], timeout=4 * 3600)
        run_step("right shares", [sys.executable, runner, "--right-shares"], timeout=4 * 3600)

    if not args.skip_alerts:
        run_step("karma alerts", [sys.executable, str(repo / "scripts" / "karma_alerts.py"), "watch"])

    # Last word of the run: what is current and what is not. A step that dies
    # quietly still shows up here as a stale product.
    run_step("data freshness", [sys.executable, str(repo / "scripts" / "data_freshness.py")])


def _market_traded_today(repo: Path) -> bool:
    """True if the prices just scraped carry today's date."""
    from datetime import date

    sys.path.insert(0, str(repo / "scripts"))
    try:
        from data_freshness import _newest_price_date
    except Exception as exc:
        print(f"WARNING: could not check trading day ({exc}); assuming market traded.")
        return True
    return _newest_price_date() == date.today()


def _acquire_lock():
    """Hold an exclusive lock for the run, or return None if one is already held.

    Without this, a run that overruns its schedule is joined by the next one and
    they fight over the same CSVs.  The handle is returned (not closed) so the
    lock lives as long as the process.
    """
    import fcntl

    handle = open(Path(__file__).parent.parent / ".daily_run.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle


def run_step(name: str, cmd: list, timeout: int = 1800) -> None:
    """Run a follow-on step without letting its failure kill the rest of the run.

    A failure here is logged loudly rather than raised: yesterday's data plus a
    visible warning beats aborting the daily job, and the alarm step reports
    staleness on its own rather than giving a false all-clear.

    The child gets its own process group so a timeout kills the whole tree.
    subprocess.run() only kills the direct child, which is why the 2026-08-31
    dividend step kept logging for 8 hours after "timed out after 30 min".
    """
    import signal
    import subprocess

    print(f"\n=== {name} ===", flush=True)
    proc = None
    try:
        proc = subprocess.Popen(cmd, start_new_session=True)
        returncode = proc.wait(timeout=timeout)
        if returncode != 0:
            print(f"WARNING: {name} exited {returncode}. Data may be stale.")
    except subprocess.TimeoutExpired:
        _kill_tree(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=30)
        except Exception:
            _kill_tree(proc, signal.SIGKILL)
        print(f"WARNING: {name} timed out after {timeout // 60} min (killed). Data may be stale.")
    except Exception as exc:
        print(f"WARNING: {name} failed: {exc}. Data may be stale.")


def _kill_tree(proc, sig) -> None:
    """Signal the child's whole process group; orphans are the thing to avoid."""
    if proc is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Backfill historical floorsheets from merolagani, one session per CSV.

The daily scraper can only ever capture the current session, so every day the
Mac was asleep at 17:30 left a permanent hole (see data/floorsheet — 53 files
where there should be hundreds). merolagani's floorsheet page has a date
filter, which this drives to fetch past sessions.

Resumable by design: a session that already has a CSV is skipped, so an
interrupted run (sleep, reboot, Ctrl-C) is restarted by simply running it
again. Trading days come from the NEPSE index history rather than a weekday
rule, so public holidays are never requested.

Usage:
  python3 scripts/backfill_floorsheet.py --since 2026-01-01
  python3 scripts/backfill_floorsheet.py --since 2026-01-01 --dry-run
"""

import argparse
import random
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scraper"))

import pandas as pd  # noqa: E402
from run_github_actions import scrape_floorsheet, save_floorsheet, FLOORSHEET_DIR  # noqa: E402

INDEX_HISTORY = REPO / "data" / "index" / "nepse" / "history.csv"


def trading_days(since: date) -> list:
    """Sessions the market actually held, newest last."""
    df = pd.read_csv(INDEX_HISTORY, parse_dates=["date"])
    return sorted({d.date() for d in df["date"] if d.date() >= since})


def already_have() -> set:
    return {
        datetime.strptime(m.group(1), "%Y-%m-%d").date()
        for p in FLOORSHEET_DIR.glob("floorsheet_*.csv")
        if (m := re.search(r"(\d{4}-\d\d-\d\d)", p.name))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="First session to backfill (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be fetched, then exit")
    parser.add_argument("--limit", type=int, help="Stop after N sessions (useful for a first test)")
    parser.add_argument("--workers", type=int, default=1, help="How many workers share this backfill")
    parser.add_argument("--worker-id", type=int, default=0, help="This worker's index (0-based)")
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d").date()
    have = already_have()
    missing = [d for d in trading_days(since) if d not in have]
    # Interleave rather than split into blocks: every worker then covers the
    # whole span, so stopping one early leaves gaps spread thin instead of a
    # solid missing quarter. Each session is a separate file, so workers never
    # write the same path.
    if args.workers > 1:
        missing = missing[args.worker_id::args.workers]
    if args.limit:
        missing = missing[:args.limit]

    print(f"Sessions since {since}: {len(trading_days(since))} | already held: {len(have)} | to fetch: {len(missing)}")
    if args.dry_run:
        for d in missing:
            print(f"  would fetch {d}")
        return 0
    if not missing:
        print("Nothing to do.")
        return 0

    done = failed = 0
    for i, day in enumerate(missing, 1):
        print(f"\n[{i}/{len(missing)}] {day}", flush=True)
        try:
            records = scrape_floorsheet(for_date=day)
        except Exception as exc:
            print(f"  FAILED {day}: {exc}", flush=True)
            failed += 1
            continue

        if not records:
            # No rows: a holiday the index still lists, or the filter returned
            # nothing. Leave no file so a later run retries it.
            print(f"  no rows for {day} — skipped", flush=True)
            failed += 1
            continue

        save_floorsheet(records)
        done += 1
        time.sleep(random.uniform(2, 4))  # be a polite guest on their server

    print(f"\nBackfill finished: {done} sessions saved, {failed} skipped/failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

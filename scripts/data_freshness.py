#!/usr/bin/env python3
"""
Report how stale each data product is, and fail loudly when one falls behind.

Written after a NameError in the daily scraper silently killed every step after
the price scrape for ~2.5 months. Prices stayed current, so nothing looked
wrong. This check exists so the next silent failure announces itself the same
day instead of being discovered by accident.

Run with: python3 scripts/data_freshness.py
Exit code 1 if any product breaches its threshold.
"""

import csv
import re
import sys
from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# NEPSE trades Sunday-Thursday, so a 4-day allowance covers a normal weekend
# plus one public holiday before anything is called stale.
TRADING_DAY_TOLERANCE = 4
MONTHLY_TOLERANCE = 75      # NRB publishes monthly stats ~2 months in arrears
REGISTRY_TOLERANCE = 7
WEEKLY_TOLERANCE = 10        # nepsealpha quarterly runs on a weekly cron

# Sub-indices NEPSE has retired. The combined Insurance index stopped on
# 2018-07-16, the day before Non-Life Insurance began; Life Insurance and
# Non-Life Insurance carry it forward. Its history is complete, not stale.
RETIRED_INDICES = {"insurance"}

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _parse(value) -> date | None:
    match = _DATE_RE.search(str(value or ""))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _last_date_in_column(path: Path, column: str) -> date | None:
    """Max date in a named CSV column. Scans fully — these files are small."""
    if not path.exists():
        return None
    try:
        with path.open(newline="") as fh:
            dates = [_parse(row.get(column, "")) for row in csv.DictReader(fh)]
    except Exception:
        return None
    found = [d for d in dates if d]
    return max(found) if found else None


def _mtime_date(path: Path) -> date | None:
    if not path.exists():
        return None
    return date.fromtimestamp(path.stat().st_mtime)


def _newest_price_date() -> date | None:
    company_dir = DATA_DIR / "company-wise"
    if not company_dir.exists():
        return None
    dates = [_last_date_in_column(p, "date") for p in company_dir.glob("*/prices.csv")]
    found = [d for d in dates if d]
    return max(found) if found else None


def _oldest_index_date() -> tuple[date | None, str]:
    """Oldest last-updated date across sub-indices, so one dead feed is visible."""
    index_dir = DATA_DIR / "index"
    if not index_dir.exists():
        return None, ""
    worst, worst_name = None, ""
    for history in sorted(index_dir.glob("*/history.csv")):
        if history.parent.name in RETIRED_INDICES:
            continue
        d = _last_date_in_column(history, "date")
        if d and (worst is None or d < worst):
            worst, worst_name = d, history.parent.name
    return worst, worst_name


def _typical_mtime(pattern: str) -> date | None:
    """Median mtime across a glob, for per-company files that carry no scrape
    timestamp of their own — a fiscal year is not a date the scrape ran.

    Median, not max: a full run rewrites every file that has data, so the
    median tracks the last complete pass. Max would report fresh after a single
    file was touched, which is exactly how a one-symbol test run masked three
    months of stale right-share data.
    """
    dates = sorted(d for d in (_mtime_date(p) for p in DATA_DIR.glob(pattern)) if d)
    return dates[len(dates) // 2] if dates else None


def _newest_floorsheet_date() -> date | None:
    floorsheet_dir = DATA_DIR / "floorsheet"
    if not floorsheet_dir.exists():
        return None
    dates = [_parse(p.name) for p in floorsheet_dir.glob("floorsheet_*.csv")]
    found = [d for d in dates if d]
    return max(found) if found else None


def collect() -> list[dict]:
    """Return one row per data product: name, last date, tolerance in days."""
    worst_index, worst_index_name = _oldest_index_date()
    index_label = f"index history (oldest: {worst_index_name})" if worst_index_name else "index history"
    rates_csv = DATA_DIR / "interest_rates" / "fd_rates.csv"

    return [
        {"product": "company prices", "last": _newest_price_date(), "tolerance": TRADING_DAY_TOLERANCE},
        {"product": index_label, "last": worst_index, "tolerance": TRADING_DAY_TOLERANCE},
        {"product": "floorsheet", "last": _newest_floorsheet_date(), "tolerance": TRADING_DAY_TOLERANCE},
        {"product": "ipo listings", "last": _mtime_date(DATA_DIR / "ipo_listings.csv"), "tolerance": TRADING_DAY_TOLERANCE},
        {"product": "interest rates", "last": _last_date_in_column(rates_csv, "date"), "tolerance": MONTHLY_TOLERANCE},
        {"product": "dividends", "last": _typical_mtime("company-wise/*/dividend.csv"), "tolerance": REGISTRY_TOLERANCE},
        {"product": "right shares", "last": _typical_mtime("company-wise/*/right-share.csv"), "tolerance": REGISTRY_TOLERANCE},
        {"product": "fundamentals", "last": _typical_mtime("company-wise/*/fundamentals.json"), "tolerance": TRADING_DAY_TOLERANCE},
        {"product": "quarterly (nepsealpha)", "last": _typical_mtime("company-wise/*/nepsealpha_quarterly.json"), "tolerance": WEEKLY_TOLERANCE},
        {"product": "btc history", "last": _last_date_in_column(DATA_DIR / "btc" / "history.csv", "date"), "tolerance": TRADING_DAY_TOLERANCE},
        {"product": "merger registry", "last": _mtime_date(DATA_DIR / "company_mergers.json"), "tolerance": REGISTRY_TOLERANCE},
        {"product": "company registry", "last": _mtime_date(DATA_DIR / "company_id_mapping.json"), "tolerance": REGISTRY_TOLERANCE},
    ]


def report(today: date | None = None) -> int:
    """Print the freshness table. Returns the number of stale products."""
    today = today or date.today()
    rows = collect()

    print(f"{'product':<34} {'last update':<14} {'age':>6}  status")
    print("-" * 70)

    stale = 0
    for row in rows:
        last = row["last"]
        if last is None:
            print(f"{row['product']:<34} {'MISSING':<14} {'-':>6}  STALE")
            stale += 1
            continue
        age = (today - last).days
        is_stale = age > row["tolerance"]
        stale += is_stale
        status = f"STALE (> {row['tolerance']}d)" if is_stale else "ok"
        print(f"{row['product']:<34} {last.isoformat():<14} {age:>5}d  {status}")

    if stale:
        print(f"\n{stale} data product(s) stale — the daily pipeline is not completing.")
    else:
        print("\nAll data products current.")
    return stale


def _self_check() -> None:
    assert _parse("floorsheet_2026-05-09.csv") == date(2026, 5, 9)
    assert _parse("2026-13-45") is None, "invalid calendar date must not parse"
    assert _parse("not a date") is None
    assert _parse("") is None
    assert _parse(None) is None
    assert _last_date_in_column(Path("/nonexistent/prices.csv"), "date") is None
    assert _mtime_date(Path("/nonexistent")) is None
    print("data_freshness self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        sys.exit(1 if report() else 0)

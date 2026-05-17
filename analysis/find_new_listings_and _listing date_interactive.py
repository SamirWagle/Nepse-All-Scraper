#!/usr/bin/env python3
"""
Interactive NEPSE new listings tool.
Run with: python3 find_new_listings_interactive.py

All CSVs saved to Research/ folder.
"""

import re
import sys
import json
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from nepse_cagr import calculate_cagr, get_all_symbols

DEFAULT_DATA_DIR   = Path(__file__).parent.parent / "data"
DEFAULT_INVESTMENT = 100_000
START_DATE         = date(2022, 9, 25)
RESEARCH_DIR       = Path(__file__).parent.parent / "Research"
MISS_DAYS          = 10   # days missed from listing

# Load company names once
_NAMES_PATH = Path(__file__).parent.parent / "data" / "company_names.json"
_COMPANY_NAMES: dict = {}
if _NAMES_PATH.exists():
    with open(_NAMES_PATH) as _f:
        _COMPANY_NAMES = json.load(_f)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_stock_name(symbol: str) -> str:
    raw = _COMPANY_NAMES.get(symbol, symbol)
    return re.sub(r'\s*\(\s*[A-Z0-9]+\s*\)\s*$', '', raw).strip() or raw


def get_first_trading_date(symbol: str, data_dir: Path) -> date | None:
    path = data_dir / "company-wise" / symbol / "prices.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"], usecols=["date"])
        return df["date"].min().date()
    except Exception:
        return None


def get_price_on_date(symbol: str, target: date, data_dir: Path) -> float | None:
    """
    Return the closing price (ltp) on or nearest to target date.
    prices.csv is sorted descending; we sort ascending and find the
    closest available trading day on or after target, falling back
    to the nearest day before if needed.
    """
    path = data_dir / "company-wise" / symbol / "prices.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"], usecols=["date", "ltp"])
        df.sort_values("date", ascending=True, inplace=True)
        target_ts = pd.Timestamp(target)

        after = df[df["date"] >= target_ts]
        if not after.empty:
            return float(after.iloc[0]["ltp"])

        before = df[df["date"] < target_ts]
        if not before.empty:
            return float(before.iloc[-1]["ltp"])

        return None
    except Exception:
        return None


def get_cagr(r: dict) -> float:
    for key in ("cagr_pct", "cagr_%", "cagr", "annualised_return", "annualized_return"):
        if key in r:
            return float(r[key])
    raise KeyError(f"No CAGR key found. Available keys: {list(r.keys())}")


def parse_window(raw: str) -> tuple[int, int, str]:
    """
    Parse free-text like '2 months', '45 days', '1 year', '6m', '90d'.
    Returns (months, days, label).
    """
    raw = raw.strip().lower()
    m = re.match(r"^(\d+)\s*(d|day|days|m|mo|month|months|y|yr|year|years)$", raw)
    if not m:
        raise ValueError(f"Could not parse '{raw}'")
    value = int(m.group(1))
    unit  = m.group(2)
    if unit in ("d", "day", "days"):
        return 0, value, f"{value} days"
    elif unit in ("m", "mo", "month", "months"):
        return value, 0, f"{value} months"
    elif unit in ("y", "yr", "year", "years"):
        return value * 12, 0, f"{value} year{'s' if value > 1 else ''}"
    else:
        raise ValueError(f"Unknown unit: {unit}")


def compute_window_end(start: date, months: int, days: int, today: date) -> date:
    if months:
        end = start + relativedelta(months=months)
    else:
        end = start + timedelta(days=days)
    return min(end, today)


def divider(char="-", width=62):
    print(f"\n  {char * width}\n")


# ── Core analysis ─────────────────────────────────────────────────────────────

def run_analysis(months: int, days: int, window_label: str,
                 filename: str, data_dir: Path, investment: float,
                 full_query: bool = False, missed_days: int = 0,
                 start_date: date | None = None):

    RESEARCH_DIR.mkdir(exist_ok=True)
    output_path = RESEARCH_DIR / filename
    today       = date.today()
    since       = start_date or START_DATE

    print(f"\n  Finding all stocks listed after {since}...")
    all_symbols = get_all_symbols(data_dir)

    listings = []
    for sym in all_symbols:
        first_date = get_first_trading_date(sym, data_dir)
        if first_date and first_date > since:
            listings.append((sym, first_date))

    listings.sort(key=lambda x: x[1])
    print(f"  Found {len(listings)} stocks\n")

    if missed_days:
        print(f"  Offset: +{missed_days} days from listing date (missed listing by {missed_days} days)")
    if full_query:
        print(f"  Window: listing date → today\n")
    else:
        print(f"  Window: {window_label} per stock from entry date\n")

    results = []
    skipped = []

    for i, (sym, listing_date) in enumerate(listings, 1):
        print(f"  [{i:>3}/{len(listings)}]  {sym:<16}", end="\r", flush=True)

        # shift start by missed days
        entry_date = listing_date + timedelta(days=missed_days)

        if full_query:
            stock_end = today
        else:
            stock_end = compute_window_end(entry_date, months, days, today)

        if stock_end <= entry_date:
            skipped.append((sym, "entry date is today or in the future"))
            continue

        try:
            r = calculate_cagr(
                symbol=sym,
                start_date=entry_date,
                initial_investment=investment,
                data_dir=data_dir,
                verbose=False,
                end_date=stock_end,
            )

            if r["years"] == 0:
                skipped.append((sym, "no trading data in window"))
                continue

            start_val = r["initial_investment"]
            end_val   = r["todays_value"]
            total_ret = ((end_val / start_val) - 1) * 100 if start_val else 0.0

            # ── fetch actual prices at entry and window end ──
            listing_price = get_price_on_date(sym, entry_date, data_dir)
            end_price     = get_price_on_date(sym, stock_end,  data_dir)

            col_start = "listing_date+10d" if missed_days else "listing_date"
            col_end   = "window_end+10d"   if missed_days else "window_end"

            results.append({
                "#":              None,
                "ticker":         r["symbol"],
                "name":           get_stock_name(r["symbol"]),
                col_start:        entry_date,
                col_end:          stock_end,
                "timeframe":      "to today" if full_query else window_label,
                "listing_price":  round(listing_price, 2) if listing_price is not None else "N/A",
                "end_price":      round(end_price,     2) if end_price     is not None else "N/A",
                "total_return_%": round(total_ret, 2),
            })

        except ZeroDivisionError:
            skipped.append((sym, "no price data in window"))
        except Exception as e:
            skipped.append((sym, str(e)))

    print(" " * 60, end="\r")

    if not results:
        print("  No results calculated.")
        return

    df_out = pd.DataFrame(results)
    date_col = [c for c in df_out.columns if "listing_date" in c or "date" in c][0]
    df_out.sort_values(date_col, ascending=True, inplace=True)
    df_out.reset_index(drop=True, inplace=True)
    df_out["#"] = df_out.index + 1

    cols = ["#"] + [c for c in df_out.columns if c != "#"]
    df_out = df_out[cols]

    df_out.to_csv(output_path, index=False, float_format="%.2f")

    # terminal table
    date_col2 = [c for c in df_out.columns if "listing_date" in c or "date" in c][0]
    end_col   = [c for c in df_out.columns if "window_end" in c][0]
    divider("=")
    print(f"  {'#':<4} {'Ticker':<10} {'Name':<24} {date_col2:<18} {end_col:<18} {'List Px':>9} {'End Px':>9} {'Total Ret':>10}")
    print(f"  {'-'*100}")
    for _, row in df_out.iterrows():
        arrow  = "^" if row["total_return_%"] >= 0 else "v"
        name_t = str(row["name"])[:22]
        lp     = f"{row['listing_price']:>9.2f}" if row["listing_price"] != "N/A" else f"{'N/A':>9}"
        ep     = f"{row['end_price']:>9.2f}"     if row["end_price"]     != "N/A" else f"{'N/A':>9}"
        print(f"  {int(row['#']):<4} {row['ticker']:<10} {name_t:<24} "
              f"{str(row[date_col2]):<18} {str(row[end_col]):<18} "
              f"{lp} {ep} {arrow} {row['total_return_%']:>8.2f}%")
    divider("=")
    missed_note = f"  (+{missed_days} days offset from listing)" if missed_days else ""
    print(f"  {len(results)} stocks  |  window: {'listing to today' if full_query else window_label}{missed_note}")

    if skipped:
        print(f"\n  Skipped {len(skipped)} stocks:")
        for sym, err in skipped:
            print(f"    {sym:<16}  {err}")

    print(f"\n  Saved to: {output_path.resolve()}\n")


# ── Main interactive flow ─────────────────────────────────────────────────────

def prompt_yn(question: str) -> bool:
    while True:
        raw = input(f"  {question} [y/N]: ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no", ""):
            return False
        print("  Enter y or n")


def main():
    while True:
        _run_once()
        again = input("  Run another query? [y/N]: ").strip().lower()
        if again != "y":
            break


def _run_once():
    today    = date.today()
    data_dir = DEFAULT_DATA_DIR

    divider("=")
    print("  NEPSE New Listings -- Interactive Tool")
    print(f"  Base date : {START_DATE}  |  Today: {today}")
    print(f"  Output    : Research/")
    divider("=")

    # Step 1: save full or custom window
    print("\n  What would you like to do?")
    print("  [1] Save full query to CSV  (listing date → today for each stock)")
    print("  [2] Enter a custom time window")
    print("  [3] All data — from earliest listing in dataset")
    print("  [4] Look up listing date for a specific stock")

    while True:
        raw = input("\n  Enter number: ").strip()
        if raw in ("1", "2", "3", "4"):
            choice = int(raw)
            break
        print("  Invalid -- enter 1, 2, 3 or 4")

    # Step 2: missed listing date? (not applicable for option 4)
    if choice != 4:
        divider()
        missed = prompt_yn(f"Did you miss the listing date by {MISS_DAYS} days? (shifts entry & window end by +{MISS_DAYS} days)")
        missed_days = MISS_DAYS if missed else 0
    else:
        missed_days = 0

    # For option 3: find the earliest listing date across all symbols
    if choice == 3:
        all_symbols  = get_all_symbols(data_dir)
        all_dates    = [get_first_trading_date(s, data_dir) for s in all_symbols]
        earliest     = min(d for d in all_dates if d is not None)
        # Use a day before earliest so that stock is included (filter is first_date > since)
        since        = earliest - timedelta(days=1)
        print(f"\n  Earliest listing found: {earliest}  — using all data from that date")

    if choice == 1:
        filename = input("\n  Output filename [new_listings_full.csv]: ").strip() or "new_listings_full.csv"
        run_analysis(0, 0, "to today", filename, data_dir, DEFAULT_INVESTMENT,
                     full_query=True, missed_days=missed_days)

    elif choice == 2:
        divider()
        print("  Enter a time window per stock (measured from listing date).\n")
        print("  Examples:  2 months   45 days   1 year   6m   90d   3 years\n")

        while True:
            raw = input("  Time window: ").strip()
            try:
                months, days, window_label = parse_window(raw)
                break
            except ValueError:
                print(f"  Could not parse '{raw}' — try e.g. '3 months' or '90 days'")

        suffix       = "_missed10d" if missed_days else ""
        default_name = f"listings_{window_label.replace(' ', '_')}{suffix}.csv"
        filename     = input(f"\n  Output filename [{default_name}]: ").strip() or default_name

        run_analysis(months, days, window_label, filename, data_dir, DEFAULT_INVESTMENT,
                     missed_days=missed_days)

    if choice == 4:
        divider()
        while True:
            raw = input("  Enter stock symbol (e.g. NABIL): ").strip().upper()
            if raw:
                break
            print("  Symbol cannot be empty.")

        first_date = get_first_trading_date(raw, data_dir)
        divider()
        if first_date is None:
            print(f"  ❌  No price data found for {raw}.")
            print(f"      Check the symbol or run the scraper to fetch data.")
        else:
            name          = get_stock_name(raw)
            listing_price = get_price_on_date(raw, first_date, data_dir)
            days_since    = (today - first_date).days
            years_since   = days_since / 365.25

            print(f"  Symbol       : {raw}")
            print(f"  Name         : {name}")
            print(f"  Listing date : {first_date}")
            print(f"  Listing price: Rs. {listing_price:,.2f}" if listing_price else "  Listing price: N/A")
            print(f"  Days listed  : {days_since:,} days  ({years_since:.2f} years)")

            # offer to look up more symbols without re-running the full menu
            while True:
                another = input("\n  Look up another symbol? [y/N]: ").strip().lower()
                if another != "y":
                    break
                raw2 = input("  Symbol: ").strip().upper()
                if not raw2:
                    continue
                fd2  = get_first_trading_date(raw2, data_dir)
                divider()
                if fd2 is None:
                    print(f"  ❌  No price data found for {raw2}.")
                else:
                    name2  = get_stock_name(raw2)
                    lp2    = get_price_on_date(raw2, fd2, data_dir)
                    days2  = (today - fd2).days
                    yrs2   = days2 / 365.25
                    print(f"  Symbol       : {raw2}")
                    print(f"  Name         : {name2}")
                    print(f"  Listing date : {fd2}")
                    print(f"  Listing price: Rs. {lp2:,.2f}" if lp2 else "  Listing price: N/A")
                    print(f"  Days listed  : {days2:,} days  ({yrs2:.2f} years)")
        return

    else:  # choice == 3
        divider()
        print("  Enter a time window per stock (measured from listing date).\n")
        print("  Examples:  2 months   45 days   1 year   6m   90d   3 years\n")
        print("  Or press Enter to use listing date → today for each stock.\n")

        raw = input("  Time window (or Enter for full): ").strip()
        if not raw:
            filename = input("\n  Output filename [all_listings_full.csv]: ").strip() or "all_listings_full.csv"
            run_analysis(0, 0, "to today", filename, data_dir, DEFAULT_INVESTMENT,
                         full_query=True, missed_days=missed_days, start_date=since)
        else:
            while True:
                try:
                    months, days, window_label = parse_window(raw)
                    break
                except ValueError:
                    print(f"  Could not parse '{raw}' — try e.g. '3 months' or '90 days'")
                    raw = input("  Time window: ").strip()

            suffix       = "_missed10d" if missed_days else ""
            default_name = f"all_listings_{window_label.replace(' ', '_')}{suffix}.csv"
            filename     = input(f"\n  Output filename [{default_name}]: ").strip() or default_name

            run_analysis(months, days, window_label, filename, data_dir, DEFAULT_INVESTMENT,
                         missed_days=missed_days, start_date=since)

if __name__ == "__main__":
    main()

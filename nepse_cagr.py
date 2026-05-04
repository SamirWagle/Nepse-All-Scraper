"""
NEPSE Stock CAGR Calculator
============================
Uses data from: https://github.com/SamirWagle/Nepse-All-Scraper

Expected folder structure (relative to this script or set via DATA_DIR):
    data/company-wise/{SYMBOL}/prices.csv
    data/company-wise/{SYMBOL}/dividend.csv
    data/company-wise/{SYMBOL}/right-share.csv   (optional)

prices.csv columns    : date, open, high, low, ltp, percent_change, qty, turnover
dividend.csv columns  : fiscal_year, bonus_share, cash_dividend, total_dividend, book_closure_date
right-share.csv cols  : ratio, total_units, issue_price, opening_date, closing_date, status, issue_manager

Usage examples
--------------
    python nepse_cagr.py --symbol NABIL --years 5
    python nepse_cagr.py --symbol NABIL --start-date 2018-01-15
    python nepse_cagr.py --symbol NABIL --start-date 2018-01-15 --investment 200000
    python nepse_cagr.py --symbol NABIL --years 3 --data-dir /path/to/Nepse-All-Scraper
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd


# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
FACE_VALUE = 100          # Rs. face value for most NEPSE stocks
DEFAULT_INVESTMENT = 100_000  # Rs.
DEFAULT_DATA_DIR = Path(__file__).parent / "data"  # override with --data-dir


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def load_prices(symbol: str, data_dir: Path) -> pd.DataFrame:
    path = data_dir / "company-wise" / symbol.upper() / "prices.csv"
    if not path.exists():
        sys.exit(f"❌  prices.csv not found for {symbol} at:\n    {path}")
    df = pd.read_csv(path, parse_dates=["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    if "ltp" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"ltp": "close"})
    return df


def load_dividends(symbol: str, data_dir: Path) -> pd.DataFrame:
    path = data_dir / "company-wise" / symbol.upper() / "dividend.csv"
    if not path.exists():
        print(f"  ⚠️  No dividend.csv found for {symbol} — proceeding with no dividends/bonus shares.")
        return pd.DataFrame(columns=["fiscal_year", "bonus_share", "cash_dividend", "total_dividend", "book_closure_date"])
    df = pd.read_csv(path)
    df["book_closure_date"] = df["book_closure_date"].astype(str).str.extract(r"(\d{4}-\d{2}-\d{2})", expand=False)
    df["book_closure_date"] = pd.to_datetime(df["book_closure_date"], format="%Y-%m-%d", errors="coerce")
    df.sort_values("book_closure_date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    for col in ["bonus_share", "cash_dividend", "total_dividend"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
                .replace("", "0")
                .replace("nan", "0")
                .astype(float)
                / 100.0
            )
    return df


def load_right_shares(symbol: str, data_dir: Path) -> pd.DataFrame:
    """
    Load right-share.csv for the given symbol.
    Columns: ratio, total_units, issue_price, opening_date, closing_date, status, issue_manager

    ratio is like "7:1" meaning for every 7 shares held, investor gets 1 right share.
    We use closing_date as the action date (when the right issue closes / you receive shares).
    """
    path = data_dir / "company-wise" / symbol.upper() / "right-share.csv"
    if not path.exists():
        return pd.DataFrame(columns=["ratio", "total_units", "issue_price", "opening_date", "closing_date", "status", "issue_manager"])

    df = pd.read_csv(path)

    # Parse closing_date (use as the action date)
    df["closing_date"] = pd.to_datetime(df["closing_date"], format="%Y-%m-%d", errors="coerce")

    # Parse ratio "7:1" → ratio_n=7, ratio_d=1 → multiplier = 1/7
    def parse_ratio(r):
        try:
            parts = str(r).split(":")
            n = float(parts[0])  # existing shares needed
            d = float(parts[1])  # new shares received
            return d / n         # fraction of current units to add
        except Exception:
            return 0.0

    df["ratio_multiplier"] = df["ratio"].apply(parse_ratio)

    # Clean issue_price
    df["issue_price"] = (
        df["issue_price"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("nan", "0")
        .astype(float)
    )

    df.sort_values("closing_date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def nearest_price(prices: pd.DataFrame, target_date: date, direction: str = "forward") -> pd.Series:
    prices_dates = prices["date"].dt.date
    if direction == "forward":
        mask = prices_dates >= target_date
        subset = prices[mask]
        if subset.empty:
            subset = prices
        return subset.iloc[0]
    else:
        mask = prices_dates <= target_date
        subset = prices[mask]
        if subset.empty:
            subset = prices
        return subset.iloc[-1]


# ─────────────────────────────────────────────
# Core CAGR calculation
# ─────────────────────────────────────────────

def calculate_cagr(
    symbol: str,
    start_date: date,
    initial_investment: float,
    data_dir: Path,
    verbose: bool = True,
) -> dict:
    today = date.today()
    if start_date >= today:
        sys.exit("❌  Start date must be before today.")

    prices    = load_prices(symbol, data_dir)
    dividends = load_dividends(symbol, data_dir)
    rights    = load_right_shares(symbol, data_dir)

    # ── Step 1: Initial purchase ──────────────────────────────────────────
    start_row = nearest_price(prices, start_date, direction="forward")
    actual_start_date = start_row["date"].date()
    start_price = float(start_row["close"])
    units = initial_investment / start_price

    first_available = prices["date"].dt.date.min()
    if start_date < first_available:
        print(f"\n  ⚠️  WARNING: Requested start date {start_date} is before this stock's")
        print(f"  earliest available data ({first_available}).")
        print(f"  Calculation will start from {first_available} instead.\n")

    if verbose:
        print(f"\n{'='*60}")
        print(f"  NEPSE CAGR Calculator  |  {symbol.upper()}")
        print(f"{'='*60}")
        print(f"  Requested start date : {start_date}")
        if start_date < first_available:
            print(f"  ⚠️  Adjusted to       : {actual_start_date}  (earliest available data)")
        else:
            print(f"  Actual start date    : {actual_start_date}  (nearest trading day)")
        print(f"  Price on start date  : Rs. {start_price:,.2f}")
        print(f"  Initial investment   : Rs. {initial_investment:,.2f}")
        print(f"  Units purchased      : {units:.4f} kitta")
        print(f"\n  {'Date':<14} {'Event':<35} {'Units After':>12} {'Cash Rs.':>12}")
        print(f"  {'-'*75}")
        print(f"  {str(actual_start_date):<14} {'Initial purchase':<35} {units:>12.4f} {'':>12}")

    # ── Step 2: Build a unified timeline of all corporate actions ─────────
    # Each action: (date, type, row)
    actions = []

    for _, row in dividends.iterrows():
        action_date = row["book_closure_date"]
        if pd.isna(action_date):
            continue
        action_date = action_date.date()
        if action_date <= actual_start_date or action_date > today:
            continue
        actions.append((action_date, "dividend", row))

    for _, row in rights.iterrows():
        action_date = row["closing_date"]
        if pd.isna(action_date):
            continue
        action_date = action_date.date()
        if action_date <= actual_start_date or action_date > today:
            continue
        actions.append((action_date, "right", row))

    # Sort all actions by date
    actions.sort(key=lambda x: x[0])

    # ── Step 3: Process all corporate actions chronologically ────────────
    total_cash_dividends  = 0.0
    total_right_share_cost = 0.0

    for action_date, action_type, row in actions:

        if action_type == "right":
            multiplier  = float(row["ratio_multiplier"])
            issue_price = float(row["issue_price"])
            ratio_str   = str(row["ratio"])

            new_units   = units * multiplier
            cost        = new_units * issue_price
            units       += new_units
            total_right_share_cost += cost

            event_label = f"Right share ({ratio_str})  @ Rs.{issue_price:.0f}"
            if verbose:
                print(f"  {str(action_date):<14} {event_label:<35} {units:>12.4f} {cost:>12,.2f}")

        elif action_type == "dividend":
            bonus_pct = float(row.get("bonus_share", 0) or 0)
            cash_pct  = float(row.get("cash_dividend", 0) or 0)
            fiscal_yr = str(row.get("fiscal_year", ""))

            # Cash dividend is calculated on CURRENT units (before bonus is applied).
            # This matches SS Pro behaviour: the dividend is declared on existing holdings,
            # and the bonus shares are new units you receive separately.
            if cash_pct > 0:
                cash_rs = units * FACE_VALUE * cash_pct
                total_cash_dividends += cash_rs
                event_label = f"Cash div {cash_pct*100:.4f}%  [{fiscal_yr}]"
                if verbose:
                    print(f"  {str(action_date):<14} {event_label:<35} {units:>12.4f} {cash_rs:>12,.2f}")

            if bonus_pct > 0:
                new_units = units * bonus_pct
                units += new_units
                event_label = f"Bonus {bonus_pct*100:.2f}%  [{fiscal_yr}]"
                if verbose:
                    print(f"  {str(action_date):<14} {event_label:<35} {units:>12.4f} {'':>12}")

    # ── Step 4: Current value ─────────────────────────────────────────────
    latest_row  = nearest_price(prices, today, direction="backward")
    latest_date = latest_row["date"].date()
    ltp         = float(latest_row["close"])

    market_value   = units * ltp
    total_invested = initial_investment + total_right_share_cost
    todays_value   = market_value + total_cash_dividends

    years = (latest_date - actual_start_date).days / 365.25
    cagr  = (todays_value / total_invested) ** (1 / years) - 1

    if verbose:
        print(f"\n  {'─'*75}")
        print(f"  Latest price date       : {latest_date}  (LTP: Rs. {ltp:,.2f})")
        print(f"  Total units today       : {units:.4f} kitta")
        print(f"  Market value            : Rs. {market_value:,.2f}  ({units:.4f} × {ltp:,.2f})")
        print(f"  Total cash dividends    : Rs. {total_cash_dividends:,.2f}")
        print(f"  Total right share cost  : Rs. {total_right_share_cost:,.2f}")
        print(f"  Today's Value           : Rs. {todays_value:,.2f}")
        print(f"\n  ── CAGR Calculation ───────────────────────────────────────")
        print(f"  Formula : (Today's Value / Total Invested)^(1/years) - 1")
        print(f"  Total invested          : Rs. {total_invested:,.2f}  (initial + right share cost)")
        print(f"          : ({todays_value:,.2f} / {total_invested:,.2f})^(1/{years:.4f}) - 1")
        print(f"\n  Years   : {years:.4f}")
        print(f"  CAGR    : {cagr*100:.2f}%")
        print(f"{'='*60}\n")

    return {
        "symbol": symbol.upper(),
        "start_date": actual_start_date,
        "end_date": latest_date,
        "years": round(years, 4),
        "initial_investment": initial_investment,
        "total_right_share_cost": round(total_right_share_cost, 2),
        "total_invested": round(total_invested, 2),
        "start_price": start_price,
        "units_bought": round(initial_investment / start_price, 4),
        "total_units_today": round(units, 4),
        "ltp": ltp,
        "market_value": round(market_value, 2),
        "total_cash_dividends": round(total_cash_dividends, 2),
        "todays_value": round(todays_value, 2),
        "cagr_pct": round(cagr * 100, 2),
    }


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Calculate CAGR of a NEPSE stock using Nepse-All-Scraper data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--symbol", required=False, default=None, help="Stock symbol, e.g. NABIL")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format. Overrides --years.")
    parser.add_argument("--years", type=float, help="Number of years back from today (e.g. 5 or 2.5).")
    parser.add_argument("--investment", type=float, default=DEFAULT_INVESTMENT,
                        help=f"Initial investment in Rs. (default: {DEFAULT_INVESTMENT:,})")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help=f"Root of Nepse-All-Scraper repo (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--quiet", action="store_true", help="Print only the CAGR result.")

    args = parser.parse_args()

    # ── Interactive mode if no arguments given ──────────────────────────
    if not args.symbol:
        print("\n  NEPSE CAGR Calculator — Interactive Mode")
        print("  " + "─" * 40)
        args.symbol = input("  Stock symbol (e.g. NABIL): ").strip().upper()

    if not args.start_date and not args.years:
        print("\n  How do you want to set the start date?")
        print("  [1] Number of years back (e.g. 5)")
        print("  [2] Specific start date (e.g. 2018-01-15)")
        choice = input("  Enter 1 or 2: ").strip()
        if choice == "1":
            args.years = float(input("  Number of years: ").strip())
        elif choice == "2":
            args.start_date = input("  Start date (YYYY-MM-DD): ").strip()
        else:
            sys.exit("❌  Invalid choice.")

    inv_input = input(f"\n  Initial investment in Rs. (press Enter for default {DEFAULT_INVESTMENT:,}): ").strip()
    if inv_input:
        args.investment = float(inv_input)

    # Resolve start date
    if args.start_date:
        try:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        except ValueError:
            sys.exit("❌  --start-date must be in YYYY-MM-DD format.")
    elif args.years:
        start_date = date.today() - timedelta(days=int(args.years * 365.25))
    else:
        sys.exit("❌  Provide either --start-date or --years.")

    result = calculate_cagr(
        symbol=args.symbol,
        start_date=start_date,
        initial_investment=args.investment,
        data_dir=args.data_dir,
        verbose=not args.quiet,
    )

    if args.quiet:
        print(f"{result['symbol']}  |  CAGR: {result['cagr_pct']:.2f}%  "
              f"({result['start_date']} → {result['end_date']}, {result['years']:.2f} yrs)")


# ─────────────────────────────────────────────
# Importable API
# ─────────────────────────────────────────────

def get_cagr(
    symbol: str,
    years: float = None,
    start_date: date = None,
    investment: float = DEFAULT_INVESTMENT,
    data_dir: Path = DEFAULT_DATA_DIR,
    verbose: bool = True,
) -> dict:
    """
    Importable function. Returns a dict with full breakdown + cagr_pct.

    Example:
        from nepse_cagr import get_cagr
        result = get_cagr("NABIL", years=5)
        print(result["cagr_pct"])
    """
    if start_date is None and years is None:
        raise ValueError("Provide either start_date or years.")
    if start_date is None:
        start_date = date.today() - timedelta(days=int(years * 365.25))
    return calculate_cagr(symbol, start_date, investment, data_dir, verbose)


if __name__ == "__main__":
    main()

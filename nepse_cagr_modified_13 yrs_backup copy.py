"""
NEPSE Stock CAGR Calculator
============================
Uses data from: https://github.com/SamirWagle/Nepse-All-Scraper

Expected folder structure (relative to this script or set via DATA_DIR):
    data/company-wise/{SYMBOL}/prices.csv
    data/company-wise/{SYMBOL}/dividend.csv
    data/company-wise/{SYMBOL}/right-share.csv   (optional)

Usage examples
--------------
    python nepse_cagr_modified.py --mode single --symbol NABIL --years 5
    python nepse_cagr_modified.py --mode multiple --symbol NABIL,NICA,ADBL --years 13
    python nepse_cagr_modified.py --mode all --years 13
    python nepse_cagr_modified.py --mode all --years 13 --output-csv results.csv
"""

import argparse
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
DAYS_PER_YEAR = 365.25    # accounts for leap years

# Known listing dates (overrides earliest data in CSV if earlier)
LISTING_DATES = {
    "SPIL": date(2023, 4, 3),
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def get_all_symbols(data_dir: Path) -> list:
    company_dir = data_dir / "company-wise"
    if not company_dir.exists():
        sys.exit(f"❌  company-wise directory not found at: {company_dir}")
    return sorted([
        d.name for d in company_dir.iterdir()
        if d.is_dir() and (d / "prices.csv").exists()
    ])


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
    end_date: date = None,
) -> dict:
    """
    Calculate total return and CAGR for a NEPSE stock over a date window.

    Corporate actions applied chronologically:
      - Right shares: new units added, issue price added to total_invested
      - Cash dividend: cumulative units × face_value × pct (not reinvested)
      - Bonus shares: new units added, no cash impact

    Returns dict with keys: symbol, start_date, end_date, years,
      initial_investment, total_right_share_cost, total_invested,
      start_price, units_bought, total_units_today, ltp,
      market_value, total_cash_dividends, todays_value, cagr_pct
    """
    try:
        reference_end = end_date if end_date is not None else date.today()
        if start_date >= reference_end:
            raise ValueError(f"Start date {start_date} must be before end date {reference_end}.")

        prices    = load_prices(symbol, data_dir)
        dividends = load_dividends(symbol, data_dir)
        rights    = load_right_shares(symbol, data_dir)

        # Check if there's a known listing date that's later than earliest data
        known_listing_date = LISTING_DATES.get(symbol.upper())
        first_available = prices["date"].dt.date.min()
        if known_listing_date and known_listing_date > first_available:
            first_available = known_listing_date
            prices = prices[prices["date"].dt.date >= known_listing_date].reset_index(drop=True)

        # ── Step 1: Initial purchase ──────────────────────────────────────────
        start_row = nearest_price(prices, start_date, direction="forward")
        actual_start_date = start_row["date"].date()
        start_price = float(start_row["close"])
        units = initial_investment / start_price

        if start_date < first_available:
            if verbose:
                print(f"\n  ⚠️  WARNING: Requested start date {start_date} is before this stock's")
                print(f"  earliest available data ({first_available}).")
                print(f"  Calculation will start from {first_available} instead.\n")

        if actual_start_date >= reference_end:
            raise ValueError(
                f"No price data for {symbol} before cycle end {reference_end}. "
                f"Earliest available data: {first_available}."
            )

        if verbose:
            print(f"\n{'='*60}")
            print(f"  NEPSE CAGR Calculator  |  {symbol.upper()}")
            print(f"{'='*60}")
            print(f"  Requested start date : {start_date}")
            if start_date < first_available:
                print(f"  ⚠️  Adjusted to       : {actual_start_date}  (earliest available data)")
            else:
                print(f"  Actual start date    : {actual_start_date}  (nearest trading day)")
            print(f"  End date             : {reference_end}{' (today)' if end_date is None else ''}")
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
            if action_date <= actual_start_date or action_date > reference_end:
                continue
            actions.append((action_date, "dividend", row))

        for _, row in rights.iterrows():
            action_date = row["closing_date"]
            if pd.isna(action_date):
                continue
            action_date = action_date.date()
            if action_date <= actual_start_date or action_date > reference_end:
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

        # ── Step 4: End-of-window value ───────────────────────────────────────
        latest_row  = nearest_price(prices, reference_end, direction="backward")
        latest_date = latest_row["date"].date()
        ltp         = float(latest_row["close"])

        market_value   = units * ltp
        total_invested = initial_investment + total_right_share_cost
        todays_value   = market_value + total_cash_dividends

        years = (latest_date - actual_start_date).days / DAYS_PER_YEAR
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
    except Exception as e:
        return {
            "symbol": symbol.upper(),
            "error": str(e)
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
    parser.add_argument("--mode", choices=["single", "multiple", "all"], 
                        help="Analysis mode: single stock, multiple stocks (comma-separated), or all stocks")
    parser.add_argument("--symbol", required=False, default=None, 
                        help="Stock symbol (e.g. NABIL) or comma-separated list for multiple mode")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format. Overrides --years.")
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--years", type=float, help="Number of years back from today (e.g. 5 or 13).")
    parser.add_argument("--investment", type=float, default=DEFAULT_INVESTMENT,
                        help=f"Initial investment in Rs. (default: {DEFAULT_INVESTMENT:,})")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help=f"Root of Nepse-All-Scraper repo (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--quiet", action="store_true", help="Print only the CAGR result.")
    parser.add_argument("--output-csv", help="Save results to CSV file (for multiple/all mode)")
    parser.add_argument("--min-years", type=float, help="Minimum years of data required (excludes stocks with less data)")

    args = parser.parse_args()

    # ── Interactive mode if no arguments given ──────────────────────────
    if not args.mode:
        print("\n  NEPSE CAGR Calculator — Interactive Mode")
        print("  " + "─" * 40)
        print("\n  How many stocks do you want to analyze?")
        print("  [1] Single stock")
        print("  [2] Multiple stocks (comma-separated)")
        print("  [3] All stocks")
        mode_choice = input("  Enter 1, 2, or 3: ").strip()
        
        if mode_choice == "1":
            args.mode = "single"
            args.symbol = input("  Stock symbol (e.g. NABIL): ").strip().upper()
        elif mode_choice == "2":
            args.mode = "multiple"
            symbols_input = input("  Stock symbols (comma-separated, e.g. NABIL,NICA,ADBL): ").strip().upper()
            args.symbol = symbols_input
        elif mode_choice == "3":
            args.mode = "all"
            args.symbol = None
        else:
            sys.exit("❌  Invalid choice.")
    
    elif args.mode == "single" and not args.symbol:
        args.symbol = input("  Stock symbol (e.g. NABIL): ").strip().upper()
    elif args.mode == "multiple" and not args.symbol:
        symbols_input = input("  Stock symbols (comma-separated, e.g. NABIL,NICA,ADBL): ").strip().upper()
        args.symbol = symbols_input

    # Get symbols list based on mode
    if args.mode == "all":
        symbols = get_all_symbols(args.data_dir)
        print(f"\n  Found {len(symbols)} stocks to analyze")
    elif args.mode == "multiple":
        symbols = [s.strip() for s in args.symbol.split(",")]
        print(f"\n  Analyzing {len(symbols)} stocks: {', '.join(symbols)}")
    else:  # single
        symbols = [args.symbol.upper()]

    if not args.start_date and not args.years:
        print("\n  How do you want to set the start date?")
        print("  [1] Number of years back (e.g. 5 or 13)")
        print("  [2] Specific start date (e.g. 2018-01-15)")
        choice = input("  Enter 1 or 2: ").strip()
        if choice == "1":
            args.years = float(input("  Number of years: ").strip())
        elif choice == "2":
            args.start_date = input("  Start date (YYYY-MM-DD): ").strip()
        else:
            sys.exit("❌  Invalid choice.")

    # ── End date prompt (interactive only) ──────────────────────────────
    if not args.end_date and args.mode == "single":
        end_date_input = input("\n  End date in YYYY-MM-DD (press Enter for today): ").strip()
        if end_date_input:
            args.end_date = end_date_input

    if args.mode == "single":
        inv_input = input(f"\n  Initial investment in Rs. (press Enter for default {DEFAULT_INVESTMENT:,}): ").strip()
        if inv_input:
            args.investment = float(inv_input)

    # Minimum years filter for multiple/all mode
    if args.mode in ["multiple", "all"] and args.years and not args.min_years:
        filter_input = input(f"\n  Exclude stocks with less than {args.years} years of data? (y/n, default: y): ").strip().lower()
        if filter_input != 'n':
            args.min_years = args.years

    # Resolve start date
    if args.start_date:
        try:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        except ValueError:
            sys.exit("❌  --start-date must be in YYYY-MM-DD format.")
    elif args.years:
        start_date = date.today() - timedelta(days=int(args.years * DAYS_PER_YEAR))
    else:
        sys.exit("❌  Provide either --start-date or --years.")

    # Resolve end date
    if args.end_date:
        try:
            end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError:
            sys.exit("❌  --end-date must be in YYYY-MM-DD format.")
    else:
        end_date = None

    # ── Process stocks ──────────────────────────────────────────────────
    results = []
    
    for symbol in symbols:
        if args.mode in ["multiple", "all"]:
            verbose_mode = False
        else:
            verbose_mode = not args.quiet
            
        result = calculate_cagr(
            symbol=symbol,
            start_date=start_date,
            initial_investment=args.investment,
            data_dir=args.data_dir,
            verbose=verbose_mode,
            end_date=end_date,
        )
        
        # Check if we should include this result
        if "error" in result:
            if verbose_mode:
                print(f"  ⚠️  Skipping {symbol}: {result['error']}")
            continue
            
        # Filter by minimum years if specified
        if args.min_years and result.get("years", 0) < args.min_years - 0.1:
            if args.mode in ["multiple", "all"]:
                print(f"  ⚠️  Skipping {symbol}: only {result['years']:.2f} years of data (minimum: {args.min_years})")
            continue
            
        results.append(result)
        
        # Print summary for multiple/all mode
        if args.mode in ["multiple", "all"]:
            print(f"  ✓ {result['symbol']:<8} | CAGR: {result['cagr_pct']:>7.2f}% | Years: {result['years']:>6.2f} | "
                  f"Start: {result['start_date']} | End: {result['end_date']}")

    # ── Output results ──────────────────────────────────────────────────
    if args.mode in ["multiple", "all"] and results:
        print(f"\n{'='*80}")
        print(f"  Summary: Analyzed {len(results)} stocks")
        print(f"{'='*80}")
        
        # Sort by CAGR
        results_sorted = sorted(results, key=lambda x: x["cagr_pct"], reverse=True)
        
        print(f"\n  Top 10 by CAGR:")
        print(f"  {'Rank':<6} {'Symbol':<10} {'CAGR %':>10} {'Years':>8} {'Total Value':>15} {'Invested':>15}")
        print(f"  {'-'*70}")
        for i, r in enumerate(results_sorted[:10], 1):
            print(f"  {i:<6} {r['symbol']:<10} {r['cagr_pct']:>10.2f}% {r['years']:>8.2f} "
                  f"{r['todays_value']:>15,.0f} {r['total_invested']:>15,.0f}")
        
        # Save to CSV if requested
        args.output_csv = args.output_csv or "Research/results.csv"
        if args.output_csv:
            df = pd.DataFrame(results_sorted)
            df.to_csv(args.output_csv, index=False)
            print(f"\n  ✓ Results saved to: {args.output_csv}")
            
    elif args.mode == "single" and results and args.quiet:
        result = results[0]
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
    end_date: date = None,
) -> dict:
    """
    Importable function. Returns a dict with full breakdown + cagr_pct.

    Example:
        from nepse_cagr_modified import get_cagr
        result = get_cagr("NABIL", years=5)
        print(result["cagr_pct"])

        # With a custom end date:
        result = get_cagr("NABIL", years=5, end_date=date(2023, 1, 1))
    """
    if start_date is None and years is None:
        raise ValueError("Provide either start_date or years.")
    if start_date is None:
        start_date = date.today() - timedelta(days=int(years * DAYS_PER_YEAR))
    return calculate_cagr(symbol, start_date, investment, data_dir, verbose, end_date=end_date)


if __name__ == "__main__":
    main()

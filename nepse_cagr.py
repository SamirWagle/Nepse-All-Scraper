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
    python nepse_cagr.py --symbol NABIL --years 3 --end-date 2023-01-01
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

# Mutual funds and others with Rs. 10 face value
FACE_VALUE_OVERRIDES = {
    "SEF": 10,
    "NIBLSF": 10,
    "NMBSF": 10,
    "LEMF": 10,
}
DEFAULT_INVESTMENT = 100_000  # Rs.
DEFAULT_DATA_DIR = Path(__file__).parent / "data"  # override with --data-dir
DAYS_PER_YEAR = 365.25    # accounts for leap years

def _load_listing_dates(data_dir: Path) -> dict:
    csv_path = data_dir / "ipo_listings.csv"
    result = {}
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            df.columns = df.columns.str.strip().str.lower()
            for _, row in df.iterrows():
                sym = str(row["symbol"]).strip().upper()
                try:
                    result[sym] = date.fromisoformat(str(row["listing_date"]).strip())
                except ValueError:
                    pass
        except Exception:
            pass
    return result

# Listing dates loaded from ipo_listings.csv at startup
LISTING_DATES = _load_listing_dates(DEFAULT_DATA_DIR)


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


def load_index_prices(index_name: str, data_dir: Path) -> pd.DataFrame:
    path = data_dir / "index" / index_name / "history.csv"
    if not path.exists():
        sys.exit(f"❌  history.csv not found for index '{index_name}' at:\n    {path}")
    df = pd.read_csv(path, parse_dates=["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    if "ltp" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"ltp": "close"})
    return df


def resolve_target(symbol: str, data_dir: Path) -> tuple:
    """
    Resolve a user-typed symbol to either a company ticker or a sector index.
    Returns (kind, resolved_name) where kind is "company" or "index".
    """
    company_path = data_dir / "company-wise" / symbol.upper() / "prices.csv"
    if company_path.exists():
        return "company", symbol.upper()

    index_dir = data_dir / "index"
    if index_dir.exists():
        query = symbol.strip().lower().replace(" ", "").replace("_", "")
        candidates = sorted(
            d.name for d in index_dir.iterdir()
            if d.is_dir() and (d / "history.csv").exists()
        )
        for name in candidates:
            if name.lower().replace("_", "") == query:
                return "index", name
        for name in candidates:
            norm = name.lower().replace("_", "")
            if query in norm or norm in query:
                return "index", name

    sys.exit(
        f"❌  No company or sector index found for '{symbol}'.\n"
        f"    Checked: {company_path}\n"
        f"    Checked data/index/ for a sector match (e.g. hydropower, banking, nepse)."
    )


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


def xirr(cashflows: list) -> float:
    """
    Money-weighted rate of return. Solves:
        0 = Sum( CF_i / (1+r)^((date_i - date_0)/365) )
    for r, via bisection.

    cashflows: list of (date, amount) tuples. Negative = money in,
    positive = money out (dividends, final market value).
    """
    t0 = min(d for d, _ in cashflows)

    def npv(rate):
        return sum(
            cf / (1.0 + rate) ** ((d - t0).days / 365.0)
            for d, cf in cashflows
        )

    lo, hi = -0.9999, 10.0
    flo, fhi = npv(lo), npv(hi)
    while flo * fhi > 0 and hi < 1000:
        hi *= 2
        fhi = npv(hi)
    if flo * fhi > 0:
        return float("nan")

    for _ in range(200):
        mid = (lo + hi) / 2
        fmid = npv(mid)
        if abs(fmid) < 1e-6:
            return mid
        if flo * fmid < 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return (lo + hi) / 2


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
    reference_end = end_date if end_date is not None else date.today()
    if start_date >= reference_end:
        raise ValueError(f"Start date {start_date} must be before end date {reference_end}.")

    kind, resolved = resolve_target(symbol, data_dir)
    is_index = kind == "index"

    if is_index:
        prices    = load_index_prices(resolved, data_dir)
        face_value = FACE_VALUE
        dividends = pd.DataFrame(columns=["fiscal_year", "bonus_share", "cash_dividend", "total_dividend", "book_closure_date"])
        rights    = pd.DataFrame(columns=["ratio", "total_units", "issue_price", "opening_date", "closing_date", "status", "issue_manager"])
        known_listing_date = None
        display_symbol = f"{resolved.upper()} INDEX"
    else:
        prices    = load_prices(resolved, data_dir)
        face_value = FACE_VALUE_OVERRIDES.get(resolved, FACE_VALUE)
        dividends = load_dividends(resolved, data_dir)
        rights    = load_right_shares(resolved, data_dir)
        known_listing_date = LISTING_DATES.get(resolved)
        display_symbol = resolved

    # Check if there's a known listing date that's later than earliest data
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
        print(f"\n  ⚠️  WARNING: Requested start date {start_date} is before this stock's")
        print(f"  earliest available data ({first_available}).")
        print(f"  Calculation will start from {first_available} instead.\n")

    if actual_start_date >= reference_end:
        raise ValueError(
            f"No price data for {symbol} before cycle end {reference_end}. "
            f"Earliest available data: {first_available}."
        )

    has_rights = False
    if not rights.empty:
        valid_rights = rights[
            (rights["closing_date"].dt.date > actual_start_date)
            & (rights["closing_date"].dt.date <= reference_end)
        ]
        has_rights = not valid_rights.empty
    method_label = "XIRR" if has_rights else "CAGR"

    # Resolve actual end date/price up front so the header can show it
    latest_row  = nearest_price(prices, reference_end, direction="backward")
    latest_date = latest_row["date"].date()
    ltp         = float(latest_row["close"])

    if verbose:
        print(f"\n{'='*60}")
        print(f"  NEPSE {method_label} Calculator  |  {display_symbol}")
        print(f"{'='*60}")
        print(f"  Requested start date : {start_date}")
        if start_date < first_available:
            print(f"  ⚠️  Adjusted to       : {actual_start_date}  (earliest available data)")
        else:
            print(f"  Actual start date    : {actual_start_date}  (nearest trading day)")
        print(f"  Requested end date   : {reference_end}{' (today)' if end_date is None else ''}")
        if latest_date != reference_end:
            print(f"  Actual end date      : {latest_date}  (nearest trading day)")
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
    cashflows = [(actual_start_date, -initial_investment)]

    for action_date, action_type, row in actions:

        if action_type == "right":
            multiplier  = float(row["ratio_multiplier"])
            issue_price = float(row["issue_price"])
            ratio_str   = str(row["ratio"])

            new_units   = units * multiplier
            cost        = new_units * issue_price
            units       += new_units
            total_right_share_cost += cost
            cashflows.append((action_date, -cost))

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
                cash_rs = units * face_value * cash_pct
                total_cash_dividends += cash_rs
                cashflows.append((action_date, cash_rs))
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
    market_value   = units * ltp
    total_invested = initial_investment + total_right_share_cost
    todays_value   = market_value + total_cash_dividends

    years = (latest_date - actual_start_date).days / DAYS_PER_YEAR
    cagr  = (todays_value / total_invested) ** (1 / years) - 1

    # ── XIRR: money-weighted return, each cashflow discounted from its
    # own date (fixes rights-share cash arriving mid-stream getting
    # treated as if it were invested for the full period). Dividends
    # are NOT reinvested — they're a cash-out on the date paid.
    cashflows.append((latest_date, market_value))
    xirr_rate = xirr(cashflows)

    if verbose:
        print(f"\n  {'─'*75}")
        print(f"  Latest price date       : {latest_date}  (LTP: Rs. {ltp:,.2f})")
        print(f"  Total units today       : {units:.4f} kitta")
        print(f"  Market value            : Rs. {market_value:,.2f}  ({units:.4f} × {ltp:,.2f})")
        print(f"  Total cash dividends    : Rs. {total_cash_dividends:,.2f}")
        print(f"  Total right share cost  : Rs. {total_right_share_cost:,.2f}")

        if has_rights:
            print(f"\n  ── XIRR Calculation ───────────────────────────────────────")
            print(f"  Formula : 0 = Sum( CF_i / (1+r)^((date_i - date_0)/365) )")
            print(f"            CF negative = money in (purchase, right share cost)")
            print(f"            CF positive = money out (cash div at payment date,")
            print(f"                          market value at end date = final CF)")
            print(f"  Years   : {years:.4f}")
            if xirr_rate == xirr_rate:  # not NaN
                print(f"  XIRR    : {xirr_rate*100:.2f}%")
            else:
                print(f"  XIRR    : could not solve (no sign change in cashflow NPV)")
        else:
            print(f"  Today's Value           : Rs. {todays_value:,.2f}")
            print(f"\n  ── CAGR Calculation ───────────────────────────────────────")
            print(f"  Formula : (Today's Value / Total Invested)^(1/years) - 1")
            print(f"  Total invested          : Rs. {total_invested:,.2f}  (initial + right share cost)")
            print(f"          : ({todays_value:,.2f} / {total_invested:,.2f})^(1/{years:.4f}) - 1")
            print(f"\n  Years   : {years:.4f}")
            print(f"  CAGR    : {cagr*100:.2f}%")
        print(f"{'='*60}\n")

    return {
        "symbol": display_symbol,
        "method": method_label,
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
        "xirr_pct": round(xirr_rate * 100, 2) if xirr_rate == xirr_rate else None,
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
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format. Defaults to today.")
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

    # ── End date prompt (interactive only) ──────────────────────────────
    if not args.end_date:
        end_date_input = input("\n  End date in YYYY-MM-DD (press Enter for today): ").strip()
        if end_date_input:
            args.end_date = end_date_input

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

    result = calculate_cagr(
        symbol=args.symbol,
        start_date=start_date,
        initial_investment=args.investment,
        data_dir=args.data_dir,
        verbose=not args.quiet,
        end_date=end_date,
    )

    if args.quiet:
        pct = result['xirr_pct'] if result['method'] == "XIRR" else result['cagr_pct']
        pct_str = f"{pct:.2f}%" if pct is not None else "n/a"
        print(f"{result['symbol']}  |  {result['method']}: {pct_str}  "
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
        from nepse_cagr import get_cagr
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

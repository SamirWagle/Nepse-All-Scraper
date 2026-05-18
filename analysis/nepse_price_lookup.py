"""
Interactively fetch NEPSE closing prices for any symbol and set of dates.
Also supports viewing full or filtered bonus share history.
Reads directly from data/company-wise/SYMBOL/prices.csv and dividend.csv.
If a date is a holiday/non-trading day, rolls forward to the next available trading date.

Usage: python3 nepse_price_lookup.py
"""

import re
import sys
import pandas as pd
from datetime import date, timedelta, datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR      = Path.home() / "CodingProjects" / "Nepse-CAGR" / "data" / "company-wise"
MAX_ROLL_DAYS = 14

DATE_FORMATS = [
    "%B %d %Y",   # October 24 2012
    "%b %d %Y",   # Oct 24 2012
    "%d %B %Y",   # 24 October 2012
    "%d %b %Y",   # 24 Oct 2012
    "%Y-%m-%d",   # 2012-10-24
    "%d-%m-%Y",   # 24-10-2012
    "%d/%m/%Y",   # 24/10/2012
    "%Y/%m/%d",   # 2012/10/24
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def normalise(s: str) -> str:
    """'October 24, 2012' → 'October 24 2012'"""
    return re.sub(r'(\d),\s*(\d{4})', r'\1 \2', s).strip()


def parse_date(s: str) -> date | None:
    s = normalise(s)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_year(s: str) -> int | None:
    """Parse a 4-digit year string."""
    s = s.strip()
    if re.fullmatch(r"\d{4}", s):
        return int(s)
    return None


def prompt(msg: str) -> str:
    """Print a prompt and return stripped input."""
    sys.stdout.write(msg)
    sys.stdout.flush()
    return sys.stdin.readline().strip()


def load_prices(symbol: str) -> pd.DataFrame | None:
    csv = DATA_DIR / symbol / "prices.csv"
    if not csv.exists():
        return None
    df = pd.read_csv(csv, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    return df.set_index("date").sort_index()


def load_dividends(symbol: str) -> pd.DataFrame | None:
    """
    Load dividend.csv for a symbol.
    Cleans bonus_share / cash_dividend columns (strip %, divide by 100).
    Returns None if file not found.
    """
    csv = DATA_DIR / symbol / "dividend.csv"
    if not csv.exists():
        return None
    df = pd.read_csv(csv)

    # Parse book_closure_date robustly
    df["book_closure_date"] = (
        df["book_closure_date"]
        .astype(str)
        .str.extract(r"(\d{4}-\d{2}-\d{2})", expand=False)
    )
    df["book_closure_date"] = pd.to_datetime(
        df["book_closure_date"], format="%Y-%m-%d", errors="coerce"
    )

    # Clean percentage columns
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
            )

    df.sort_values("book_closure_date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def get_price_for_date(df: pd.DataFrame, target: date) -> tuple[date, float] | None:
    """Find price on target date or the next available trading day in the dataset."""
    check = target
    for _ in range(MAX_ROLL_DAYS):
        if check in df.index:
            return check, float(df.loc[check, "ltp"])
        check += timedelta(days=1)
    future = df.index[df.index > target]
    if len(future) > 0:
        next_day = future[0]
        return next_day, float(df.loc[next_day, "ltp"])
    return None


def read_dates_block() -> list[date]:
    """
    Read dates one per line until blank line or EOF.
    """
    sys.stdout.write(
        "\nPaste or type dates (one per line). "
        "Press Enter on a blank line when done.\n"
        "Formats: 2012-10-24  |  24/10/2012  |  October 24, 2012  |  Oct 24 2012\n\n"
    )
    sys.stdout.flush()

    raw_lines = []
    while True:
        sys.stdout.write("  > ")
        sys.stdout.flush()
        line = sys.stdin.readline()
        stripped = line.rstrip("\n").strip()
        if stripped == "":
            if raw_lines:
                break
            continue
        raw_lines.append(stripped)

    target_dates = []
    for raw in raw_lines:
        for part in re.split(r";", raw):
            part = part.strip()
            if not part:
                continue
            parsed = parse_date(part)
            if parsed is None:
                print(f"  ⚠  Couldn't parse '{part}' — skipped.")
            else:
                target_dates.append(parsed)

    return target_dates


# ── Bonus Share History ───────────────────────────────────────────────────────

def show_bonus_history(symbol: str, df_div: pd.DataFrame, from_year: int | None, to_year: int | None):
    """
    Display a formatted bonus share history table.
    Filters to rows with bonus_share > 0, then optionally filters by year range.
    """
    bonus_rows = df_div[df_div["bonus_share"] > 0].copy()

    if bonus_rows.empty:
        print(f"\n  No bonus shares found for {symbol}.\n")
        return

    # Extract calendar year from book_closure_date for filtering
    bonus_rows["_year"] = bonus_rows["book_closure_date"].dt.year

    if from_year is not None:
        bonus_rows = bonus_rows[bonus_rows["_year"] >= from_year]
    if to_year is not None:
        bonus_rows = bonus_rows[bonus_rows["_year"] <= to_year]

    if bonus_rows.empty:
        period = _period_label(from_year, to_year)
        print(f"\n  No bonus shares found for {symbol}{period}.\n")
        return

    period = _period_label(from_year, to_year)
    print(f"\n{'='*65}")
    print(f"  Bonus Share History  |  {symbol}{period}")
    print(f"{'='*65}")
    print(f"  {'Fiscal Year':<18}  {'Book Closure':<14}  {'Bonus %':>10}  {'Cash Div %':>12}")
    print(f"  {'─'*59}")

    total_bonus = 0.0
    for _, row in bonus_rows.iterrows():
        fiscal_yr   = str(row.get("fiscal_year", "—"))
        bdate       = row["book_closure_date"]
        bdate_str   = bdate.strftime("%Y-%m-%d") if pd.notna(bdate) else "—"
        bonus_pct   = float(row.get("bonus_share", 0) or 0)
        cash_pct    = float(row.get("cash_dividend", 0) or 0)
        total_bonus += bonus_pct
        print(
            f"  {fiscal_yr:<18}  {bdate_str:<14}  {bonus_pct:>9.2f}%  {cash_pct:>11.2f}%"
        )

    print(f"  {'─'*59}")
    print(f"  {'Total bonus accumulated':<33}  {total_bonus:>9.2f}%")

    # Compounded growth factor
    rows_iter = bonus_rows.iterrows()
    multiplier = 1.0
    for _, row in rows_iter:
        bonus_pct = float(row.get("bonus_share", 0) or 0)
        multiplier *= (1 + bonus_pct / 100)
    print(f"  {'Units multiplier (compounded)':<33}  {multiplier:>9.4f}×")
    print(f"  (1 unit on start date → {multiplier:.4f} units today from bonus only)")
    print(f"{'='*65}\n")


def _period_label(from_year: int | None, to_year: int | None) -> str:
    if from_year and to_year:
        return f"  ({from_year} – {to_year})"
    elif from_year:
        return f"  ({from_year} onwards)"
    elif to_year:
        return f"  (up to {to_year})"
    return "  (all time)"


def ask_bonus_period() -> tuple[int | None, int | None]:
    """
    Ask the user whether they want full history or a specific year range.
    Returns (from_year, to_year), either of which may be None.
    """
    print("\n  Bonus share history options:")
    print("  [1] Full history (all years)")
    print("  [2] Specific period (from year / to year)")
    choice = prompt("  Enter 1 or 2: ")

    if choice == "2":
        from_str = prompt("  From year (e.g. 2015, or press Enter to skip): ")
        to_str   = prompt("  To year   (e.g. 2023, or press Enter to skip): ")
        from_year = parse_year(from_str) if from_str else None
        to_year   = parse_year(to_str)   if to_str   else None
        if from_str and from_year is None:
            print(f"  ⚠  Couldn't parse '{from_str}' as a year — ignoring.")
        if to_str and to_year is None:
            print(f"  ⚠  Couldn't parse '{to_str}' as a year — ignoring.")
        return from_year, to_year

    return None, None   # full history


# ── Symbol loader with validation ─────────────────────────────────────────────

def load_symbol() -> tuple[str, pd.DataFrame | None]:
    """Prompt for symbol, load prices, return (symbol, prices_df)."""
    while True:
        symbol = prompt("\nEnter company symbol (e.g. CIT, NLIC): ").upper()
        if not symbol:
            print("  Symbol cannot be empty.")
            continue
        df = load_prices(symbol)
        if df is None:
            print(f"  No data found for '{symbol}'. Check symbol and try again.")
            continue
        print(f"  ✓ {len(df)} trading days  ({df.index.min()} → {df.index.max()})")
        return symbol, df


# ── Main menu ─────────────────────────────────────────────────────────────────

def main():
    print("\n=== NEPSE Price Lookup & Bonus History ===")

    symbol, prices_df = load_symbol()

    while True:
        print(f"\n  What would you like to do for {symbol}?")
        print("  [1] Look up prices for specific dates")
        print("  [2] Bonus share history")
        print("  [3] Change symbol")
        print("  [4] Quit")
        choice = prompt("  Enter choice: ")

        if choice == "1":
            # ── Price lookup ──────────────────────────────────────────────
            target_dates = []
            while not target_dates:
                target_dates = read_dates_block()
                if not target_dates:
                    print("  No valid dates entered — please try again.")

            print(f"\n  {'Requested':<14}  {'Actual':<14}  {'Rolled?':<8}  {'LTP (Rs)':>10}")
            print("  " + "─" * 52)
            for target in target_dates:
                result = get_price_for_date(prices_df, target)
                if result is None:
                    print(f"  {str(target):<14}  {'N/A':<14}  {'—':<8}  {'N/A':>10}")
                else:
                    actual, ltp = result
                    rolled = "YES →" if actual != target else "no"
                    print(f"  {str(target):<14}  {str(actual):<14}  {rolled:<8}  {ltp:>10.2f}")

        elif choice == "2":
            # ── Bonus share history ───────────────────────────────────────
            df_div = load_dividends(symbol)
            if df_div is None:
                print(f"\n  ⚠  No dividend.csv found for {symbol}.")
            else:
                from_year, to_year = ask_bonus_period()
                show_bonus_history(symbol, df_div, from_year, to_year)

        elif choice == "3":
            symbol, prices_df = load_symbol()

        elif choice == "4":
            print("\n  Goodbye!\n")
            break

        else:
            print("  Invalid choice — please enter 1, 2, 3, or 4.")


if __name__ == "__main__":
    main()

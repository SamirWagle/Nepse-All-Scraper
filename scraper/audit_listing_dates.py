"""
audit_listing_dates.py

Cross-checks ipo_listings.csv against the first trading date in each company's
prices.csv. The first row of prices.csv is ground truth: a stock cannot trade
before it lists. If listing_date > first_trade_date, the listing date is wrong.

Output:
  data/listing_date_audit.csv   — full report (symbol, listing_date, first_trade, delta_days, status)
  Prints summary to stdout.

Usage:
  python3 -m scraper.audit_listing_dates
  python3 -m scraper.audit_listing_dates --fix    # rewrite ipo_listings.csv with corrected dates
"""
import argparse
import csv
import sys
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
IPO_FILE = DATA_DIR / "ipo_listings.csv"
COMPANY_DIR = DATA_DIR / "company-wise"
AUDIT_FILE = DATA_DIR / "listing_date_audit.csv"

# A listing_date later than the first observed trade is impossible.
# We treat any positive delta as a CRITICAL error.
# A listing_date earlier than the first trade by a wide margin is suspicious
# but not necessarily wrong (price history may not go back that far).
SUSPICIOUS_GAP_DAYS = 90


def parse_date(s):
    if not s:
        return None
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def load_ipo_listings():
    if not IPO_FILE.exists():
        print(f"ERROR: {IPO_FILE} not found", file=sys.stderr)
        sys.exit(1)
    with open(IPO_FILE, newline="") as f:
        reader = csv.DictReader(f)
        return [(row["symbol"], row["listing_date"]) for row in reader if row.get("symbol")]


def first_trade_date(symbol):
    """Read company-wise/{SYMBOL}/prices.csv and return earliest date or None."""
    prices_path = COMPANY_DIR / symbol / "prices.csv"
    if not prices_path.exists():
        return None
    earliest = None
    try:
        with open(prices_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d = parse_date(row.get("date"))
                if d and (earliest is None or d < earliest):
                    earliest = d
    except Exception as e:
        print(f"  {symbol}: failed to read prices.csv: {e}", file=sys.stderr)
        return None
    return earliest


def classify(listing_date_str, first_trade):
    listing = parse_date(listing_date_str)
    if listing is None:
        return "INVALID_LISTING_DATE", None
    if first_trade is None:
        return "NO_PRICE_HISTORY", None

    delta = (first_trade - listing).days  # positive = first trade after listing (normal)

    if delta < 0:
        # listing_date is AFTER first observed trade → impossible → wrong
        return "WRONG_LISTING_AFTER_TRADE", delta
    if delta > SUSPICIOUS_GAP_DAYS:
        return "SUSPICIOUS_LARGE_GAP", delta
    return "OK", delta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite ipo_listings.csv: for any entry where listing_date > first_trade_date, replace with first_trade_date.",
    )
    args = parser.parse_args()

    entries = load_ipo_listings()
    print(f"Auditing {len(entries)} entries from ipo_listings.csv...")
    print(f"Company-wise directory: {COMPANY_DIR}")
    print()

    rows = []
    counts = {"OK": 0, "WRONG_LISTING_AFTER_TRADE": 0, "SUSPICIOUS_LARGE_GAP": 0,
              "NO_PRICE_HISTORY": 0, "INVALID_LISTING_DATE": 0}
    wrong_entries = []

    for symbol, listing_date_str in entries:
        first_trade = first_trade_date(symbol)
        status, delta = classify(listing_date_str, first_trade)
        counts[status] += 1
        rows.append({
            "symbol": symbol,
            "listing_date": listing_date_str,
            "first_trade_date": first_trade.isoformat() if first_trade else "",
            "delta_days": delta if delta is not None else "",
            "status": status,
        })
        if status == "WRONG_LISTING_AFTER_TRADE":
            wrong_entries.append((symbol, listing_date_str, first_trade.isoformat()))

    # Write audit report
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "listing_date", "first_trade_date", "delta_days", "status"])
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    print("=" * 60)
    print("AUDIT SUMMARY")
    print("=" * 60)
    for k, v in counts.items():
        print(f"  {k:<32} {v}")
    print(f"\nFull report: {AUDIT_FILE}")

    if wrong_entries:
        print(f"\n--- WRONG ENTRIES (listing_date AFTER first trade) ---")
        print(f"{'Symbol':<10} {'Stored':<12} -> {'Should Be (first trade)':<12}")
        for sym, stored, actual in wrong_entries:
            print(f"  {sym:<10} {stored:<12} -> {actual:<12}")

    if args.fix and wrong_entries:
        print(f"\n--fix flag set. Rewriting ipo_listings.csv...")
        # Reload all entries, replace wrong ones
        fixed = {}
        for sym, ld in entries:
            fixed[sym] = ld
        for sym, _, actual in wrong_entries:
            fixed[sym] = actual

        records = [{"symbol": s, "listing_date": d} for s, d in sorted(fixed.items())]
        with open(IPO_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "listing_date"])
            writer.writeheader()
            writer.writerows(records)
        print(f"[OK] Fixed {len(wrong_entries)} entries in {IPO_FILE}")
    elif args.fix:
        print("\nNo entries to fix.")


if __name__ == "__main__":
    main()

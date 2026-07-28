"""
index_history.py
----------------
Scrapes historical NEPSE index / sub-index data from ShareSansar.
Saves to: data/index/{folder_name}/history.csv

Usage:
    python index_history.py
    python index_history.py --index "NEPSE Index"
    python index_history.py --all
    python index_history.py --all --full-scrape
    python index_history.py --debug   # print request/response details
    python index_history.py --query --index "NEPSE Index" --date 2024-01-15
"""

import os
import time
import argparse
import requests
import urllib3
import pandas as pd
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL            = "https://www.sharesansar.com"
INDEX_HISTORY_URL   = f"{BASE_URL}/index-history-data"

ALL_INDICES = [
    "NEPSE Index",
    "Sensitive Index",
    "Sensitive Float Index",
    "Float Index",
    "Banking SubIndex",
    "Development Bank Index",
    "Finance Index",
    "Hotels And Tourism",
    "HydroPower Index",
    "Insurance",
    "Investment",
    "Life Insurance",
    "Manufacturing And Processing",
    "Microfinance Index",
    "Mutual Fund",
    "Non Life Insurance",
    "Others Index",
    "Trading Index",
]

INDEX_FOLDER_NAMES = {
    "NEPSE Index":                  "nepse",
    "Sensitive Index":              "sensitive",
    "Sensitive Float Index":        "sensitive_float",
    "Float Index":                  "float",
    "Banking SubIndex":             "banking",
    "Development Bank Index":       "development_bank",
    "Finance Index":                "finance",
    "Hotels And Tourism":           "hotels_tourism",
    "HydroPower Index":             "hydropower",
    "Insurance":                    "insurance",
    "Investment":                   "investment",
    "Life Insurance":               "life_insurance",
    "Manufacturing And Processing": "manufacturing",
    "Microfinance Index":           "microfinance",
    "Mutual Fund":                  "mutual_fund",
    "Non Life Insurance":           "non_life_insurance",
    "Others Index":                 "others",
    "Trading Index":                "trading",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         BASE_URL,
}

AJAX_HEADERS = {
    "User-Agent":       HEADERS["User-Agent"],
    "X-Requested-With": "XMLHttpRequest",
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "Referer":          INDEX_HISTORY_URL,
}

# Numeric IDs from <select> on the ShareSansar index history page
INDEX_IDS = {
    "NEPSE Index":                  12,
    "Sensitive Index":              16,
    "Sensitive Float Index":        15,
    "Float Index":                   4,
    "Banking SubIndex":              1,
    "Development Bank Index":        2,
    "Finance Index":                 3,
    "Hotels And Tourism":            5,
    "HydroPower Index":              6,
    "Insurance":                     7,
    "Investment":                   18,
    "Life Insurance":                8,
    "Manufacturing And Processing":  9,
    "Microfinance Index":           10,
    "Mutual Fund":                  11,
    "Non Life Insurance":           13,
    "Others Index":                 14,
    "Trading Index":                17,
}

# ---------------------------------------------------------------------------
# Parse & clean
# ---------------------------------------------------------------------------

def clean_dataframe(df):
    rename_map = {
        "published_date": "date",
        "current":        "close",
        "per_change":     "percent_change",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df = df.drop(columns=[c for c in ["index_id", "change_", "DT_Row_Index"] if c in df.columns], errors="ignore")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


# ---------------------------------------------------------------------------
# Core scrape
# ---------------------------------------------------------------------------

def scrape_index(index_name, from_date, to_date, session, delay=1.5, debug=False):
    index_id = INDEX_IDS.get(index_name)
    if index_id is None:
        print(f"[!] No numeric ID for '{index_name}'")
        return pd.DataFrame()

    start = datetime.strptime(from_date, "%Y-%m-%d")
    end   = datetime.strptime(to_date,   "%Y-%m-%d")

    all_rows    = []
    chunk_start = start

    while chunk_start <= end:
        # ShareSansar silently returns 0 rows for date ranges >= 31 days.
        # Keep chunks to 29 days to stay within the server's undocumented limit.
        chunk_end = min(chunk_start + timedelta(days=29), end)

        params = {
            "index_id": index_id,
            "from":     chunk_start.strftime("%Y-%m-%d"),
            "to":       chunk_end.strftime("%Y-%m-%d"),
            "draw":     1,
            "start":    0,
            "length":   50,
        }

        if debug:
            print(f"\n[DEBUG] GET params: {params}")

        try:
            resp = session.get(
                INDEX_HISTORY_URL,
                params=params,
                headers=AJAX_HEADERS,
                timeout=30,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [!] Request failed ({chunk_start.date()} – {chunk_end.date()}): {e}")
            chunk_start = chunk_end + timedelta(days=1)
            time.sleep(delay)
            continue

        if debug:
            print(f"[DEBUG] Response: total={data.get('recordsTotal')} rows={len(data.get('data',[]))}")

        rows = data.get("data", [])
        if rows:
            all_rows.extend(rows)
            print(f"  [+] {len(rows)} rows ({chunk_start.date()} – {chunk_end.date()})")
        else:
            print(f"  [-] no data ({chunk_start.date()} – {chunk_end.date()})")

        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(delay)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df = clean_dataframe(df)
    df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Save / merge
# ---------------------------------------------------------------------------

def save_index_data(df, csv_path):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    if os.path.exists(csv_path):
        try:
            existing = pd.read_csv(csv_path)
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["date"], keep="last")
            df = combined.sort_values("date").reset_index(drop=True)
        except Exception:
            pass
    df.to_csv(csv_path, index=False)
    print(f"  [✓] Saved {len(df)} rows → {csv_path}")


def get_latest_date_in_csv(csv_path):
    if not os.path.exists(csv_path):
        return None
    try:
        existing = pd.read_csv(csv_path)
        if existing.empty or "date" not in existing.columns:
            return None
        return existing["date"].max()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# High-level runners
# ---------------------------------------------------------------------------

def _auto_detect_data_dir():
    """Repo root — the parent of scraper/, always.

    This used to walk upward looking for any directory containing `data`, which
    broke silently when `scraper/data/` appeared on 2026-05-04: the walk matched
    it first, and three months of index scrapes landed in `scraper/data/index/`
    instead of the repo's real `data/index/`. Every scrape succeeded, so nothing
    ever errored — the app just kept reading files frozen at 2026-05-06.

    This file lives in scraper/, so the root is its parent. No search, nothing
    to shadow.
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_single(index_name, from_date, to_date, data_dir, incremental=True, debug=False):
    folder_name = INDEX_FOLDER_NAMES.get(index_name)
    if folder_name is None:
        print(f"[!] Unknown index: '{index_name}'. Valid options:\n  " +
              "\n  ".join(ALL_INDICES))
        return

    csv_path  = os.path.join(data_dir, "data", "index", folder_name, "history.csv")
    today_str = datetime.today().strftime("%Y-%m-%d")
    to_date   = to_date or today_str

    if from_date is None:
        if incremental:
            latest = get_latest_date_in_csv(csv_path)
            if latest:
                from_date = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                print(f"[→] Incremental: starting from {from_date} for '{index_name}'")
            else:
                from_date = "2011-01-01"
                print(f"[→] No existing data. Full scrape from {from_date} for '{index_name}'")
        else:
            from_date = "2011-01-01"

    if from_date > to_date:
        print(f"[✓] '{index_name}' already up to date.")
        return

    session = requests.Session()
    print(f"\n[↓] Scraping '{index_name}' ({from_date} → {to_date})")

    df = scrape_index(index_name, from_date, to_date, session, debug=debug)

    if df.empty:
        print(f"  [-] No data returned for '{index_name}'")
        return

    save_index_data(df, csv_path)


def run_all(from_date, to_date, data_dir, incremental=True, debug=False):
    session   = requests.Session()
    today_str = datetime.today().strftime("%Y-%m-%d")
    _to       = to_date or today_str

    for index_name in ALL_INDICES:
        folder_name = INDEX_FOLDER_NAMES[index_name]
        csv_path    = os.path.join(data_dir, "data", "index", folder_name, "history.csv")

        _from = from_date
        if _from is None and incremental:
            latest = get_latest_date_in_csv(csv_path)
            _from  = (
                (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                if latest else "2011-01-01"
            )
        elif _from is None:
            _from = "2011-01-01"

        if _from > _to:
            print(f"[✓] '{index_name}' already up to date. Skipping.")
            continue

        print(f"\n[↓] Scraping '{index_name}' ({_from} → {_to})")
        df = scrape_index(index_name, _from, _to, session, debug=debug)

        if df.empty:
            print(f"  [-] No data returned for '{index_name}'")
        else:
            save_index_data(df, csv_path)

        time.sleep(2.0)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def query_index(index_name, date_str, data_dir):
    folder_name = INDEX_FOLDER_NAMES.get(index_name)
    if folder_name is None:
        print(f"[!] Unknown index: '{index_name}'. Valid options:\n  " + "\n  ".join(ALL_INDICES))
        return

    csv_path = os.path.join(data_dir, "data", "index", folder_name, "history.csv")
    if not os.path.exists(csv_path):
        print(f"[!] No data found for '{index_name}'.\n    Scrape first: python index_history.py --index \"{index_name}\"")
        return

    df = pd.read_csv(csv_path)
    if df.empty or "date" not in df.columns:
        print(f"[!] CSV empty or malformed: {csv_path}")
        return

    df["date"] = pd.to_datetime(df["date"])
    target = pd.to_datetime(date_str)

    exact = df[df["date"] == target]
    if not exact.empty:
        _print_row(index_name, exact.iloc[0], exact=True)
        return

    before = df[df["date"] < target]
    if before.empty:
        print(f"[!] No data before {date_str} for '{index_name}'.")
        return

    _print_row(index_name, before.iloc[-1], exact=False, requested=date_str)


def _print_row(index_name, row, exact=True, requested=None):
    date_val = row["date"]
    if hasattr(date_val, "strftime"):
        date_val = date_val.strftime("%Y-%m-%d")

    if not exact:
        print(f"  (no trading data on {requested} — nearest prior trading day shown)")

    cols = ["open", "high", "low", "close", "percent_change", "turnover"]
    print(f"\n  Index : {index_name}")
    print(f"  Date  : {date_val}")
    for col in cols:
        if col in row.index:
            print(f"  {col:<15}: {row[col]}")


# ---------------------------------------------------------------------------
# Interactive date prompt helper
# ---------------------------------------------------------------------------

def prompt_for_date():
    """Ask user for a date interactively. Returns date string or None."""
    print("\nWhat would you like to do?")
    print("  1. Query data for a specific date")
    print("  2. Scrape / update latest data")
    choice = input("\nEnter 1 or 2: ").strip()

    if choice == "1":
        while True:
            date_input = input("Enter date (YYYY-MM-DD), or press Enter for today: ").strip()
            if not date_input:
                return datetime.today().strftime("%Y-%m-%d")
            try:
                datetime.strptime(date_input, "%Y-%m-%d")
                return date_input
            except ValueError:
                print("  [!] Invalid format. Please use YYYY-MM-DD (e.g. 2024-01-15)")
    return None  # means scrape mode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape NEPSE index history from ShareSansar.")
    parser.add_argument("--index",      type=str, default=None,
                        help='Index name e.g. "NEPSE Index". Omit for interactive mode.')
    parser.add_argument("--all",        action="store_true", help="Scrape all indices.")
    parser.add_argument("--query",      action="store_true",
                        help="Query mode: look up --index on --date.")
    parser.add_argument("--date",       type=str, default=None, metavar="YYYY-MM-DD",
                        help="Date for --query (defaults to today).")
    parser.add_argument("--from-date",  type=str, default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--to-date",    type=str, default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--full-scrape",action="store_true",
                        help="Ignore existing CSV and scrape from 2011-01-01.")
    parser.add_argument("--data-dir",   type=str, default=None,
                        help="Repo root (auto-detected by default).")
    parser.add_argument("--debug",      action="store_true",
                        help="Print raw HTML and request/response details.")
    args = parser.parse_args()

    data_dir    = args.data_dir or _auto_detect_data_dir()
    incremental = not args.full_scrape

    if args.query:
        if not args.index:
            print("[!] --query requires --index")
            return
        date_str = args.date or datetime.today().strftime("%Y-%m-%d")
        query_index(args.index, date_str, data_dir)
    elif args.all:
        run_all(args.from_date, args.to_date, data_dir, incremental, debug=args.debug)
    elif args.index:
        run_single(args.index, args.from_date, args.to_date, data_dir, incremental, debug=args.debug)
    else:
        # ── Interactive mode ──────────────────────────────────────────────
        print("Available indices:")
        for i, name in enumerate(ALL_INDICES, 1):
            print(f"  {i:2}. {name}")
        choice = input("\nEnter index name or number: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            index_name = ALL_INDICES[idx] if 0 <= idx < len(ALL_INDICES) else None
        else:
            index_name = choice

        if index_name:
            date_input = prompt_for_date()
            if date_input:
                # Query mode
                query_index(index_name, date_input, data_dir)
            else:
                # Scrape mode
                run_single(index_name, args.from_date, args.to_date, data_dir, incremental, debug=args.debug)


if __name__ == "__main__":
    main()

"""
run_github_actions.py
=====================
Daily scraper designed for GitHub Actions.
Scrapes for ALL priority companies (company_list.json):
  1. Dividend history    -> data/company-wise/{SYMBOL}/dividend.csv
  2. Right share history -> data/company-wise/{SYMBOL}/right-share.csv
  3. Floorsheet          -> data/floorsheet_YYYY-MM-DD.csv + .json

Usage (locally or in GitHub Actions):
  python scraper/run_github_actions.py                  # all 3
  python scraper/run_github_actions.py --dividends      # dividends only
  python scraper/run_github_actions.py --right-shares   # right shares only
  python scraper/run_github_actions.py --floorsheet     # floorsheet only
  python scraper/run_github_actions.py --floorsheet --max-pages 5   # test
"""

import sys
import os
import csv
import json
import time
import random
import logging
import argparse
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import date as dt_date

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
COMPANY_WISE = DATA_DIR / "company-wise"
FLOORSHEET_DIR = DATA_DIR / "floorsheet"
COMPANY_LIST = Path(__file__).resolve().parent / "company_list.json"

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("daily")

# ── HTTP session ───────────────────────────────────────────────────────────
BASE_URL = "https://www.sharesansar.com"

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s




# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def load_priority_companies():
    """Return list of symbols from company_list.json."""
    with open(COMPANY_LIST) as f:
        return json.load(f)


def get_csrf_and_company_id(session, symbol):
    """
    Using an existing session, visit the company page to get cookies + CSRF token + company ID.
    Returns (csrf_token, company_id) or (None, None) on failure.
    """
    url = f"{BASE_URL}/company/{symbol.lower()}"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            log.warning(f"[{symbol}] Company page returned {resp.status_code}")
            return None, None
        soup = BeautifulSoup(resp.text, "html.parser")

        csrf_meta = soup.find("meta", {"name": "_token"})
        csrf = csrf_meta["content"] if csrf_meta else ""

        cid_div = soup.find("div", {"id": "companyid"})
        company_id = cid_div.text.strip() if cid_div else ""

        return csrf, company_id
    except Exception as e:
        log.error(f"[{symbol}] Failed to load company page: {e}")
        return None, None


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def read_existing_set(filepath: Path, key_col: str) -> set:
    """Return a set of values from key_col in an existing CSV."""
    if not filepath.exists():
        return set()
    with open(filepath, newline="", encoding="utf-8") as f:
        return {row[key_col] for row in csv.DictReader(f) if row.get(key_col)}


def append_to_csv(filepath: Path, fieldnames: list, rows: list):
    """Append rows to CSV, writing header if file is new."""
    file_exists = filepath.exists() and filepath.stat().st_size > 0
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def overwrite_csv(filepath: Path, fieldnames: list, rows: list):
    """Write/overwrite a CSV with the given rows."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ═══════════════════════════════════════════════════════════════════════════
# 1. DIVIDEND HISTORY
# ═══════════════════════════════════════════════════════════════════════════
DIVIDEND_FIELDS = ["fiscal_year", "bonus_share", "cash_dividend", "total_dividend", "book_closure_date"]

def _make_full_dt_params(company_id):
    """Build full DataTables POST params for ShareSansar AJAX endpoints."""
    return {
        'draw': '1',
        'columns[0][data]': 'published_date',
        'columns[0][name]': '',
        'columns[0][searchable]': 'true',
        'columns[0][orderable]': 'false',
        'columns[0][search][value]': '',
        'columns[0][search][regex]': 'false',
        'columns[1][data]': 'title',
        'columns[1][name]': '',
        'columns[1][searchable]': 'true',
        'columns[1][orderable]': 'false',
        'columns[1][search][value]': '',
        'columns[1][search][regex]': 'false',
        'search[value]': '',
        'search[regex]': 'false',
        'company': str(company_id),
        'start': '0',
        'length': '50',
    }


def _post_ajax(session, url, params, csrf, referer):
    """POST to ShareSansar AJAX, retrying on 202. Returns parsed JSON or None."""
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRF-TOKEN': csrf,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': referer,
    }
    for attempt in range(3):
        resp = session.post(url, data=params, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        log.warning(f"  AJAX returned {resp.status_code} (attempt {attempt+1})")
        if resp.status_code == 202:
            time.sleep(2)
        else:
            break
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 1. DIVIDEND HISTORY
# ═══════════════════════════════════════════════════════════════════════════
DIVIDEND_FIELDS = ["fiscal_year", "bonus_share", "cash_dividend", "total_dividend", "book_closure_date"]


def update_dividends(symbol):
    """Scrape dividend history for the given symbol."""
    session = make_session()

    # Step 1: load company page to establish cookies + get CSRF
    company_url = f"{BASE_URL}/company/{symbol.lower()}"
    page = session.get(company_url, timeout=30)
    if page.status_code != 200:
        log.warning(f"  [{symbol}] Company page failed: {page.status_code}")
        return
    soup = BeautifulSoup(page.text, "html.parser")
    csrf_meta = soup.find("meta", {"name": "_token"})
    if not csrf_meta:
        log.warning(f"  [{symbol}] No CSRF token found")
        return
    csrf = csrf_meta["content"]

    # Look up company_id from mapping
    mapping_path = DATA_DIR / "company_id_mapping.json"
    with open(mapping_path) as f:
        mapping = json.load(f)
    company_id = mapping.get(symbol.upper())
    if not company_id:
        log.warning(f"  [{symbol}] No company ID in mapping")
        return

    # Step 2: POST to dividend endpoint with full DataTables params
    records = []
    start = 0
    while True:
        params = _make_full_dt_params(company_id)
        params['start'] = str(start)
        data = _post_ajax(session, f"{BASE_URL}/company-dividend", params, csrf, company_url)
        if not data:
            break
        batch = data.get("data", [])
        total = int(data.get("recordsFiltered", 0) or data.get("recordsTotal", 0))
        if not batch:
            break
        for row in batch:
            records.append({
                "fiscal_year":       str(row.get("year", "")).strip(),
                "bonus_share":       str(row.get("bonus_share", "0")).strip(),
                "cash_dividend":     str(row.get("cash_dividend", "0")).strip(),
                "total_dividend":    str(row.get("total_dividend", "0")).strip(),
                "book_closure_date": str(row.get("bookclose_date", "")).strip(),
            })
        if start + 50 >= total or len(batch) < 50:
            break
        start += 50
        time.sleep(0.5)

    if not records:
        log.info(f"  [{symbol}] No dividend data")
        return

    out = COMPANY_WISE / symbol / "dividend.csv"
    ensure_dir(out.parent)
    overwrite_csv(out, DIVIDEND_FIELDS, records)
    log.info(f"  [{symbol}] Saved {len(records)} dividend records")


# ═══════════════════════════════════════════════════════════════════════════
# 2. RIGHT SHARE HISTORY
# ═══════════════════════════════════════════════════════════════════════════
RIGHT_SHARE_FIELDS = ["ratio", "total_units", "issue_price", "opening_date", "closing_date", "status", "issue_manager"]


def update_right_shares(symbol):
    """Scrape right share history for the given symbol."""
    session = make_session()

    company_url = f"{BASE_URL}/company/{symbol.lower()}"
    page = session.get(company_url, timeout=30)
    if page.status_code != 200:
        log.warning(f"  [{symbol}] Company page failed: {page.status_code}")
        return
    soup = BeautifulSoup(page.text, "html.parser")
    csrf_meta = soup.find("meta", {"name": "_token"})
    if not csrf_meta:
        log.warning(f"  [{symbol}] No CSRF token found")
        return
    csrf = csrf_meta["content"]

    mapping_path = DATA_DIR / "company_id_mapping.json"
    with open(mapping_path) as f:
        mapping = json.load(f)
    company_id = mapping.get(symbol.upper())
    if not company_id:
        log.warning(f"  [{symbol}] No company ID in mapping")
        return

    records = []
    start = 0
    while True:
        params = _make_full_dt_params(company_id)
        params['start'] = str(start)
        data = _post_ajax(session, f"{BASE_URL}/company-rightshare", params, csrf, company_url)
        if not data:
            break
        batch = data.get("data", [])
        total = int(data.get("recordsFiltered", 0) or data.get("recordsTotal", 0))
        if not batch:
            break
        for row in batch:
            records.append({
                "ratio":         str(row.get("ratio_value", "")).strip(),
                "total_units":   str(row.get("total_units", "0")).strip(),
                "issue_price":   str(row.get("issue_price", "0")).strip(),
                "opening_date":  str(row.get("opening_date", "")).strip(),
                "closing_date":  str(row.get("closing_date", "")).strip(),
                "status":        str(row.get("is_open", "")).strip(),
                "issue_manager": str(row.get("issue_manager", "")).strip(),
            })
        if start + 50 >= total or len(batch) < 50:
            break
        start += 50
        time.sleep(0.5)

    if not records:
        log.info(f"  [{symbol}] No right share data")
        return

    out = COMPANY_WISE / symbol / "right-share.csv"
    ensure_dir(out.parent)
    overwrite_csv(out, RIGHT_SHARE_FIELDS, records)
    log.info(f"  [{symbol}] Saved {len(records)} right share records")

# ═══════════════════════════════════════════════════════════════════════════
# 3. FLOORSHEET
# ═══════════════════════════════════════════════════════════════════════════
FLOORSHEET_FIELDS = ["date", "sn", "contract_no", "stock_symbol", "buyer", "seller", "quantity", "rate", "amount"]
FLOORSHEET_URL = "https://merolagani.com/Floorsheet.aspx"

def _get_floorsheet_hidden(soup):
    return {i["name"]: i.get("value", "") for i in soup.find_all("input", type="hidden") if i.get("name")}


def scrape_floorsheet(max_pages=None):
    """Scrape today's full floorsheet from merolagani. Returns list of records."""
    import re
    today = str(dt_date.today())
    fs_session = make_session()
    fs_session.headers.update({
        "Origin": "https://merolagani.com",
        "Referer": FLOORSHEET_URL,
        "Upgrade-Insecure-Requests": "1",
    })

    log.info("Floorsheet: loading page...")
    resp = fs_session.get(FLOORSHEET_URL, timeout=30)
    if resp.status_code != 200:
        log.error(f"Floorsheet: failed to load page ({resp.status_code})")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    all_records = []
    page_num = 1

    while True:
        log.info(f"Floorsheet: page {page_num}...")
        table = soup.find("table", class_="table-bordered")
        if not table:
            log.warning("Floorsheet: table not found")
            break

        for row in table.find("tbody").find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 8:
                continue
            all_records.append({
                "date":         today,
                "sn":           cols[0].get_text(strip=True),
                "contract_no":  cols[1].get_text(strip=True),
                "stock_symbol": cols[2].get_text(strip=True),
                "buyer":        cols[3].get_text(strip=True),
                "seller":       cols[4].get_text(strip=True),
                "quantity":     cols[5].get_text(strip=True),
                "rate":         cols[6].get_text(strip=True),
                "amount":       cols[7].get_text(strip=True),
            })

        if max_pages and page_num >= max_pages:
            break

        next_btn = soup.find("a", title="Next Page") or soup.find("a", string="Next")
        if not next_btn:
            break

        onclick = next_btn.get("onclick", "")
        m = re.search(r"changePageIndex\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]", onclick)
        if not m:
            break

        next_page_num, hidden_field_id, submit_btn_id = m.group(1), m.group(2), m.group(3)
        hidden_input = soup.find(id=hidden_field_id)
        submit_input = soup.find(id=submit_btn_id)
        if not hidden_input or not submit_input:
            break

        payload = _get_floorsheet_hidden(soup)
        payload[hidden_input["name"]] = next_page_num
        payload[submit_input["name"]] = ""

        time.sleep(random.uniform(1, 2))
        resp = fs_session.post(FLOORSHEET_URL, data=payload, timeout=45)
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        page_num += 1

    log.info(f"Floorsheet: scraped {len(all_records)} records")
    return all_records


def save_floorsheet(records):
    """Save to data/floorsheet/floorsheet_YYYY-MM-DD.csv (overwrites if re-run same day)."""
    if not records:
        return
    today = str(dt_date.today())
    ensure_dir(FLOORSHEET_DIR)

    csv_path = FLOORSHEET_DIR / f"floorsheet_{today}.csv"

    overwrite_csv(csv_path, FLOORSHEET_FIELDS, records)
    log.info(f"Floorsheet: saved -> {csv_path}")


# ═══════════════════════════════════════════════════════════════════════════
# RUNNERS
# ═══════════════════════════════════════════════════════════════════════════

def run_dividends():
    companies = load_priority_companies()
    log.info(f"=== Dividend update for {len(companies)} companies ===")
    for i, sym in enumerate(sorted(companies), 1):
        log.info(f"[{i}/{len(companies)}] {sym}")
        try:
            update_dividends(sym)
        except Exception as e:
            log.error(f"  [{sym}] Error: {e}")
        time.sleep(random.uniform(0.8, 1.5))
    log.info("=== Dividend update complete ===")


def run_right_shares():
    companies = load_priority_companies()
    log.info(f"=== Right share update for {len(companies)} companies ===")
    for i, sym in enumerate(sorted(companies), 1):
        log.info(f"[{i}/{len(companies)}] {sym}")
        try:
            update_right_shares(sym)
        except Exception as e:
            log.error(f"  [{sym}] Error: {e}")
        time.sleep(random.uniform(0.8, 1.5))
    log.info("=== Right share update complete ===")


def run_floorsheet(max_pages=None):
    log.info("=== Floorsheet scrape ===")
    records = scrape_floorsheet(max_pages=max_pages)
    save_floorsheet(records)
    log.info("=== Floorsheet complete ===")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Nepsy GitHub Actions Daily Scraper")
    parser.add_argument("--dividends",    action="store_true", help="Scrape dividend history")
    parser.add_argument("--right-shares", action="store_true", help="Scrape right share history")
    parser.add_argument("--floorsheet",   action="store_true", help="Scrape today's floorsheet")
    parser.add_argument("--max-pages",    type=int, default=None, help="Limit floorsheet pages (for testing)")
    args = parser.parse_args()

    # If no flag given, run all three
    run_all = not (args.dividends or args.right_shares or args.floorsheet)

    if run_all or args.dividends:
        run_dividends()

    if run_all or args.right_shares:
        run_right_shares()

    if run_all or args.floorsheet:
        run_floorsheet(max_pages=args.max_pages)


if __name__ == "__main__":
    main()

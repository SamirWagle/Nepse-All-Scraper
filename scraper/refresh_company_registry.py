#!/usr/bin/env python3
"""
Refresh the company registry from ShareSansar so new listings become searchable.

ShareSansar's /company-list page embeds the full symbol registry as a JS array:

    var cmpjson = [{"id":1362,"symbol":"SOHL","companyname":"Solu Hydropower Limited"}, ...]

That single array carries id + symbol + name, so this replaces both the (never
written) company_id_mapping.json refresh and a per-symbol name scrape.

Merges only — existing entries are never overwritten, so hand-corrected names
and merged/delisted symbols survive.

Run with: python3 scraper/refresh_company_registry.py
"""

import csv
import json
import logging
import re
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MAPPING_PATH = DATA_DIR / "company_id_mapping.json"
NAMES_PATH = DATA_DIR / "company_names.json"
COMPANIES_CSV = DATA_DIR / "companies.csv"

COMPANY_LIST_PATHS = (
    DATA_DIR / "company_list.json",
    Path(__file__).resolve().parent / "company_list.json",
)

LIST_URL = "https://www.sharesansar.com/company-list"
TODAY_PRICE_URL = "https://www.sharesansar.com/today-share-price"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
CMPJSON_RE = re.compile(r"var\s+cmpjson\s*=\s*(\[.*?\])\s*;", re.S)
MIN_EXPECTED_ENTRIES = 1000  # sanity floor: NEPSE registry is ~1600 symbols
MIN_EXPECTED_TRADED = 100    # sanity floor: a normal session trades 300+ symbols


def parse_registry(html: str) -> list[dict]:
    """Extract and validate the cmpjson array from the company-list page."""
    match = CMPJSON_RE.search(html)
    if not match:
        raise ValueError("cmpjson array not found — ShareSansar page layout changed")

    entries = json.loads(match.group(1))
    # ShareSansar's registry carries a few non-ticker rows (association names,
    # "STOCK-BROKER"). Real NEPSE tickers never contain whitespace.
    valid = [
        e for e in entries
        if isinstance(e, dict)
        and str(e.get("symbol", "")).strip()
        and " " not in str(e.get("symbol", "")).strip()
        and isinstance(e.get("id"), int)
    ]
    if len(valid) < MIN_EXPECTED_ENTRIES:
        raise ValueError(
            f"only {len(valid)} usable entries (expected >= {MIN_EXPECTED_ENTRIES}) "
            "— refusing to merge a truncated registry"
        )
    return valid


def fetch_registry() -> list[dict]:
    resp = requests.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_registry(resp.text)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        raise ValueError(f"{path} is not readable JSON: {e}") from e


def find_renames(entries: list[dict], mapping: dict) -> dict:
    """
    Return {old_symbol: new_symbol} for tickers ShareSansar has renamed.

    A rename shows up as: the company id we stored is now published under a
    different symbol, AND our stored symbol is gone from the registry. This is
    how Solu Hydropower slipped through — it sat in the mapping as its
    pre-listing ticker, so searching its live ticker found nothing.
    """
    by_id = {e["id"]: str(e["symbol"]).strip().upper() for e in entries}
    live = set(by_id.values())
    return {
        sym: by_id[cid]
        for sym, cid in mapping.items()
        if sym not in live and by_id.get(cid) and by_id[cid] != sym
    }


def merge_registry(entries: list[dict], mapping: dict, names: dict) -> tuple[dict, dict]:
    """Return new (mapping, names) dicts with missing symbols added, renames applied."""
    new_mapping = dict(mapping)
    new_names = dict(names)

    for entry in entries:
        symbol = str(entry["symbol"]).strip().upper()
        name = str(entry.get("companyname", "")).strip()
        if symbol not in new_mapping:
            new_mapping[symbol] = entry["id"]
        if symbol not in new_names and name:
            new_names[symbol] = f"{name} ( {symbol} )"

    # Drop superseded tickers so a renamed company appears once, under its
    # live symbol. Symbols that still exist in the registry (merged/delisted
    # companies) are untouched — they stay searchable for historical CAGR.
    for old_sym in find_renames(entries, mapping):
        new_mapping.pop(old_sym, None)
        new_names.pop(old_sym, None)

    return new_mapping, new_names


def fetch_traded_symbols() -> set[str]:
    """Every symbol on ShareSansar's latest Today's Share Price table."""
    import pandas as pd
    from io import StringIO

    resp = requests.get(TODAY_PRICE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    if not tables:
        raise ValueError("no price table on today-share-price page")

    df = tables[0]
    if "Symbol" not in df.columns:
        raise ValueError(f"no Symbol column; got {list(df.columns)}")
    return {str(s).strip().upper() for s in df["Symbol"] if str(s).strip()}


def _sync_companies_csv(traded: set[str], dry_run: bool = False) -> list[str]:
    """Append newly traded symbols to companies.csv.

    This file drives the daily fundamentals refresh. It was maintained by hand,
    so 30 traded symbols (SOHL among them) were never picked up — their
    fundamentals, and therefore shareholding and PE, silently never refreshed.
    """
    if not COMPANIES_CSV.exists():
        return []

    with COMPANIES_CSV.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    known = {r["symbol"] for r in rows}
    added = sorted(traded - known)
    if not added or dry_run:
        return added

    names = _load_json(NAMES_PATH)
    for sym in added:
        display = re.sub(r"\s+", " ", names.get(sym, sym)).strip()
        display = re.sub(r"\(\s*[A-Z0-9./%_-]+\s*\)$", "", display).strip() or sym
        rows.append({"symbol": sym, "name": display})

    rows.sort(key=lambda r: r["symbol"])
    with COMPANIES_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["symbol", "name"])
        writer.writeheader()
        writer.writerows(rows)
    logger.info("companies.csv: added %d symbol(s): %s", len(added), ", ".join(added))
    return added


def sync_traded_symbols(dry_run: bool = False) -> list[str]:
    """
    Union today's traded symbols into the scrape lists so a newly listed
    company starts collecting prices the first day it trades.
    """
    traded = fetch_traded_symbols()
    if len(traded) < MIN_EXPECTED_TRADED:
        logger.warning(
            "Only %d traded symbols (market holiday or partial page) — skipping list sync.",
            len(traded),
        )
        return []

    added_all = set()
    for path in COMPANY_LIST_PATHS:
        if not path.exists():
            continue
        current = json.loads(path.read_text())
        merged = sorted(set(current) | traded)
        added = sorted(traded - set(current))
        if added and not dry_run:
            path.write_text(json.dumps(merged, indent=2))
        added_all.update(added)

    _sync_companies_csv(traded, dry_run=dry_run)

    if added_all:
        logger.info("Newly traded symbols added to scrape list: %s", ", ".join(sorted(added_all)))
    else:
        logger.info("No newly traded symbols.")
    return sorted(added_all)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))


def refresh(dry_run: bool = False) -> dict:
    entries = fetch_registry()
    mapping = _load_json(MAPPING_PATH)
    names = _load_json(NAMES_PATH)

    renames = find_renames(entries, mapping)
    new_mapping, new_names = merge_registry(entries, mapping, names)
    added = sorted(set(new_mapping) - set(mapping))

    logger.info(
        "Registry: %d fetched | mapping %d -> %d | names %d -> %d",
        len(entries), len(mapping), len(new_mapping), len(names), len(new_names),
    )
    logger.info("New symbols: %s", ", ".join(added) if added else "none")
    if renames:
        logger.info(
            "Renamed tickers: %s",
            ", ".join(f"{o} -> {n}" for o, n in sorted(renames.items())),
        )

    if not dry_run and (new_mapping != mapping or new_names != names):
        _write_json(MAPPING_PATH, new_mapping)
        _write_json(NAMES_PATH, new_names)
        logger.info("Wrote %s and %s", MAPPING_PATH.name, NAMES_PATH.name)

    traded_added = sync_traded_symbols(dry_run=dry_run)

    return {
        "fetched": len(entries),
        "added": added,
        "renamed": renames,
        "traded_added": traded_added,
    }


def _self_check() -> None:
    html = ('x <script> var cmpjson = ['
            '{"id":1362,"symbol":"SOHL","companyname":"Solu Hydropower Limited"},'
            '{"id":175,"symbol":"ABBL","companyname":"Old Name"}]; </script>')
    entries = json.loads(CMPJSON_RE.search(html).group(1))

    mapping = {"ABBL": 175}
    names = {"ABBL": "Hand Corrected Name"}
    new_mapping, new_names = merge_registry(entries, mapping, names)

    assert new_mapping["SOHL"] == 1362
    assert new_names["SOHL"] == "Solu Hydropower Limited ( SOHL )"
    assert new_names["ABBL"] == "Hand Corrected Name", "must not overwrite existing"
    assert mapping == {"ABBL": 175}, "must not mutate input"

    # The Solu case: stored under an old ticker, republished under a new one.
    stale = {"SHPL": 1362, "ABBL": 175}
    assert find_renames(entries, stale) == {"SHPL": "SOHL"}
    renamed_map, renamed_names = merge_registry(entries, stale, {"SHPL": "Old ( SHPL )"})
    assert "SHPL" not in renamed_map and renamed_map["SOHL"] == 1362
    assert "SHPL" not in renamed_names

    # A symbol still in the registry is never dropped, even if delisted.
    assert find_renames(entries, {"ABBL": 175}) == {}

    try:
        parse_registry(html)
    except ValueError as e:
        assert "truncated" in str(e)
    else:
        raise AssertionError("short registry should be rejected")

    print("self-check OK")


if __name__ == "__main__":
    import sys
    if "--self-check" in sys.argv:
        _self_check()
    else:
        refresh(dry_run="--dry-run" in sys.argv)

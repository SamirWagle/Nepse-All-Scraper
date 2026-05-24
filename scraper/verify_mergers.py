#!/usr/bin/env python3
"""
Verify which merged symbols the merger scraper can currently discover.

This is a local sanity-check tool. It prints:
  - symbols found from Sharesansar sources
  - symbols currently present in data/company_mergers.json
  - symbols found by the scraper but missing from the saved registry

Usage:
  python scraper/verify_mergers.py
  python scraper/verify_mergers.py --max-pages 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.mergers import ShareSansarMergerScraper


REGISTRY_PATH = ROOT / "data" / "company_mergers.json"


def load_registry_symbols() -> set[str]:
    if not REGISTRY_PATH.exists():
        return set()
    try:
        raw = json.loads(REGISTRY_PATH.read_text())
        entries = raw.get("entries", raw) if isinstance(raw, dict) else {}
        return {sym.upper() for sym in entries.keys()}
    except Exception:
        return set()


def load_registry_entries() -> dict[str, dict]:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        raw = json.loads(REGISTRY_PATH.read_text())
        entries = raw.get("entries", raw) if isinstance(raw, dict) else {}
        return {sym.upper(): entry for sym, entry in entries.items() if isinstance(entry, dict)}
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify merged-company scraping coverage.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit paginated article discovery")
    parser.add_argument("--max-companies", type=int, default=None, help="Limit company-page scan count")
    args = parser.parse_args()

    scraper = ShareSansarMergerScraper()
    registry_symbols = load_registry_symbols()
    registry_entries = load_registry_entries()

    records = []
    print("Scanning company pages...")
    target_symbols = sorted(registry_symbols) if registry_symbols else sorted(scraper._symbols)
    if args.max_companies is not None:
        target_symbols = target_symbols[:args.max_companies]
    records.extend(scraper._scrape_merged_company_pages(symbols=target_symbols))
    print("Scanning merged-companies page...")
    records.extend(scraper._scrape_merged_companies_page("https://www.sharesansar.com/merged-companies"))
    print("Scanning merger articles...")
    for url in list(dict.fromkeys(scraper._discover_article_links(max_pages=args.max_pages))):
        try:
            resp = scraper._session.get(url, timeout=30)
            resp.raise_for_status()
            title, body = scraper._extract_title_and_body(resp.text)
            records.extend(scraper._infer_record(title, body, url))
        except Exception:
            continue

    found_symbols = {rec.symbol.upper() for rec in records if rec.status in {"closed", "active_survivor"}}
    missing_from_registry = sorted(found_symbols - registry_symbols)
    extra_in_registry = sorted(registry_symbols - found_symbols)
    from_registry_source = sorted(registry_entries.keys())

    print(f"Found symbols: {len(found_symbols)}")
    for sym in sorted(found_symbols):
        print(sym)

    print()
    print(f"Registry symbols: {len(registry_symbols)}")
    for sym in sorted(registry_symbols):
        print(sym)

    print()
    print(f"Registry entries loaded: {len(from_registry_source)}")
    for sym in from_registry_source:
        print(sym)

    print()
    print(f"Found but missing from registry: {len(missing_from_registry)}")
    for sym in missing_from_registry:
        print(sym)

    print()
    print(f"In registry but not found this run: {len(extra_in_registry)}")
    for sym in extra_in_registry:
        print(sym)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
One-time script: fetches company names from sharesansar.com and saves to
data/company_names.json  ->  { "NABIL": "Nabil Bank Limited", ... }

Run with: python3 fetch_company_names.py
"""

import json
import time
import random
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR  = Path(__file__).parent.parent / "data"
OUT_PATH  = DATA_DIR / "company_names.json"
LIST_PATH = DATA_DIR / "company_list.json"
MAPPING_PATH = DATA_DIR / "company_id_mapping.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_company_name(session: requests.Session, symbol: str) -> str | None:
    """Scrape the company name from sharesansar.com/company/<symbol>."""
    url = f"https://www.sharesansar.com/company/{symbol.lower()}"
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            logger.warning(f"  {symbol:<16} HTTP {resp.status_code}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try <h1> or <title> — sharesansar puts company name in page <h1>
        for selector in [
            "h1.company-title",
            "h1",
            "title",
        ]:
            tag = soup.select_one(selector)
            if tag:
                text = tag.get_text(strip=True)
                # Title format is usually "NABIL - Nabil Bank Limited | ShareSansar"
                if "|" in text:
                    text = text.split("|")[0].strip()
                if "-" in text:
                    # take the part after the dash (full name)
                    parts = text.split("-", 1)
                    if len(parts[1].strip()) > 2:
                        text = parts[1].strip()
                if text and text.upper() != symbol:
                    return text

        logger.warning(f"  {symbol:<16} name not found in page")
        return None

    except Exception as e:
        logger.warning(f"  {symbol:<16} error: {e}")
        return None


def main():
    # Load symbol list, preferring the full mapping so merged/delisted
    # companies are included too.
    if MAPPING_PATH.exists():
        with open(MAPPING_PATH) as f:
            mapping = json.load(f)
        symbols = sorted(mapping.keys())
        logger.info(f"Loaded {len(symbols)} symbols from company_id_mapping.json")
    else:
        with open(LIST_PATH) as f:
            symbols = json.load(f)
        logger.info(f"Loaded {len(symbols)} symbols from company_list.json")

    logger.info(f"Fetching names for {len(symbols)} symbols...")

    # Load existing progress if any
    if OUT_PATH.exists():
        with open(OUT_PATH) as f:
            names = json.load(f)
        logger.info(f"Resuming — {len(names)} already fetched")
    else:
        names = {}

    session = requests.Session()
    session.headers.update(HEADERS)

    todo = [s for s in symbols if s not in names]
    logger.info(f"{len(todo)} remaining to fetch\n")

    for i, symbol in enumerate(todo, 1):
        name = get_company_name(session, symbol)
        names[symbol] = name if name else symbol   # fall back to ticker
        logger.info(f"  [{i:>3}/{len(todo)}]  {symbol:<16}  {names[symbol]}")

        # Save after every 10 to preserve progress
        if i % 10 == 0:
            with open(OUT_PATH, "w") as f:
                json.dump(names, f, indent=2, ensure_ascii=False)

        # Polite delay so sharesansar doesn't block us
        time.sleep(random.uniform(1.0, 2.0))

    # Final save
    with open(OUT_PATH, "w") as f:
        json.dump(names, f, indent=2, ensure_ascii=False)

    found = sum(1 for k, v in names.items() if v != k)
    logger.info(f"\nDone. Saved to {OUT_PATH.resolve()}")
    logger.info(f"Total: {len(names)}  |  Saved to: {OUT_PATH}")


if __name__ == "__main__":
    main()

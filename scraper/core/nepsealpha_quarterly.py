"""NepseAlpha quarterly fundamentals scraper (earnings growth + ROE trend).

Scrapes the 8-quarter table from:
    https://nepsealpha.com/stocks/{SYMBOL}/info
(JS-rendered — needs Firecrawl, costs 1 credit per call)

Cache per symbol at:
    data/company-wise/{SYMBOL}/nepsealpha_quarterly.json

Cache TTL: 24 hours (quarterly data changes rarely; keeps cron incremental).
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

NEPSEALPHA_URL = "https://nepsealpha.com/stocks"
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"
CACHE_TTL_HOURS = 24

_ROW_LABELS = {
    "roe_ttm_pct": "ROE TTM",
    "roa_ttm_pct": "ROA TTM",
    "net_margin_ttm_pct": "Net Margin TTM",
    "eps_ttm": "EPS TTM",
    "bvps": "BVPS",
    "net_profit_till_qtr": "Net Profit Till Qtr",
    "revenue_till_qtr": "Revenue Till Qtr",
}


def _firecrawl_keys():
    """Primary key first, then any comma-separated fallbacks."""
    keys = [k for k in [os.environ.get("FIRECRAWL_API_KEY")] if k]
    keys += [k.strip() for k in os.environ.get("FIRECRAWL_FALLBACK_KEYS", "").split(",") if k.strip()]
    return keys


def _firecrawl_markdown(url, timeout=60):
    """Fetch a JS-rendered page's markdown via Firecrawl, rotating keys on 401/402/429."""
    keys = _firecrawl_keys()
    if not keys:
        return None
    last_error = None
    for key in keys:
        try:
            resp = requests.post(
                FIRECRAWL_API_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True, "waitFor": 4000},
                timeout=timeout,
            )
            if resp.status_code in (401, 402, 429):
                logger.warning("Firecrawl key rejected (%s), trying next", resp.status_code)
                last_error = requests.HTTPError(f"{resp.status_code} for {url}")
                continue
            resp.raise_for_status()
            return resp.json().get("data", {}).get("markdown", "")
        except requests.RequestException as exc:
            last_error = exc
            break
    if last_error:
        logger.warning("Firecrawl fetch failed for %s: %s", url, last_error)
    return None


def _parse_row(md_lines, label):
    """Return list of cell strings for the table row containing `label`, or None."""
    for line in md_lines:
        if line.startswith("|") and label in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            return cells
    return None


def _split_value_yoy(cell):
    """Split a cell like '26.09<br> <br> -6.21 %' into (value, yoy_pct) floats."""
    parts = [p.strip() for p in re.split(r"<br\s*/?>", cell) if p.strip()]
    value, yoy = None, None
    for p in parts:
        if "%" in p:
            m = re.search(r"-?[\d,]+(?:\.\d+)?", p)
            if m:
                yoy = float(m.group(0).replace(",", ""))
        elif value is None:
            m = re.search(r"-?[\d,]+(?:\.\d+)?", p)
            if m:
                value = float(m.group(0).replace(",", ""))
    return value, yoy


def _parse_plain_pct(cell):
    m = re.search(r"-?[\d,]+(?:\.\d+)?", cell)
    return float(m.group(0).replace(",", "")) if m else None


def _parse_quarterly_table(markdown, symbol):
    lines = markdown.split("\n")

    header = _parse_row(lines, "Particular")
    quarters = header[1:] if header else []
    latest_q = quarters[-1] if quarters else None

    result = {"symbol": symbol, "latest_quarter": latest_q}

    for key, label in _ROW_LABELS.items():
        row = _parse_row(lines, label)
        if not row or len(row) < 2:
            continue
        last_cell = row[-1]
        if key in ("roe_ttm_pct", "roa_ttm_pct", "net_margin_ttm_pct"):
            result[key] = _parse_plain_pct(last_cell)
        else:
            value, yoy = _split_value_yoy(last_cell)
            result[key] = value
            result[f"{key}_yoy_pct"] = yoy

    return result


class NepseAlphaQuarterlyScraper:
    """Scrape per-company quarterly earnings/ROE trend from nepsealpha.com."""

    def __init__(self, data_dir=None):
        base = Path(__file__).resolve().parent.parent.parent
        self.data_dir = data_dir or (base / "data" / "company-wise")

    def _cache_path(self, symbol):
        return self.data_dir / symbol.upper() / "nepsealpha_quarterly.json"

    def _cache_is_fresh(self, path):
        if not path.exists():
            return False
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - mtime < timedelta(hours=CACHE_TTL_HOURS)

    def get(self, symbol, force_refresh=False):
        symbol = symbol.upper()
        cache_path = self._cache_path(symbol)

        if not force_refresh and self._cache_is_fresh(cache_path):
            try:
                return json.loads(cache_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        markdown = _firecrawl_markdown(f"{NEPSEALPHA_URL}/{symbol}/info")
        if not markdown:
            if cache_path.exists():
                try:
                    return json.loads(cache_path.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
            return {"symbol": symbol, "error": "fetch failed"}

        try:
            data = _parse_quarterly_table(markdown, symbol)
        except Exception as exc:
            logger.warning("Parse failed for %s: %s", symbol, exc)
            return {"symbol": symbol, "error": str(exc)}

        data["scraped_at"] = datetime.now().isoformat(timespec="seconds")
        data["source"] = "nepsealpha.com"

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, indent=2))
        return data


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sym = sys.argv[1] if len(sys.argv) > 1 else "NABIL"
    scraper = NepseAlphaQuarterlyScraper()
    print(json.dumps(scraper.get(sym, force_refresh=True), indent=2))

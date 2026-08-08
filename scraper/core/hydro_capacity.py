"""Hydropower installed-capacity (MW) scraper.

Primary source — the "Capacity (MW)" field on:
    https://chukul.com/stock-profile?symbol={SYMBOL}
(JS-rendered — needs Firecrawl, costs 1 credit per call)

nepsealpha.com and sharesansar.com carry an "Installed Capacity" row too, but
leave it blank ("-  MW") for every symbol checked.

Fallback — for symbols Chukul leaves blank (typically brand-new IPOs), scan
the company's own website. Its URL is read from ShareSansar's "Website Link"
field, or guessed from the domain of ShareSansar's listed company email if
that's blank. The site's homepage text is then scanned for a "capacity ...
MW" mention (e.g. SOHL: soluhydro.com states "82 MW Lower Solu Hydropower
Project"). Best-effort — company sites vary wildly in structure.

Cache per symbol at:
    data/company-wise/{SYMBOL}/hydro_capacity.json

Cache TTL: 30 days — plant capacity essentially never changes.
"""
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from scraper.core.nepsealpha_quarterly import _firecrawl_markdown

logger = logging.getLogger(__name__)

CHUKUL_URL = "https://chukul.com/stock-profile"
SHARESANSAR_URL = "https://www.sharesansar.com/company"
CACHE_TTL_HOURS = 24 * 30

_GENERIC_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com"}

_CAPACITY_RE = re.compile(r"Capacity \(MW\)\s*([\d,]+(?:\.\d+)?)\s*MW")
_MW_NEAR_CAPACITY_RE = re.compile(
    r"(?:installed\s+capacity|capacity)[^.\n\d]{0,40}?(\d{1,4}(?:\.\d+)?)\s*MW",
    re.IGNORECASE,
)
_MW_ANY_RE = re.compile(r"(\d{1,4}(?:\.\d+)?)\s*MW\b")


def _parse_capacity(markdown):
    m = _CAPACITY_RE.search(markdown or "")
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _parse_capacity_from_text(text):
    """Best-effort MW extraction from freeform company-website text."""
    if not text:
        return None
    m = _MW_NEAR_CAPACITY_RE.search(text)
    if m:
        return float(m.group(1))
    m = _MW_ANY_RE.search(text)
    if m:
        return float(m.group(1))
    return None


def _fetch_company_website(symbol):
    """Return a likely company website URL via ShareSansar, or None.

    Prefers the "Website Link" field; falls back to guessing from the
    company's email domain when that field is blank (skips generic mail
    providers like gmail.com, which aren't the company's own domain).
    """
    markdown = _firecrawl_markdown(f"{SHARESANSAR_URL}/{symbol.lower()}")
    if not markdown:
        return None

    m = re.search(r"Website Link \|\s*(\S[^|\n]*)", markdown)
    if m:
        link_m = re.search(r"\((https?://[^\s)]+)\)", m.group(1))
        if link_m:
            return link_m.group(1)
        url_m = re.search(r"https?://\S+", m.group(1))
        if url_m:
            return url_m.group(0)

    email_m = re.search(r"Email \|\s*[\w.+-]+@([\w-]+\.[\w.-]+)", markdown)
    if email_m:
        domain = email_m.group(1).lower()
        if domain not in _GENERIC_EMAIL_DOMAINS:
            return f"https://{domain}/"

    return None


class ChukulCapacityScraper:
    """Scrape installed capacity (MW) for hydropower companies from Chukul."""

    def __init__(self, data_dir=None):
        base = Path(__file__).resolve().parent.parent.parent
        self.data_dir = data_dir or (base / "data" / "company-wise")

    def _cache_path(self, symbol):
        return self.data_dir / symbol.upper() / "hydro_capacity.json"

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

        markdown = _firecrawl_markdown(f"{CHUKUL_URL}?symbol={symbol}")
        if not markdown:
            if cache_path.exists():
                try:
                    return json.loads(cache_path.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
            return {"symbol": symbol, "error": "fetch failed"}

        capacity_mw = _parse_capacity(markdown)
        source = "chukul.com" if capacity_mw else None

        if not capacity_mw:
            website = _fetch_company_website(symbol)
            if website:
                site_markdown = _firecrawl_markdown(website)
                capacity_mw = _parse_capacity_from_text(site_markdown)
                if capacity_mw:
                    source = website

        data = {
            "symbol": symbol,
            "capacity_mw": capacity_mw,
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
        }

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, indent=2))
        return data


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sym = sys.argv[1] if len(sys.argv) > 1 else "AHPC"
    scraper = ChukulCapacityScraper()
    print(json.dumps(scraper.get(sym, force_refresh=True), indent=2))

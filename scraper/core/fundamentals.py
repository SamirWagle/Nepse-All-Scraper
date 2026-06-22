"""
Merolagani fundamentals scraper.

Scrapes per-company fundamentals from:
    https://merolagani.com/CompanyDetail.aspx?symbol={SYMBOL}

Cache per symbol at:
    data/company-wise/{SYMBOL}/fundamentals.json

Cache TTL: 6 hours.
"""
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://merolagani.com/CompanyDetail.aspx"
SHAREHUB_URL = "https://sharehubnepal.com/company"
CACHE_TTL_HOURS = 6

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _parse_number(raw):
    """Parse leading numeric token from raw text → float.

    Handles: '143,402,084,100.00', '530.00', '33.34 (FY:082-083, Q:3)',
    '6.10%', '-1.5', '0.4 %'.
    Returns None on failure.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    # Match leading optional sign + digits (with commas) + optional decimal.
    m = re.match(r"-?[\d,]+(?:\.\d+)?", s)
    if not m:
        return None
    cleaned = m.group(0).replace(",", "")
    if not cleaned or cleaned in (".", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_range(raw):
    """Parse '562.00-471.00' → (562.00, 471.00). Returns (None, None) on failure."""
    if not raw:
        return None, None
    parts = re.split(r"[-–]", str(raw))
    if len(parts) < 2:
        return None, None
    hi = _parse_number(parts[0])
    lo = _parse_number(parts[1])
    return hi, lo


def _extract_fy(raw):
    """Extract FY tag like '(FY:082-083, Q:3)' from value string."""
    if not raw:
        return None
    m = re.search(r"FY:([\d\-]+)", str(raw))
    return m.group(1) if m else None


def _parse_nepali_fy(raw):
    """Normalise Nepali fiscal year string to sortable form '082-083'.

    Accepts: '082/083', '082-083', '2082/83', '2081-082', '081/82', etc.
    Returns None for unrecognisable strings.
    """
    if not raw:
        return None
    s = str(raw).strip()
    m = re.search(r'(\d{2,4})[/-](\d{2,3})', s)
    if not m:
        return None
    left, right = m.group(1), m.group(2)

    def to3(n):
        n = int(n)
        if n > 1000:
            n %= 100
        return f"{n:03d}"
    return f"{to3(left)}-{to3(right)}"


def _update_eps_history(symbol_dir: Path, eps: float, eps_fy: str) -> None:
    """Append current EPS to eps_history.csv when this fiscal year is new.

    File columns: fiscal_year (e.g. '082-083'), eps (float).
    Idempotent — calling multiple times for the same FY is safe.
    """
    import csv as _csv
    fy_norm = _parse_nepali_fy(eps_fy)
    if not fy_norm or eps is None or eps <= 0:
        return

    csv_path = symbol_dir / "eps_history.csv"
    existing: dict = {}
    if csv_path.exists():
        try:
            with open(csv_path, newline="") as f:
                for row in _csv.DictReader(f):
                    try:
                        existing[row["fiscal_year"]] = float(row["eps"])
                    except (KeyError, ValueError):
                        pass
        except OSError:
            pass

    if fy_norm in existing:
        return

    write_header = not existing
    try:
        with open(csv_path, "a", newline="") as f:
            writer = _csv.writer(f)
            if write_header:
                writer.writerow(["fiscal_year", "eps"])
            writer.writerow([fy_norm, round(eps, 2)])
    except OSError as exc:
        logger.warning("Could not write eps_history for %s: %s", symbol_dir.name, exc)


def _fetch_shareholding(symbol, session, timeout=15):
    """Scrape promoter/public share counts from ShareHubNepal.

    Returns dict with keys: promoter_shares, public_shares, promoter_pct,
    public_pct, all_time_high, all_time_high_date. Empty dict on failure.
    """
    try:
        url = f"{SHAREHUB_URL}/{symbol}"
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        html = resp.text

        # Inline JSON keys like \"promoterShares\":162341990
        def _num(key):
            m = re.search(rf'\\?"{key}\\?":(\d+(?:\.\d+)?)', html)
            return float(m.group(1)) if m else None

        def _str(key):
            m = re.search(rf'\\?"{key}\\?":\\?"([^"\\]+)\\?"', html)
            return m.group(1) if m else None

        promoter = _num("promoterShares")
        public = _num("publicShares")
        ath = _num("allTimeHigh")
        ath_date = _str("allTimeHighDate")

        out = {}
        # ShareHubNepal sometimes reports promoterShares:0 for listed companies
        # (e.g. UNL), which is bad data — a listed firm with a real public float
        # still has promoter holding. Treat promoter==0 alongside public>0 as
        # unreliable and skip, rather than overwriting good data with 100% public.
        shareholding_unreliable = (
            promoter is not None and promoter == 0
            and public is not None and public > 0
        )
        if shareholding_unreliable:
            logger.warning(
                "Skipping shareholding for %s: promoterShares=0 (likely bad source data)",
                symbol,
            )
        else:
            if promoter is not None:
                out["promoter_shares"] = promoter
            if public is not None:
                out["public_shares"] = public
            if promoter is not None and public is not None:
                total = promoter + public
                if total > 0:
                    out["promoter_pct"] = round(promoter / total * 100, 2)
                    out["public_pct"] = round(public / total * 100, 2)
        if ath is not None:
            out["all_time_high"] = ath
        if ath_date:
            out["all_time_high_date"] = ath_date
        return out
    except Exception as exc:
        logger.warning("Shareholding scrape failed for %s: %s", symbol, exc)
        return {}


class MerolaganiFundamentalsScraper:
    """Scrape per-company fundamentals from merolagani.com."""

    def __init__(self, data_dir=None):
        base = Path(__file__).resolve().parent.parent.parent
        self.data_dir = data_dir or (base / "data" / "company-wise")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _cache_path(self, symbol):
        return self.data_dir / symbol.upper() / "fundamentals.json"

    def _cache_is_fresh(self, path):
        if not path.exists():
            return False
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - mtime < timedelta(hours=CACHE_TTL_HOURS)

    def get(self, symbol, force_refresh=False):
        """Return fundamentals dict for symbol. Uses cache when fresh."""
        symbol = symbol.upper()
        cache_path = self._cache_path(symbol)

        if not force_refresh and self._cache_is_fresh(cache_path):
            try:
                return json.loads(cache_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        try:
            data = self._scrape(symbol)
        except Exception as exc:
            logger.warning("Fundamentals scrape failed for %s: %s", symbol, exc)
            if cache_path.exists():
                try:
                    return json.loads(cache_path.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
            return {"symbol": symbol, "error": str(exc)}

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, indent=2))
        return data

    def _scrape(self, symbol):
        url = f"{BASE_URL}?symbol={symbol}"
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table", id="accordion")
        if not table:
            raise RuntimeError("accordion table not found")

        raw = {}
        for tbody in table.find_all("tbody", recursive=False):
            tr = tbody.find("tr")
            if not tr:
                continue
            th = tr.find("th")
            td = tr.find("td")
            if not th or not td:
                continue
            label = " ".join(th.get_text(strip=True).split()).rstrip(":")
            value = " ".join(td.get_text(" ", strip=True).split())
            if label and value:
                raw[label] = value

        name_span = soup.find("span", id=lambda x: x and "companyName" in x)
        company_name = name_span.get_text(strip=True) if name_span else symbol

        h52, l52 = _parse_range(raw.get("52 Weeks High - Low", ""))

        result = {
            "symbol": symbol,
            "company_name": company_name,
            "sector": raw.get("Sector"),
            "shares_outstanding": _parse_number(raw.get("Shares Outstanding")),
            "market_price": _parse_number(raw.get("Market Price")),
            "percent_change": _parse_number(raw.get("% Change")),
            "last_traded_on": raw.get("Last Traded On"),
            "high_52w": h52,
            "low_52w": l52,
            "avg_180d": _parse_number(raw.get("180 Day Average")),
            "avg_120d": _parse_number(raw.get("120 Day Average")),
            "year_yield_pct": _parse_number(raw.get("1 Year Yield")),
            "eps": _parse_number(raw.get("EPS")),
            "eps_fy": _extract_fy(raw.get("EPS")),
            "pe_ratio": _parse_number(raw.get("P/E Ratio")),
            "book_value": _parse_number(raw.get("Book Value")),
            "pbv": _parse_number(raw.get("PBV")),
            "dividend_pct": _parse_number(raw.get("% Dividend")),
            "dividend_fy": _extract_fy(raw.get("% Dividend")),
            "avg_volume_30d": _parse_number(raw.get("30-Day Avg Volume")),
            "market_cap": _parse_number(raw.get("Market Capitalization")),
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "source": "merolagani.com",
        }
        # Accumulate EPS history for Shiller P/E — appends to eps_history.csv
        if result.get("eps") and result.get("eps_fy"):
            _update_eps_history(Path(self.data_dir) / result["symbol"], result["eps"], result["eps_fy"])
        # Best-effort: merge shareholding + ATH from ShareHubNepal (free)
        result.update(_fetch_shareholding(symbol, self.session))
        return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sym = sys.argv[1] if len(sys.argv) > 1 else "NABIL"
    scraper = MerolaganiFundamentalsScraper()
    print(json.dumps(scraper.get(sym, force_refresh=True), indent=2))

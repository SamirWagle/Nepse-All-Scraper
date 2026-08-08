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


def _update_financial_history(symbol_dir: Path, record: dict) -> None:
    """Accumulate yearly financial snapshots to financial_history.csv.

    Columns: fiscal_year, net_profit, total_revenue, npl_pct, book_value, dividend_pct
    Idempotent per fiscal_year — only appends when a new FY is seen.
    """
    import csv as _csv
    fy = record.get("fiscal_year")
    if not fy:
        return
    csv_path = symbol_dir / "financial_history.csv"
    COLS = ["fiscal_year", "net_profit", "total_revenue", "npl_pct", "book_value", "dividend_pct"]
    existing: dict = {}
    if csv_path.exists():
        try:
            with open(csv_path, newline="") as f:
                for row in _csv.DictReader(f):
                    existing[row["fiscal_year"]] = row
        except OSError:
            pass
    if fy in existing:
        return
    write_header = not existing
    try:
        with open(csv_path, "a", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=COLS)
            if write_header:
                writer.writeheader()
            writer.writerow({c: record.get(c, "") for c in COLS})
    except OSError as exc:
        logger.warning("Could not write financial_history for %s: %s", symbol_dir.name, exc)


def _read_financial_history(symbol_dir: Path) -> list:
    """Return last 3 years of financial_history.csv rows, newest first."""
    import csv as _csv
    csv_path = symbol_dir / "financial_history.csv"
    if not csv_path.exists():
        return []
    try:
        with open(csv_path, newline="") as f:
            rows = list(_csv.DictReader(f))
        rows.sort(key=lambda r: r.get("fiscal_year", ""), reverse=True)
        return rows[:3]
    except OSError:
        return []


def _apply_eps_fallback(result, company_dir):
    """Fill EPS/P-E from the NepseAlpha quarterly file when Merolagani has none.

    Merolagani reports EPS 0.00 until a company files a full year after listing,
    and a literal 0.00 P/E is worse than no answer — it reads as a real ratio.
    NepseAlpha publishes EPS TTM from the quarterlies, which covers exactly the
    newly listed companies Merolagani leaves blank (SOHL: EPS TTM 11.44).

    Anything still unknown becomes None so the UI renders an em dash.
    """
    if result.get("eps"):
        return

    quarterly_path = Path(company_dir) / "nepsealpha_quarterly.json"
    eps_ttm = None
    if quarterly_path.exists():
        try:
            quarterly = json.loads(quarterly_path.read_text())
            eps_ttm = quarterly.get("eps_ttm")
            latest_quarter = quarterly.get("latest_quarter")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s: %s", quarterly_path, exc)

    if eps_ttm and eps_ttm > 0:
        result["eps"] = eps_ttm
        result["eps_fy"] = latest_quarter or result.get("eps_fy")
        result["eps_source"] = "nepsealpha.com (EPS TTM)"
        price = result.get("market_price")
        if price:
            result["pe_ratio"] = round(price / eps_ttm, 2)
        return

    # No EPS anywhere: report unknown rather than zero.
    result["eps"] = None
    if not result.get("pe_ratio"):
        result["pe_ratio"] = None


def _apply_hydro_capacity(result, company_dir):
    """Fill installed capacity (MW) from the cached Chukul scrape, hydro sector only."""
    if (result.get("sector") or "").strip().lower() != "hydro power":
        return

    capacity_path = Path(company_dir) / "hydro_capacity.json"
    if not capacity_path.exists():
        return
    try:
        capacity = json.loads(capacity_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s: %s", capacity_path, exc)
        return

    if capacity.get("capacity_mw"):
        result["capacity_mw"] = capacity["capacity_mw"]


def _fetch_shareholding(symbol, session, timeout=15):
    """Scrape promoter/public share counts and financial metrics from ShareHubNepal.

    Returns dict with keys: promoter_shares, public_shares, promoter_pct,
    public_pct, all_time_high, all_time_high_date, and best-effort financial
    fields: net_profit_sharehub, total_revenue_sharehub, npl_pct_sharehub.
    Empty dict on failure.
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
        # Hydropower IPOs carry a project-affected-locals tranche that
        # ShareHubNepal reports separately. Ignoring it made promoter+public
        # fall short of listedShares, so the mismatch guard below discarded
        # good data for 91 hydropower companies (SOHL: 80M + 10M + 10M = 100M).
        # Locals are ordinary non-promoter holders, so they count as public.
        local = _num("localShares")
        if local:
            public = (public or 0) + local
        listed = _num("listedShares")
        ath = _num("allTimeHigh")
        ath_date = _str("allTimeHighDate")

        out = {}
        # ShareHubNepal sometimes reports promoterShares:0 when it has no data —
        # arithmetic still checks out (0 + public == listedShares) so the old
        # sum-mismatch check couldn't catch it. Confirmed bad on UNL 2026-08:
        # JSON says promoterShares:0 but ShareHub's own page prose says ~80%
        # Hindustan Unilever + ~5% Sibkrim Land & Industrial. Only AKJCL is a
        # confirmed genuine 100%-public company — treat any other promoter==0
        # as unreliable rather than silently trusting it.
        GENUINE_ZERO_PROMOTER_SYMBOLS = {"AKJCL"}
        shareholding_unreliable = (
            promoter is not None and public is not None and listed is not None
            and abs((promoter + public) - listed) > 1
        ) or (
            promoter is not None and public is not None
            and promoter == 0 and public == 0
        ) or (
            promoter is not None and promoter == 0
            and symbol not in GENUINE_ZERO_PROMOTER_SYMBOLS
        )
        if shareholding_unreliable:
            logger.warning(
                "Skipping shareholding for %s: promoter+public doesn't match listedShares (bad source data)",
                symbol,
            )
        else:
            if promoter is not None:
                out["promoter_shares"] = promoter
            if public is not None:
                out["public_shares"] = public
            if local:
                out["local_shares"] = local
            if promoter is not None and public is not None:
                total = promoter + public
                if total > 0:
                    out["promoter_pct"] = round(promoter / total * 100, 2)
                    out["public_pct"] = round(public / total * 100, 2)
        if ath is not None:
            out["all_time_high"] = ath
        if ath_date:
            out["all_time_high_date"] = ath_date

        # Extract additional fields confirmed present in sharehubnepal inline JSON.
        paid_up = _num("paidUpCapital")
        bonus_val = _num("bonus")
        if paid_up is not None:
            out["paid_up_capital"] = paid_up
        if bonus_val is not None:
            out["bonus_dividend_pct"] = bonus_val

        return out
    except Exception as exc:
        logger.warning("Shareholding scrape failed for %s: %s", symbol, exc)
        return {}


SHARESANSAR_URL = "https://www.sharesansar.com/company"
NEPSEALPHA_URL = "https://nepsealpha.com/stocks"
CHUKUL_URL = "https://chukul.com/stock-profile"
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"

_NEPALI_UNIT_MULTIPLIER = {"ar": 1_000_000_000, "cr": 10_000_000, "lac": 100_000}


def _firecrawl_markdown(url, timeout=30):
    """Fetch a JS-rendered page's markdown via Firecrawl. Returns str or None.

    Costs a Firecrawl credit per call — only use for tiebreaker sources, not
    routine per-scrape fetches.
    """
    import os
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.post(
            FIRECRAWL_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("markdown", "")
    except Exception as exc:
        logger.warning("Firecrawl fetch failed for %s: %s", url, exc)
        return None


def _fetch_sharesansar_shares(symbol, session, timeout=15):
    """Scrape 'Listed Shares' from ShareSansar's company page. Returns float or None."""
    try:
        url = f"{SHARESANSAR_URL}/{symbol.lower()}"
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        m = re.search(r"Listed Shares</td>\s*<td[^>]*>\s*([\d,]+(?:\.\d+)?)", resp.text)
        return float(m.group(1).replace(",", "")) if m else None
    except Exception as exc:
        logger.warning("ShareSansar shares scrape failed for %s: %s", symbol, exc)
        return None


def _fetch_nepsealpha_paid_up_capital(symbol):
    """Fetch 'Paid Up Capital' from nepsealpha.com (JS-rendered — needs Firecrawl).
    Tiebreaker source only; costs a Firecrawl credit per call. Returns float or None.
    """
    markdown = _firecrawl_markdown(f"{NEPSEALPHA_URL}/{symbol}/info")
    if not markdown:
        return None
    m = re.search(r"Paid Up Capital \| NPR ([\d,]+(?:\.\d+)?)", markdown)
    return float(m.group(1).replace(",", "")) if m else None


def _fetch_chukul_paid_up_capital(symbol):
    """Fetch 'Paid-up Capital' from chukul.com (JS-rendered — needs Firecrawl).
    Value is shown abbreviated (e.g. '1.07 Ar.' = 1.07 Arba). Tiebreaker source
    only; costs a Firecrawl credit per call. Returns float or None.

    Weighted low (0.5) in the reconciliation vote — observed 2026-07 lagging on
    HPPL's rights-issue-corrected paid-up capital the same way merolagani and
    ShareSansar did, so it's not a reliably fast-updating source despite reporting
    the same field as ShareHub/NepseAlpha.
    """
    markdown = _firecrawl_markdown(f"{CHUKUL_URL}?symbol={symbol}")
    if not markdown:
        return None
    m = re.search(r"Paid-up Capital([\d.]+)\s*(Ar|Cr|Lac)\.", markdown)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    return value * _NEPALI_UNIT_MULTIPLIER[unit]


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
        _apply_eps_fallback(result, Path(self.data_dir) / symbol)
        _apply_hydro_capacity(result, Path(self.data_dir) / symbol)

        # Accumulate EPS history for Shiller P/E — appends to eps_history.csv
        if result.get("eps") and result.get("eps_fy"):
            _update_eps_history(Path(self.data_dir) / result["symbol"], result["eps"], result["eps_fy"])
        # Best-effort: merge shareholding + ATH + financial metrics from ShareHubNepal
        result.update(_fetch_shareholding(symbol, self.session))

        # Derived: net_profit = EPS × shares_outstanding (current FY only)
        # Uses merolagani's shares_outstanding as-is here — EPS is reported against
        # that same (possibly pre-rights-issue) share base, so this stays consistent
        # even if shares_outstanding gets corrected below.
        if result.get("eps") and result.get("shares_outstanding"):
            result["net_profit"] = round(result["eps"] * result["shares_outstanding"], 2)

        # merolagani's shares_outstanding/market_cap/book_value/pbv can lag behind a
        # rights issue (site doesn't always recompute promptly). Cross-check against
        # up to 4 other sources: ShareHubNepal's paid_up_capital (already fetched
        # above, free) and ShareSansar's "Listed Shares" (one extra cheap HTTP call)
        # run routinely; NepseAlpha's and chukul's paid-up capital (both JS-rendered,
        # need Firecrawl — costs a credit each) only run as tiebreakers when the
        # cheap sources disagree, not on every scrape of every ticker. Observed on
        # HPPL 2026-07: merolagani AND sharesansar both still showed 10,654,170
        # shares weeks after a rights allotment that ShareHub/NepseAlpha's paid-up
        # capital already reflected as 15,981,255 — a 2-vs-2 split needing a
        # tiebreaker. chukul also turned out to lag on this same field (still showed
        # the stale figure), hence its lower weight below.
        old_shares = result.get("shares_outstanding")
        if old_shares:
            paid_up = result.get("paid_up_capital")
            sharehub_shares = paid_up / 100.0 if paid_up else None
            sharesansar_shares = _fetch_sharesansar_shares(symbol, self.session)

            def _disagrees(a, b):
                return a is not None and b is not None and abs(a - b) / b > 0.02

            # weight 1.5 for paid-up-capital-derived sources proven fast-updating
            # (ShareHub, NepseAlpha); 1.0 for raw "shares outstanding"/"listed
            # shares" display fields (merolagani, ShareSansar); 0.5 for chukul,
            # which reports the same paid-up-capital field but was caught lagging
            # on HPPL just like the 1.0-tier sources — same field, slower site.
            votes = [(old_shares, 1.0)]  # merolagani's own value
            if sharehub_shares is not None:
                votes.append((sharehub_shares, 1.5))
            if sharesansar_shares is not None:
                votes.append((sharesansar_shares, 1.0))

            candidates = [v for v, _ in votes[1:]]
            signal = any(_disagrees(c, old_shares) for c in candidates)
            if signal:
                nepsealpha_paid_up = _fetch_nepsealpha_paid_up_capital(symbol)
                if nepsealpha_paid_up:
                    votes.append((nepsealpha_paid_up / 100.0, 1.5))
                chukul_paid_up = _fetch_chukul_paid_up_capital(symbol)
                if chukul_paid_up:
                    votes.append((chukul_paid_up / 100.0, 0.5))

            # Cluster votes within 2% of each other; the cluster with the highest
            # weight sum wins (ties: keep merolagani's own value, don't guess).
            best_cluster, best_weight = None, 0.0
            for v, _ in votes:
                cluster = [(x, w) for x, w in votes if abs(x - v) / v <= 0.02]
                weight = sum(w for _, w in cluster)
                if weight > best_weight:
                    best_cluster, best_weight = cluster, weight
            derived_shares = (
                sum(x * w for x, w in best_cluster) / sum(w for _, w in best_cluster)
                if best_cluster else None
            )

            if derived_shares and abs(derived_shares - old_shares) / old_shares > 0.02:
                logger.warning(
                    "%s: shares_outstanding stale (%.0f vs %d-source consensus %.0f, weight %.1f) — correcting",
                    symbol, old_shares, len(best_cluster), derived_shares, best_weight,
                )
                # New shares from a rights issue bring in fresh paid-in capital at par
                # (Rs.100) — equity isn't just the old equity spread over more shares,
                # it grows by (new_shares - old_shares) x par. Verified against
                # nepsealpha's HPPL book value (118.53): dividing old equity by the
                # new share count alone gives 85.19, which is wrong.
                equity = result.get("book_value") * old_shares if result.get("book_value") else None
                if equity:
                    equity += (derived_shares - old_shares) * 100.0
                result["shares_outstanding"] = derived_shares
                if result.get("market_price"):
                    result["market_cap"] = round(result["market_price"] * derived_shares, 2)
                if equity:
                    result["book_value"] = round(equity / derived_shares, 2)
                    if result.get("market_price"):
                        result["pbv"] = round(result["market_price"] / result["book_value"], 2)
            elif signal:
                logger.warning(
                    "%s: shares_outstanding disagreement across sources, no 2-source consensus reached — leaving as-is",
                    symbol,
                )

        # Accumulate financial snapshot for 3-year history
        symbol_dir = Path(self.data_dir) / result["symbol"]
        _update_financial_history(symbol_dir, {
            "fiscal_year":  result.get("eps_fy", ""),
            "net_profit":   result.get("net_profit", ""),
            "total_revenue": result.get("total_revenue", ""),
            "npl_pct":      result.get("npl_pct", ""),
            "book_value":   result.get("book_value", ""),
            "dividend_pct": result.get("dividend_pct", ""),
        })

        # Attach last 3 years of accumulated history
        result["financial_history"] = _read_financial_history(symbol_dir)

        return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sym = sys.argv[1] if len(sys.argv) > 1 else "NABIL"
    scraper = MerolaganiFundamentalsScraper()
    print(json.dumps(scraper.get(sym, force_refresh=True), indent=2))

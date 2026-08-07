"""
ShareSansar merger announcement scraper.

This scrapes ShareSansar's merger/acquisition content feed and tries to extract
company merger records into a normalized registry format consumed by the app.

Output:
    data/company_mergers.json

The scraper is intentionally conservative:
    - It only marks a symbol as closed when the article text strongly suggests it
    - It can also mark the surviving company as active_survivor when the article
      explicitly says the joint transaction continues under the surviving name
    - Records are written as registry entries that can be reviewed/edited later
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sharesansar.com"
CATEGORY_URLS = [
    f"{BASE_URL}/merger-acquisition",
    f"{BASE_URL}/category/mergeracquistion",
    f"{BASE_URL}/merged-companies",
]
KNOWN_SEED_URLS = [
    "https://www.sharesansar.com/merged-companies",
    "https://www.sharesansar.com/merger-acquisition",
    "https://www.sharesansar.com/index.php/newsdetail/share-trading-of-civil-bank-limited-stops-from-today-integrated-transaction-with-himalayan-bank-limited-to-start-from-falgun-12-2023-02-16",
    "https://www.sharesansar.com/newsdetail/global-ime-bank-inks-final-merger-deal-with-bank-of-kathmandu-becoming-largest-bank-in-the-nation-thus-amalgamating-21-bfis-so-far-2022-11-15",
    "https://www.sharesansar.com/index.php/newsdetail/global-ime-bank-and-bank-of-kathmandu-begin-joint-transaction-after-successful-merger-becomes-biggest-bank-in-the-nation-in-almost-every-parameter-2023-01-10",
    "https://www.sharesansar.com/newsdetail/final-merger-agreement-between-global-ime-bank-bank-of-kathmandu-completed-integrated-transaction-to-start-from-poush-25-2023-01-05",
    "https://www.sharesansar.com/index.php/newsdetail/civil-bank-international-leasing-finance-joint-transaction-starts-from-today-as-civil-bank",
    "https://www.sharesansar.com/newsdetail/global-ime,commerz-and-trust-start-operation-as-merged-entity",
    "https://www.sharesansar.com/newsdetail/final-merger-procedure-between-sagarmatha-lumbini-insurance-completed-integrated-transaction-to-start-from-falgun-29-2023-03-10",
    "https://www.sharesansar.com/newsdetail/after-the-successful-merger-302-crore-unit-shares-of-igi-prudential-insurance-listed-in-nepse-for-trading-2023-06-01",
    "https://www.sharesansar.com/newsdetail/after-the-successful-merger-262-crore-unit-shares-of-sagarmatha-lumbini-insurance-company-salico-listed-in-nepse-for-trading-2023-05-14",
]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class MergerRecord:
    symbol: str
    status: str = "closed"
    display_name: str | None = None
    merged_date: str | None = None
    merged_into: str | None = None
    merged_into_name: str | None = None
    merged_from: str | None = None
    merged_from_name: str | None = None
    surviving_symbol: str | None = None
    surviving_name: str | None = None
    display_mode: str = "closed"
    note: str | None = None
    source_url: str | None = None
    source_title: str | None = None


def _make_session() -> requests.Session:
    """Use cloudscraper when installed (bypasses ShareSansar's Cloudflare
    challenge); fall back to a normal requests.Session."""
    try:
        import cloudscraper  # type: ignore
        s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "darwin", "desktop": True})
    except Exception:
        s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def _normalize_company_name_key(name: str) -> str:
    """Aggressive normalization for cross-source name lookup.

    Strips HTML, parenthetical ticker, leading qualifiers like "(Former)",
    common suffixes (Limited/Ltd./Bank), ampersands, punctuation, and
    whitespace. Returns uppercase key."""
    if not name:
        return ""
    text = re.sub(r"<[^>]+>", " ", name)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("\xa0", " ")
    # Drop "(Former)", "(NEW)", "(Old)" leading qualifiers
    text = re.sub(r"\(\s*(former|new|old)\s*\)", " ", text, flags=re.I)
    text = re.sub(r"\(\s*[A-Z0-9]+\s*\)", " ", text)  # drop (TICKER)
    text = text.upper()
    text = re.sub(
        r"\b(LIMITED|LIMTIED|LTD|LTD\.|COMPANY|CO\.|CO|PRIVATE|PVT|PVT\.|NEPAL|THE|FORMER)\b",
        " ", text,
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class ShareSansarMergerScraper:
    def __init__(self, data_dir: Path | None = None):
        base = Path(__file__).resolve().parent.parent.parent
        self.data_dir = data_dir or (base / "data")
        self.registry_path = self.data_dir / "company_mergers.json"
        self._session = _make_session()
        self._symbol_name_map = self._load_symbol_name_map()
        self._symbols = set(self._symbol_name_map.keys())
        self._name_to_symbol = {
            self._normalize_text(name).upper(): sym
            for sym, name in self._symbol_name_map.items()
        }
        # Looser key map for fuzzy name lookup across sources.
        self._fuzzy_name_to_symbol: dict[str, str] = {}
        for sym, name in self._symbol_name_map.items():
            key = _normalize_company_name_key(self._clean_company_name(name))
            if key and key not in self._fuzzy_name_to_symbol:
                self._fuzzy_name_to_symbol[key] = sym

    def _load_symbol_name_map(self) -> dict[str, str]:
        mapping = {}
        for path in [self.data_dir / "company_names.json", self.data_dir / "company_id_mapping.json"]:
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text())
            except Exception:
                continue
            if path.name == "company_names.json":
                for sym, name in raw.items():
                    mapping[sym.upper()] = self._clean_company_name(str(name))
            else:
                for sym in raw.keys():
                    mapping.setdefault(sym.upper(), sym)
        return mapping

    def _load_existing_registry(self) -> dict:
        if not self.registry_path.exists():
            return {"version": 1, "entries": {}}
        raw = json.loads(self.registry_path.read_text())
        if "entries" in raw and isinstance(raw["entries"], dict):
            return raw
        return {"version": 1, "entries": raw if isinstance(raw, dict) else {}}

    def _save_registry(self, registry: dict) -> None:
        self.registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False))

    def _merge_entry(self, existing: dict, new: dict) -> dict:
        """
        Keep already-saved values intact and only fill gaps from newer data.
        """
        merged = dict(existing)
        for key, value in new.items():
            if value is None:
                continue
            if key not in merged or merged[key] in (None, "", [], {}):
                merged[key] = value
        return merged

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _clean_company_name(self, name: str) -> str:
        cleaned = self._normalize_text(name)
        # Drop trailing " ( SYMBOL )" or "(SYMBOL)" (names file embeds it from raw HTML).
        cleaned = re.sub(r"\s*\(\s*[A-Z0-9]+\s*\)\s*$", "", cleaned).strip()
        return cleaned

    @staticmethod
    def _name_is_matchable(name: str) -> bool:
        """A company name is safe to substring-match only when long enough and
        mostly alphabetic. Otherwise '2' or 'API' would match unrelated text."""
        if not name or len(name) < 6:
            return False
        return sum(1 for ch in name if ch.isalpha()) >= 4

    MERGER_KEYWORDS = re.compile(
        r"\b(merger|merged|merging|acquisition|acquired|amalgamat\w*|joint transaction|integrated transaction)\b",
        re.I,
    )

    # ShareSansar's registry lists the exchange itself as a company, and every
    # merger headline ends "...listed in NEPSE for trading". Left in, the bare
    # ticker match reads that as the exchange being a merger party — which is
    # how IGI ended up recorded as having merged into NEPSE.
    EXCLUDED_SYMBOLS = frozenset({"NEPSE"})

    ARTICLE_SELECTORS = (
        "article",
        "[itemprop=articleBody]",
        ".news-detail",
        ".newsdetail",
        ".news-content",
        ".article-content",
        ".content-detail",
        "main",
    )

    def _extract_title_and_body(self, html: str) -> tuple[str, str]:
        """Pull title from <h1>/<title> and body from the article container only.
        Falls back to full DOM when no article container is found, but strips
        common chrome (header/nav/footer/aside) first to avoid matching
        unrelated tickers in the global menu/sidebar."""
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        for selector in ["h1", "h2", "title"]:
            tag = soup.select_one(selector)
            if tag:
                title = self._normalize_text(tag.get_text(" ", strip=True))
                if title:
                    break

        container = None
        for sel in self.ARTICLE_SELECTORS:
            container = soup.select_one(sel)
            if container:
                break
        if container is None:
            for tag in soup(["header", "nav", "footer", "aside", "script", "style"]):
                tag.decompose()
            container = soup.body or soup

        body = self._normalize_text(container.get_text(" ", strip=True))
        return title, body

    def _discover_article_links(self, max_pages: int | None = None) -> list[str]:
        links: list[str] = []
        seen = set()
        for base_url in CATEGORY_URLS:
            url = base_url
            page = 0
            while True:
                page += 1
                if max_pages and page > max_pages:
                    break
                try:
                    resp = self._session.get(url, timeout=30)
                    resp.raise_for_status()
                except Exception as exc:
                    logger.warning("Merger feed fetch failed for %s: %s", url, exc)
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/newsdetail/" in href or "/eventdetail/" in href:
                        full = href if href.startswith("http") else f"{BASE_URL}{href}"
                        if full not in seen:
                            seen.add(full)
                            links.append(full)
                next_link = soup.find("a", string=re.compile(r"Next", re.I)) or soup.find("a", href=re.compile(r"cursor="))
                if not next_link or not next_link.get("href"):
                    break
                href = next_link["href"]
                url = href if href.startswith("http") else f"{BASE_URL}{href}"
        return links

    def _candidate_symbols(self, text: str) -> list[str]:
        """Return tickers that appear *near* merger language in `text`.

        Rules to prevent false positives:
          - A bare ticker (e.g. "API") must occur within 200 chars of a merger
            keyword, so it can't match a sidebar/menu mention.
          - A full company name match requires `_name_is_matchable` so junk
            names like "2" cannot match.
        """
        text_up = text.upper()
        # Pre-compute merger-keyword positions to test proximity cheaply.
        keyword_spans = [m.start() for m in self.MERGER_KEYWORDS.finditer(text)]
        if not keyword_spans:
            return []

        def near_keyword(pos: int, window: int = 200) -> bool:
            return any(abs(pos - k) <= window for k in keyword_spans)

        candidates: list[str] = []
        for sym, name in self._symbol_name_map.items():
            if sym in self.EXCLUDED_SYMBOLS:
                continue
            name_clean = self._clean_company_name(name)
            name_up = name_clean.upper() if name_clean else ""
            matched = False
            if self._name_is_matchable(name_clean):
                pos = text_up.find(name_up)
                if pos != -1 and near_keyword(pos):
                    matched = True
            if not matched:
                m = re.search(rf"(?<![A-Z0-9]){re.escape(sym)}(?![A-Z0-9])", text_up)
                if m and near_keyword(m.start()):
                    matched = True
            if matched:
                candidates.append(sym)
        return list(dict.fromkeys(candidates))

    def _symbol_for_company_name(self, company_name: str | None) -> str | None:
        if not company_name:
            return None
        target = self._normalize_text(company_name).upper()
        sym = self._name_to_symbol.get(target)
        return None if sym in self.EXCLUDED_SYMBOLS else sym

    def _extract_company_profile_names(self, text: str) -> list[str]:
        names = []
        for match in re.finditer(r"### Company Profile\s+(.*?)(?:###|$)", text, re.I | re.S):
            chunk = match.group(1)
            for part in re.split(r"\n+", chunk):
                part = self._normalize_text(part)
                if part and len(part) > 3:
                    # Keep only values that map exactly to a known company name.
                    if self._symbol_for_company_name(part):
                        names.append(part)
        return list(dict.fromkeys(names))

    @staticmethod
    def _parse_company_info_table(soup: BeautifulSoup) -> dict[str, str]:
        """Read the ShareSansar company-page info table into {Key: Value}.

        Field names observed: Symbol, Name, Sector, Operation Date,
        Listed Shares, Paid Up, Total Paid Up Value, Phone Number, Email,
        Address, Website Link, Share Registrar.
        """
        info: dict[str, str] = {}
        for table in soup.select("table"):
            for tr in table.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if len(cells) < 2:
                    continue
                key = re.sub(r"\s+", " ", cells[0]).strip().rstrip(":")
                val = re.sub(r"\s+", " ", " ".join(cells[1:])).strip()
                if key and val:
                    info.setdefault(key, val)
        return info

    def _scrape_merged_company_pages(self, symbols: list[str] | None = None, max_symbols: int | None = None) -> list[MergerRecord]:
        """Scan ShareSansar company pages and keep symbols whose info table
        says Sector: Merged. Extracts Operation Date as merged_date when
        present."""
        if symbols is None:
            symbols = sorted(self._symbols)
        else:
            symbols = [sym.upper() for sym in symbols if sym]
        if max_symbols:
            symbols = symbols[:max_symbols]

        records: list[MergerRecord] = []
        for sym in symbols:
            try:
                resp = self._session.get(f"{BASE_URL}/company/{sym.lower()}", timeout=20)
                resp.raise_for_status()
            except Exception:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            info = self._parse_company_info_table(soup)
            sector = (info.get("Sector") or "").strip()
            if sector.lower() != "merged":
                continue

            display_name = self._clean_company_name(
                info.get("Name") or self._symbol_name_map.get(sym, "") or sym
            )
            # Note: ShareSansar's "Operation Date" on company pages is the
            # company's start-of-operation date (founding/listing era), not
            # the merger date. Do NOT store it as merged_date — it would be
            # wrong for almost every merged symbol (e.g. BOK shows 1995).

            records.append(MergerRecord(
                symbol=sym,
                status="closed",
                display_name=display_name,
                display_mode="closed",
                note=f"{display_name} is marked as Merged on ShareSansar company page.",
                source_url=f"{BASE_URL}/company/{sym.lower()}",
                source_title=f"ShareSansar company page ({sym})",
            ))

        return records

    def _fetch_ma_feed(self) -> list[dict]:
        """Pull the full ShareSansar Mergers & Acquisitions DataTable feed.

        Returns the raw row dicts across both `type` partitions (0/1). The
        endpoint requires Sec-Fetch headers and a warm session; we paginate
        with length=20 because larger pages trigger a Cloudflare 202 stall.
        """
        ma_url = f"{BASE_URL}/merger-acquisition"
        # Warm the session — the endpoint refuses cold XHR calls.
        try:
            self._session.get(f"{BASE_URL}/", timeout=30)
            self._session.get(ma_url, timeout=30)
        except Exception as exc:
            logger.warning("M&A warm-up failed: %s", exc)
            return []

        hdrs = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": ma_url,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

        rows: list[dict] = []
        for type_partition in (1, 0):
            draw = 1
            for start in range(0, 1000, 20):
                try:
                    resp = self._session.get(
                        ma_url,
                        params={
                            "type": str(type_partition),
                            "draw": str(draw),
                            "start": str(start),
                            "length": "20",
                        },
                        headers=hdrs,
                        timeout=30,
                    )
                except Exception as exc:
                    logger.warning("M&A fetch error type=%s start=%s: %s", type_partition, start, exc)
                    break
                if resp.status_code != 200:
                    logger.warning("M&A fetch non-200 type=%s start=%s status=%s", type_partition, start, resp.status_code)
                    break
                try:
                    page = resp.json().get("data", [])
                except Exception:
                    page = []
                if not page:
                    break
                rows.extend(page)
                draw += 1
        return rows

    # An "absorbed" segment from ShareSansar is normally one full corporate
    # name. We detect segment terminators (Limited / Ltd / Sanstha) so the
    # " and " inside multi-word names ("Credit and Commerce Bank Limited")
    # does not split the entity name in half.
    _SEGMENT_TERMINATOR = re.compile(
        r"\b(LIMITED|LIMTIED|LTD\.?|SANSTHA|COMPANY|MARKETS|CAPITAL)\b",
        re.I,
    )

    @classmethod
    def _split_absorbed_names(cls, text: str) -> list[str]:
        """Split a ShareSansar 'companies' cell into individual company names.

        Names are joined by ' and ' / ' & ' / ',' with HTML entities, but the
        connectors also appear inside legitimate names. We split on connectors
        then re-glue any fragment that doesn't end with a corporate-form word
        back to the previous fragment."""
        if not text:
            return []
        cleaned = re.sub(r"<[^>]+>", " ", text)
        cleaned = cleaned.replace("&amp;", "&").replace("&nbsp;", " ").replace("\xa0", " ")

        raw_parts = re.split(r"\s+(?:and|&)\s+|\s*,\s*", cleaned, flags=re.I)
        merged: list[str] = []
        for part in raw_parts:
            piece = re.sub(r"\s+", " ", part).strip().strip(".")
            if not piece:
                continue
            if merged and not cls._SEGMENT_TERMINATOR.search(merged[-1]):
                # Previous segment was incomplete — re-glue with " and ".
                merged[-1] = f"{merged[-1]} and {piece}"
            else:
                merged.append(piece)
        return [p for p in merged if len(p) > 3]

    def _resolve_name_to_symbol(self, name: str) -> str | None:
        """Map a raw company-name string from a ShareSansar feed to a known
        ticker via several lookup tiers."""
        if not name:
            return None
        # 1) parenthetical ticker (e.g. "... Limited (NCCB)")
        m = re.search(r"\(\s*([A-Z][A-Z0-9]{1,9})\s*\)", name)
        if m and m.group(1) in self._symbols and m.group(1) not in self.EXCLUDED_SYMBOLS:
            return m.group(1)
        # 2) exact normalized name
        sym = self._symbol_for_company_name(name)
        if sym:
            return sym
        # 3) aggressive normalized key
        key = _normalize_company_name_key(name)
        if key and key in self._fuzzy_name_to_symbol:
            return self._fuzzy_name_to_symbol[key]
        # 4) suffix-aware: try stripping " Promoter Share" / " Promotor Share"
        stripped = re.sub(r"\b(Promoter|Promotor)\s+Share\b", "", name, flags=re.I).strip()
        if stripped and stripped != name:
            return self._resolve_name_to_symbol(stripped)
        return None

    def _records_from_ma_row(self, row: dict) -> list[MergerRecord]:
        """Convert one M&A feed row into MergerRecord(s) for absorbed sym(s).

        We only emit a record when:
          - survivor symbol exists in our universe
          - absorbed symbol resolves to a different known ticker
          - the row carries at least one date (transaction/final/mou)
        """
        company = row.get("company") or {}
        survivor_sym = (company.get("symbol") or "").upper()
        survivor_name = company.get("companyname") or ""
        if not survivor_sym or survivor_sym not in self._symbols:
            return []

        merged_date = row.get("transaction_date") or row.get("final_date") or row.get("mou_date")
        if merged_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(merged_date)):
            merged_date = None

        absorbed_names = self._split_absorbed_names(row.get("companies") or "")
        absorbed_syms: list[str] = []
        for name in absorbed_names:
            sym = self._resolve_name_to_symbol(name)
            if sym and sym != survivor_sym and sym in self._symbols and sym not in absorbed_syms:
                absorbed_syms.append(sym)
        if not absorbed_syms:
            return []

        survivor_display = self._clean_company_name(
            self._symbol_name_map.get(survivor_sym, "") or survivor_name
        )

        out: list[MergerRecord] = []
        for sym in absorbed_syms:
            absorbed_display = self._clean_company_name(
                self._symbol_name_map.get(sym, "") or sym
            )
            out.append(MergerRecord(
                symbol=sym,
                status="closed",
                display_name=absorbed_display,
                merged_date=merged_date,
                merged_into=survivor_sym,
                merged_into_name=survivor_display,
                surviving_symbol=survivor_sym,
                surviving_name=survivor_display,
                display_mode="closed",
                note=f"{absorbed_display} merged into {survivor_display}.",
                source_url=f"{BASE_URL}/merger-acquisition",
                source_title=f"ShareSansar M&A feed → {survivor_sym}",
            ))
        return out

    def _scrape_ma_feed_records(self) -> list[MergerRecord]:
        """High-fidelity merger records from ShareSansar's M&A DataTable."""
        rows = self._fetch_ma_feed()
        logger.info("M&A feed yielded %s raw rows", len(rows))
        records: list[MergerRecord] = []
        for row in rows:
            records.extend(self._records_from_ma_row(row))
        logger.info("M&A feed produced %s merger records", len(records))
        return records

    def _scrape_merged_companies_page(self, url: str) -> list[MergerRecord]:
        """
        Best-effort parser for ShareSansar's merged-companies listing page.

        The page may be server-rendered or partially hydrated. We only act when
        we can identify a stable row shape with company names and a joint date.
        """
        try:
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Merged-companies page fetch failed for %s: %s", url, exc)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        records: list[MergerRecord] = []

        def emit(absorbed_name: str | None, survivor_name: str | None, joined_date: str | None, action: str = "") -> None:
            if not absorbed_name:
                return
            absorbed_sym = self._symbol_for_company_name(absorbed_name)
            survivor_sym = self._symbol_for_company_name(survivor_name) if survivor_name else None
            if not absorbed_sym:
                return
            records.append(MergerRecord(
                symbol=absorbed_sym,
                status="closed",
                display_name=self._symbol_name_map.get(absorbed_sym) or absorbed_name,
                merged_date=joined_date,
                merged_into=survivor_sym or survivor_name,
                merged_into_name=self._symbol_name_map.get(survivor_sym) or survivor_name,
                surviving_symbol=survivor_sym,
                surviving_name=self._symbol_name_map.get(survivor_sym) or survivor_name,
                display_mode="closed",
                note=f"{absorbed_name} listed as merged on ShareSansar merged-companies page.",
                source_url=url,
                source_title=f"ShareSansar merged companies ({action})".strip(),
            ))
            if survivor_sym:
                records.append(MergerRecord(
                    symbol=survivor_sym,
                    status="active_survivor",
                    display_name=self._symbol_name_map.get(survivor_sym) or survivor_name,
                    merged_date=joined_date,
                    merged_from=absorbed_sym,
                    merged_from_name=self._symbol_name_map.get(absorbed_sym) or absorbed_name,
                    surviving_symbol=survivor_sym,
                    surviving_name=self._symbol_name_map.get(survivor_sym) or survivor_name,
                    display_mode="survivor",
                    note=f"{survivor_name} listed as the surviving merged entity on ShareSansar merged-companies page.",
                    source_url=url,
                    source_title=f"ShareSansar merged companies ({action})".strip(),
                ))

        for table in soup.find_all("table"):
            headers = [self._normalize_text(th.get_text(" ", strip=True)) for th in table.find_all("th")]
            header_map = {h.lower(): i for i, h in enumerate(headers)}
            for tr in table.find_all("tr"):
                cells = [self._normalize_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                if not cells:
                    continue
                row_text = " ".join(cells)
                if not re.search(r"\bmerger\b|\bmerged\b", row_text, re.I):
                    continue

                joined_date = None
                m_date = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", row_text)
                if m_date:
                    joined_date = m_date.group(1)

                absorbed_name = None
                survivor_name = None
                action = ""

                if header_map:
                    def cell_for(*labels: str) -> str | None:
                        for label in labels:
                            idx = header_map.get(label)
                            if idx is not None and idx < len(cells):
                                return cells[idx]
                        return None

                    absorbed_name = cell_for("company name", "name", "merged company")
                    survivor_name = cell_for("company name (after merged)", "company name after merged", "after merged", "merged entity", "new company name")
                    action = cell_for("action") or ""

                if not absorbed_name and cells:
                    absorbed_name = cells[0]
                if not survivor_name and len(cells) > 1:
                    survivor_name = cells[1]
                if len(cells) > 3 and not action:
                    action = cells[3]

                if absorbed_name and survivor_name:
                    emit(absorbed_name, survivor_name, joined_date, action)

        return records

    def _build_richer_merger_index(self, max_pages: int | None = None) -> dict[str, dict]:
        """
        Build a lightweight lookup of symbols -> richer merger metadata from
        the merged-companies page and merger articles.

        This is used to enrich company-page detections that only say "Merged".
        """
        index: dict[str, dict] = {}

        def store(record: MergerRecord) -> None:
            sym = record.symbol.upper()
            current = index.get(sym, {})
            payload = {k: v for k, v in asdict(record).items() if v is not None}
            index[sym] = self._merge_entry(current, payload)

        for rec in self._scrape_merged_companies_page(f"{BASE_URL}/merged-companies"):
            store(rec)

        links = list(dict.fromkeys(KNOWN_SEED_URLS + self._discover_article_links(max_pages=max_pages)))
        for url in links:
            try:
                resp = self._session.get(url, timeout=30)
                resp.raise_for_status()
                title, body = self._extract_title_and_body(resp.text)
                for rec in self._infer_record(title, body, url):
                    store(rec)
            except Exception:
                continue

        return index

    def _title_mentions(self, sym: str, title: str) -> bool:
        """The absorbed ticker (or its company name) must appear in the article
        title — this is the single strongest filter against unrelated tickers
        being matched via body text."""
        if not title:
            return False
        title_up = title.upper()
        if re.search(rf"(?<![A-Z0-9]){re.escape(sym)}(?![A-Z0-9])", title_up):
            return True
        name = self._clean_company_name(self._symbol_name_map.get(sym, ""))
        if self._name_is_matchable(name) and name.upper() in title_up:
            return True
        return False

    def _build_record(
        self,
        absorbed: str,
        survivor_sym: str | None,
        survivor_name_fallback: str | None,
        merger_date: str | None,
        url: str,
        title: str,
    ) -> MergerRecord:
        absorbed_name = self._clean_company_name(self._symbol_name_map.get(absorbed, absorbed))
        survivor_name = self._clean_company_name(
            self._symbol_name_map.get(survivor_sym, "") if survivor_sym else ""
        ) or survivor_name_fallback
        return MergerRecord(
            symbol=absorbed,
            status="closed",
            display_name=absorbed_name or absorbed,
            merged_date=merger_date,
            merged_into=survivor_sym or survivor_name_fallback,
            merged_into_name=survivor_name,
            surviving_symbol=survivor_sym,
            surviving_name=survivor_name,
            display_mode="closed",
            note=f"{absorbed_name or absorbed} merged into {survivor_name or survivor_sym or 'an unknown entity'}.",
            source_url=url,
            source_title=title,
        )

    def _infer_record(self, title: str, body: str, url: str) -> list[MergerRecord]:
        text = f"{title}\n{body}"
        # The title-only check is the strongest guard against false positives,
        # so we filter candidates down to those that actually appear in the
        # article title. Body-only mentions are not enough.
        syms = [sym for sym in self._candidate_symbols(text) if self._title_mentions(sym, title)]
        if not syms:
            return []

        merger_date = None
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if m:
            merger_date = m.group(1)

        survivor_name = None
        m2 = re.search(
            r"(?:joint transaction|integrated transaction|merged entity|continue operating) "
            r"(?:will )?(?:be )?(?:carried out |start |is )?(?:under|in) the name of ([^.]+?)(?:\.|$)",
            text, re.I,
        )
        if m2:
            survivor_name = self._normalize_text(m2.group(1))

        merged_to_name = None
        m3 = re.search(
            r"(?:merged into|acquired by|acquired into|join transaction with|merged with)\s+([^.]+?)(?:\.|$)",
            text, re.I,
        )
        if m3:
            merged_to_name = self._normalize_text(m3.group(1))

        profile_names = self._extract_company_profile_names(text)
        if profile_names and not survivor_name:
            survivor_name = profile_names[-1]

        survivor_sym = (
            self._symbol_for_company_name(survivor_name)
            or self._symbol_for_company_name(merged_to_name)
        )

        strong_merger_lang = re.search(
            r"successful merger|joint transaction|integrated transaction|final merger|merger deal",
            text, re.I,
        )

        if len(syms) >= 2 and strong_merger_lang:
            absorbed = syms[0]
            survivor_final = survivor_sym or syms[-1]
            # absorbed and survivor must be different and both confirmed via title
            if absorbed != survivor_final:
                return [self._build_record(absorbed, survivor_final, survivor_name or merged_to_name, merger_date, url, title)]
            return []

        absorbed = syms[0]
        if re.search(r"merged into|after a successful merger|merged with|stops from today", text, re.I):
            if absorbed == survivor_sym:
                return []
            return [self._build_record(absorbed, survivor_sym, survivor_name or merged_to_name, merger_date, url, title)]
        return []

    def purge_false_positives(self) -> int:
        """Drop registry entries whose only evidence is a newsdetail article
        that doesn't actually mention the symbol or its company name in the
        title. Returns the number of entries removed."""
        registry = self._load_existing_registry()
        entries = registry.get("entries", {})
        survivors_to_keep = {
            rec.get("merged_into") for rec in entries.values()
            if rec.get("status") == "closed" and rec.get("merged_into")
        }
        removed = 0
        for sym in list(entries.keys()):
            rec = entries[sym]
            src_title = rec.get("source_title") or ""
            src_url = rec.get("source_url") or ""
            status = rec.get("status")
            if status == "active_survivor" and sym in survivors_to_keep:
                continue
            # Only audit entries derived from newsdetail-style articles.
            if "/newsdetail/" not in src_url and "/eventdetail/" not in src_url:
                continue
            if not self._title_mentions(sym, src_title):
                del entries[sym]
                removed += 1
        if removed:
            self._save_registry(registry)
        return removed

    def scrape(self, max_pages: int | None = None) -> dict:
        registry = self._load_existing_registry()
        entries = registry.setdefault("entries", {})
        registry["version"] = 1
        richer_index = self._build_richer_merger_index(max_pages=max_pages)

        # The ShareSansar Mergers & Acquisitions DataTable is the only feed
        # that gives us merger_date + survivor reliably, so seed the registry
        # from it first. Later passes only fill gaps via _merge_entry.
        ma_records = self._scrape_ma_feed_records()
        for rec in ma_records:
            symbol = rec.symbol.upper()
            new_entry = {k: v for k, v in asdict(rec).items() if v is not None}
            entries[symbol] = self._merge_entry(entries.get(symbol, {}), new_entry)

        # Scan the full symbol universe so merged companies are discovered
        # automatically from ShareSansar company pages instead of being added
        # by hand one symbol at a time.
        company_page_records = self._scrape_merged_company_pages()
        logger.info("Merged company pages yielded %s record(s)", len(company_page_records))
        for rec in company_page_records:
            symbol = rec.symbol.upper()
            new_entry = {k: v for k, v in asdict(rec).items() if v is not None}
            rich = richer_index.get(symbol, {})
            new_entry = self._merge_entry(new_entry, rich)
            entries[symbol] = self._merge_entry(entries.get(symbol, {}), new_entry)

        merged_page_records = self._scrape_merged_companies_page(f"{BASE_URL}/merged-companies")
        if merged_page_records:
            logger.info("Merged-companies page yielded %s record(s)", len(merged_page_records))
        for rec in merged_page_records:
            if rec.status in {"closed", "active_survivor"}:
                symbol = rec.symbol.upper()
                new_entry = {k: v for k, v in asdict(rec).items() if v is not None}
                rich = richer_index.get(symbol, {})
                new_entry = self._merge_entry(new_entry, rich)
                entries[symbol] = self._merge_entry(entries.get(symbol, {}), new_entry)

        links = list(dict.fromkeys(KNOWN_SEED_URLS + self._discover_article_links(max_pages=max_pages)))
        logger.info("Discovered %s merger-related article links", len(links))

        for i, url in enumerate(links, 1):
            try:
                resp = self._session.get(url, timeout=30)
                resp.raise_for_status()
                title, body = self._extract_title_and_body(resp.text)
                records = self._infer_record(title, body, url)
                if not records:
                    continue
                for rec in records:
                    if rec.status == "closed":
                        symbol = rec.symbol.upper()
                        new_entry = {k: v for k, v in asdict(rec).items() if v is not None}
                        rich = richer_index.get(symbol, {})
                        new_entry = self._merge_entry(new_entry, rich)
                        entries[symbol] = self._merge_entry(entries.get(symbol, {}), new_entry)
                logger.info("[%s/%s] %s -> %s record(s)", i, len(links), url, len(records))
            except Exception as exc:
                logger.warning("Merger scrape failed for %s: %s", url, exc)

        registry["entries"] = {
            sym: rec
            for sym, rec in entries.items()
            if rec.get("status") in {"closed", "active_survivor"}
        }
        self._save_registry(registry)
        return registry


def run_merger_scrape(max_pages: int | None = None) -> dict:
    return ShareSansarMergerScraper().scrape(max_pages=max_pages)

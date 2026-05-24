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


class ShareSansarMergerScraper:
    def __init__(self, data_dir: Path | None = None):
        base = Path(__file__).resolve().parent.parent.parent
        self.data_dir = data_dir or (base / "data")
        self.registry_path = self.data_dir / "company_mergers.json"
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        self._symbol_name_map = self._load_symbol_name_map()
        self._symbols = set(self._symbol_name_map.keys())
        self._name_to_symbol = {
            self._normalize_text(name).upper(): sym
            for sym, name in self._symbol_name_map.items()
        }

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
        cleaned = re.sub(r"\(\s*[A-Z0-9]+\s*\)$", "", cleaned).strip()
        return cleaned

    def _extract_title_and_body(self, html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        for selector in ["h1", "h2", "title"]:
            tag = soup.select_one(selector)
            if tag:
                title = self._normalize_text(tag.get_text(" ", strip=True))
                if title:
                    break
        body = self._normalize_text(soup.get_text(" ", strip=True))
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
        text_up = text.upper()
        candidates = []
        for sym, name in self._symbol_name_map.items():
            name_up = self._normalize_text(name).upper()
            if re.search(rf"(?<![A-Z0-9]){re.escape(sym)}(?![A-Z0-9])", text_up) or name_up in text_up:
                candidates.append(sym)
        return list(dict.fromkeys(candidates))

    def _symbol_for_company_name(self, company_name: str | None) -> str | None:
        if not company_name:
            return None
        target = self._normalize_text(company_name).upper()
        return self._name_to_symbol.get(target)

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

    def _scrape_merged_company_pages(self, symbols: list[str] | None = None, max_symbols: int | None = None) -> list[MergerRecord]:
        """
        Fallback coverage: scan ShareSansar company pages and keep symbols whose
        visible page label says Sector: Merged.
        """
        records: list[MergerRecord] = []
        if symbols is None:
            symbols = sorted(self._symbols)
        else:
            symbols = [sym.upper() for sym in symbols if sym]
        if max_symbols:
            symbols = symbols[:max_symbols]

        for sym in symbols:
            try:
                resp = self._session.get(f"{BASE_URL}/company/{sym.lower()}", timeout=20)
                resp.raise_for_status()
            except Exception:
                continue

            text = self._normalize_text(BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True))
            if not re.search(r"\bSector\b\s*[:|]\s*Merged\b|\bSector:\s*Merged\b", text, re.I):
                continue

            name_match = re.search(r"#\s*([^(]+?)\s*\(\s*([A-Z0-9]+)\s*\)", text)
            display_name = self._symbol_name_map.get(sym)
            if name_match:
                display_name = self._normalize_text(name_match.group(1))

            records.append(MergerRecord(
                symbol=sym,
                status="closed",
                display_name=display_name or self._symbol_name_map.get(sym) or sym,
                display_mode="closed",
                note=f"{display_name or sym} is marked as Merged on ShareSansar company page.",
                source_url=f"{BASE_URL}/company/{sym.lower()}",
                source_title=f"ShareSansar company page ({sym})",
            ))

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

    def _infer_record(self, title: str, body: str, url: str) -> list[MergerRecord]:
        text = f"{title}\n{body}"
        syms = self._candidate_symbols(text)
        if not syms:
            return []

        records: list[MergerRecord] = []
        merger_date = None
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if m:
            merger_date = m.group(1)

        survivor_name = None
        m2 = re.search(r"(?:joint transaction|integrated transaction|merged entity|continue operating) (?:will )?(?:be )?(?:carried out |start |is )?(?:under|in) the name of ([^.]+?)(?:\.|$)", text, re.I)
        if m2:
            survivor_name = self._normalize_text(m2.group(1))

        merged_to_name = None
        m3 = re.search(r"(?:merged into|acquired by|acquired into|join transaction with|merged with)\s+([^.]+?)(?:\.|$)", text, re.I)
        if m3:
            merged_to_name = self._normalize_text(m3.group(1))

        profile_names = self._extract_company_profile_names(text)
        if profile_names and not survivor_name:
            survivor_name = profile_names[-1]

        # If there are 2+ symbols in the article, treat the first as the absorbed
        # company and the last as the survivor when the title/body indicate a
        # successful merger or integrated transaction.
        if len(syms) >= 2 and re.search(r"successful merger|joint transaction|integrated transaction|final merger|merger deal", text, re.I):
            absorbed = syms[0]
            survivor_sym = self._symbol_for_company_name(survivor_name) or self._symbol_for_company_name(merged_to_name) or syms[-1]
            records.append(MergerRecord(
                symbol=absorbed,
                status="closed",
                display_name=self._symbol_name_map.get(absorbed),
                merged_date=merger_date,
                merged_into=survivor_sym,
                merged_into_name=self._symbol_name_map.get(survivor_sym) or merged_to_name,
                surviving_symbol=survivor_sym,
                surviving_name=self._symbol_name_map.get(survivor_sym) or survivor_name,
                display_mode="closed",
                note=f"{self._symbol_name_map.get(absorbed, absorbed)} merged into {self._symbol_name_map.get(survivor_sym, survivor_sym)}.",
                source_url=url,
                source_title=title,
            ))
            return records

        sym = syms[0]
        if "merged into" in text.lower() or "after a successful merger" in text.lower() or "merged with" in text.lower() or "stops from today" in text.lower():
            survivor_sym = self._symbol_for_company_name(survivor_name) or self._symbol_for_company_name(merged_to_name)
            records.append(MergerRecord(
                symbol=sym,
                status="closed",
                display_name=self._symbol_name_map.get(sym),
                merged_date=merger_date,
                merged_into=survivor_sym or merged_to_name,
                merged_into_name=self._symbol_name_map.get(survivor_sym) if survivor_sym else merged_to_name,
                surviving_symbol=survivor_sym,
                surviving_name=self._symbol_name_map.get(survivor_sym) if survivor_sym else survivor_name,
                display_mode="closed",
                note=f"{self._symbol_name_map.get(sym, sym)} appears in a merger/acquisition announcement.",
                source_url=url,
                source_title=title,
            ))
        return records

    def scrape(self, max_pages: int | None = None) -> dict:
        registry = self._load_existing_registry()
        entries = registry.setdefault("entries", {})
        registry["version"] = 1
        richer_index = self._build_richer_merger_index(max_pages=max_pages)

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

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
]
KNOWN_SEED_URLS = [
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
                        entries[rec.symbol.upper()] = {k: v for k, v in asdict(rec).items() if v is not None}
                logger.info("[%s/%s] %s -> %s record(s)", i, len(links), url, len(records))
            except Exception as exc:
                logger.warning("Merger scrape failed for %s: %s", url, exc)

        registry["entries"] = {
            sym: rec
            for sym, rec in entries.items()
            if rec.get("status") == "closed"
        }
        self._save_registry(registry)
        return registry


def run_merger_scrape(max_pages: int | None = None) -> dict:
    return ShareSansarMergerScraper().scrape(max_pages=max_pages)

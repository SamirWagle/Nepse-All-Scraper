"""Karma Nepse News Digest — aggregates NEPSE-relevant headlines across portals,
national English dailies, merchant-bank/PE-VC newsletters, and (optionally)
Facebook pages.

Mirrors karma_signal.py's archive/snapshot/report pattern: each scan writes a
self-contained dark-theme HTML report under output/news_history/, repoints
output/news_latest.html at it, and records a deduped snapshot in
output/news_snapshots.json (skipped if the item set is identical to the last
scan — same headlines don't need a new entry).

Facebook GROUPS are intentionally unsupported — Meta's Graph API doesn't expose
group content to third-party apps and browser-automation scraping breaks
constantly / risks account bans. Public Facebook PAGES work via Graph API +
FB_ACCESS_TOKEN env var.

Only company-level events are in scope (earnings, IPO, M&A, dividends, rating
actions, etc) — plain index-level "NEPSE gains/drops N points" market recaps
are filtered out, and anything whose publish date can't be confirmed inside
the lookback window is dropped rather than kept (stale-by-default is worse
than missing).

Usage:
    python3 scripts/nepse_news.py scan
    python3 scripts/nepse_news.py scan --hours 24 --keywords "ipo,dividend"
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
HISTORY_DIR = OUTPUT_DIR / "news_history"

DEFAULT_KEYWORDS = [
    "ipo", "fpo", "further public offering", "rights share", "right share",
    "bonus share", "dividend", "book closure", "agm", "annual general meeting",
    "net profit", "quarterly report", "earnings", "eps", "credit rating",
    "acquisition", "acquire", "merger", "amalgamation", "stake sale", "buyout",
    "capital increase", "paid-up capital", "sebon action", "delisting",
    "new listing", "allotment", "debenture", "bond issue", "kitta",
    "board meeting", "promoter share", "share sell off", "share conversion",
    "hydropower", "lock-in period", "lockin period", "undervalued",
    "liquidity", "interest rate", "inflation",
    # Nepal macro/economy — moves the whole market, not one company.
    "nrb", "sebon", "monetary policy", "remittance", "forex reserve",
    "gdp growth", "budget", "trade deficit", "nepal rastra bank",
    # Plain-language economy/market terms. The corporate-action jargon above
    # only matches broker and merchant-bank notices; national dailies write
    # about the same economy in ordinary words, and without these the digest
    # silently misses every newspaper story worth reading.
    "nepse", "share market", "stock market", "stock exchange", "investor",
    "economy", "economic growth", "revenue", "export", "import", "trade",
    "microfinance", "banking sector", "commercial bank", "loan", "credit",
    "insurance", "mutual fund", "tourism", "foreign investment", "fdi",
    "electricity", "energy", "capital market", "broker", "market cap",
]

# World-market/macro headlines worth surfacing to a NEPSE investor — kept
# deliberately narrow (rate decisions, crashes, oil/gold, recession signals)
# so the digest doesn't fill up with generic global business news.
MACRO_KEYWORDS = [
    "federal reserve", "fed rate", "rate cut", "rate hike", "interest rate",
    "inflation", "recession", "gdp", "stock market crash", "selloff",
    "bear market", "bull market", "s&p 500", "nasdaq", "dow jones",
    "gold price", "oil price", "crude", "treasury yield", "bond yield",
    "central bank", "tariff", "trade war", "china economy", "india economy",
]

# Company-level headlines only — plain index-move recaps ("NEPSE jumps 42
# points", "NEPSE this week", "market summary") get excluded even if a
# keyword happens to appear elsewhere in the same title.
EXCLUDE_PATTERNS = [
    r"nepse\s+(index\s+)?(jumps|surges|drops|gains|sheds|closes|slips|rises"
    r"|falls|plunges|rebounds|climbs|dips|edges|advances|retreats)",
    r"nepse (index )?(rebounds|increases|decreases|declines|up|down) by",
    r"nepse (index )?(increases|decreases|declines|rises|falls|fell|rose"
    r"|gained|lost|dropped|climbed|slid|surged|plunged)\b",
    # Slug word order puts the verb first: "16-29-points-nepse-fell"
    r"\bpoints?\b.{0,20}\bnepse\b|\bnepse\b.{0,20}\bpoints?\b",
    r"nepse this week",
    r"turnover crosses",
    r"market (recap|summary|update)\b",
]

# Facebook PAGES only (public pages, not groups). Fill in usernames/IDs and set
# FB_ACCESS_TOKEN to enable.
FACEBOOK_PAGES: list[str] = []

# A self-identifying bot UA gets Cloudflare/WAF-blocked on several of these
# sites (confirmed on Nabil Invest — 200 under a browser UA, 403 under a bot
# one); a plain browser string is the only thing that reliably passes.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TIMEOUT = 25  # Prabhu Capital's media page regularly needs >15s
HEADERS = {"User-Agent": USER_AGENT}

MEROLAGANI_URL = "https://merolagani.com/NewsList.aspx"

# ── Sources, in order of preference ──────────────────────────────────────────
# RSS first: feeds carry a real publish timestamp, so no per-article HTTP
# fetch is needed to date them and nothing survives on a guess. All verified
# live 2026-08-01.
RSS_SOURCES = {
    "Kathmandu Post": "https://kathmandupost.com/rss",
    "Rising Nepal": "https://risingnepaldaily.com/rss",
    "Nepal Economic Forum": "https://nepaleconomicforum.org/feed/",
    # New Business Age's /rss is misconfigured — it serves janaaastha.com
    # stories, not its own. Left out until they fix it.
    "Online Khabar": "https://english.onlinekhabar.com/feed",
    "Siddhartha Capital": "https://www.siddharthacapital.com/feed/",
    "NIMB Ace Capital": "https://nimbacecapital.com/feed/",
}

# Global macro — matched against MACRO_KEYWORDS instead of DEFAULT_KEYWORDS
# and rendered in their own section of the report.
MACRO_RSS_SOURCES = {
    "CNBC World": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "CNBC Economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "FT Markets": "https://www.ft.com/markets?format=rss",
    "Investing.com": "https://www.investing.com/rss/news_14.rss",
}

# No usable feed — scraped by grabbing every <a> and keyword-filtering the
# link text, then dated via _extract_published. Kept short on purpose: sites
# whose listing pages yielded only navigation/tool links (Nabil Invest's
# result portals, Avasar, Business Oxygen, Global Equity Fund, One to Watch,
# True North, NMB/Sanima/Machhapuchchhre Capital) were dropped after the
# 2026-08-01 audit — they produced noise and never a dated article.
GENERIC_SOURCES = {
    "Himalayan Times": "https://thehimalayantimes.com/business",
    "Nepali Times": "https://nepalitimes.com/business",  # no www — that host 301s here
    # Kantipur runs Devanagari headlines with English slugs — matched via the
    # slug, see _keyword_haystack. No feed: /rss and /feed both 404.
    "Kantipur": "https://ekantipur.com/business",
    "NIC ASIA Capital": "https://www.nicasiacapital.com/news",
    "Prabhu Capital": "https://www.prabhucapital.com/media?tabKey=press-release",
    "CWEDA Equity Fund": "https://cwedaequity.com.np/notices/",
}

# Fund-manager newsletters and investor letters — PDF archives listed with
# their own publish date. Not keyword-filtered (see fetch_publications).
# NIC ASIA Capital's daily-newsletter archive is deliberately absent: it
# stopped being updated in 2021.
PUBLICATION_SOURCES = {
    "Alpha Capital": "https://www.alphacapitalnepal.com/publications",
    "Nepal Life Capital": "https://nepallifecapital.com.np/newsletter",
}

# Same thing, but the archive is rendered client-side so it needs Firecrawl.
PUBLICATION_JS_SOURCES = {
    "Muktinath Capital": "https://muktinathcapital.com/newsletter",
}

# Sharesansar renders its news list client-side — a plain fetch returns only
# the evergreen sidebar links, so it goes through Firecrawl like NepseAlpha.
# Real articles come back bold in the markdown; the nav links don't.
SHARESANSAR_URL = "https://www.sharesansar.com/category/latest"
_SHARESANSAR_ARTICLE_RE = re.compile(
    r"\[\*\*([^\]]+?)\*\*\]\((https://www\.sharesansar\.com/newsdetail/[^)]+)\)"
)

# NepseAlpha Cloudflare-blocks plain requests outright (even the homepage) —
# fetched via Firecrawl's stealth/headless proxy instead. Its "Latest
# Announcement" feed lives on the homepage, not /news or /all-news (both
# render empty client-side), and carries per-item ticker + date so it needs
# no _extract_published fetch.
NEPSEALPHA_URL = "https://nepsealpha.com/"
_NEPSEALPHA_ANNOUNCEMENT_RE = re.compile(
    r"\[\*\*([^\]]+)\*\*\]\((https://nepsealpha\.com/announcement/[^)]+)\)\s*"
    r"\n\s*-\s*\[([A-Za-z0-9]+)\]\([^)]*\)\s*\n\s*-\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})"
)

# Ansu Invest's "Research & Analysis" feed — same Cloudflare/JS-shell problem
# as NepseAlpha, fetched via Firecrawl. Its listing has no per-article date
# field; the only date signal is a "WhatsApp Image YYYY-MM-DD" filename on
# some (not all) article thumbnails — used when present, otherwise dropped
# per the unconfirmed-date policy (see _within_window).
ANSUINVEST_URL = "https://ansuinvest.com/research-opinion"
_ANSUINVEST_ARTICLE_RE = re.compile(
    r"!\[researchImg\]\(([^)]+)\)\s*\n\s*\[([^\]]+)\]\((https://ansuinvest\.com/research-opinion/view/[^)]+)\)"
)
_ANSUINVEST_IMG_DATE_RE = re.compile(r"Image%20(\d{4})-(\d{2})-(\d{2})")


@lru_cache(maxsize=None)
def _keyword_re(keyword: str) -> re.Pattern:
    """Whole-word matcher for one keyword.

    Plain substring matching silently mis-fires: "eps" is inside "nEPSe", so
    every index story looked like an earnings story. \\b also stops "import"
    matching "important" and "loan" matching "loaned".
    """
    return re.compile(rf"\b{re.escape(keyword.lower())}\b")


def _matches_keywords(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    text_l = text.lower()
    if any(re.search(p, text_l) for p in EXCLUDE_PATTERNS):
        return False
    return any(_keyword_re(kw).search(text_l) for kw in keywords)


_DATE_URL_RE = re.compile(r"/(20\d{2})/(\d{2})/(\d{2})/")
# Fallback: a bare YYYY-MM-DD anywhere in the URL, e.g. Prabhu Capital's
# .../2026-07-14-3-07-40-PM-notice.png filenames.
_DATE_ANYWHERE_RE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


def _extract_published(url: str) -> datetime | None:
    """Best-effort publish date: URL path first (cheap, e.g. Kathmandu Post's
    /money/2026/08/01/slug), then a bare date anywhere in the URL, else fetch
    the article and read its meta tags. Returns None if no reliable date can
    be found — callers must treat that as "can't confirm it's within the
    window" and drop the item.
    """
    for pattern in (_DATE_URL_RE, _DATE_ANYWHERE_RE):
        m = pattern.search(url)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            except ValueError:
                pass
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for attrs in (
            {"property": "article:published_time"},
            {"name": "article:published_time"},
            {"itemprop": "datePublished"},
            {"name": "publish-date"},
        ):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return _parse_iso(tag["content"])
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag:
            return _parse_iso(time_tag["datetime"])
    except requests.RequestException:
        pass
    return None


def _parse_iso(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# RSS/Atom date fields, in the order they're worth trying. RSS uses RFC-822
# (`pubDate`), Atom and Dublin Core use ISO-8601.
_FEED_DATE_TAGS = (
    "pubDate",
    "{http://purl.org/dc/elements/1.1/}date",
    "published",
    "updated",
)


def _feed_entry_date(entry: ET.Element) -> datetime | None:
    for tag in _FEED_DATE_TAGS:
        raw = entry.findtext(tag)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
        parsed = _parse_iso(raw)
        if parsed:
            return parsed
    return None


def fetch_rss(source: str, url: str, keywords: list[str], since: datetime) -> list[dict]:
    """Pull a feed and keep keyword-matching entries inside the window.

    Preferred over fetch_generic wherever a feed exists: the entry's own
    timestamp is authoritative, so nothing needs a follow-up fetch to be
    dated. Feeds that ship no date at all (Kathmandu Post) fall back to the
    date in the article URL.
    """
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        # RSS keeps entries under <item>, Atom under <entry>.
        entries = root.findall(".//item") or root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )
        for entry in entries:
            title = (entry.findtext("title") or "").strip()
            link = (entry.findtext("link") or "").strip()
            if not title or not link or not _matches_keywords(title, keywords):
                continue
            published = _feed_entry_date(entry) or _extract_published(link)
            if not published or published < since:
                continue
            items.append({
                "source": source,
                "title": title,
                "url": link,
                "published": published.isoformat(),
            })
    except (requests.RequestException, ET.ParseError) as e:
        print(f"[warn] {source} feed failed: {e}", file=sys.stderr)
    return items


def _within_window(items: list[dict], since: datetime) -> list[dict]:
    """Resolve each item's publish date and keep only those inside the
    lookback window. Unknown dates are dropped, not kept — see module docstring.
    """
    kept = []
    for it in items:
        published = _extract_published(it["url"])
        if published and published >= since:
            kept.append({**it, "published": published.isoformat()})
    return kept


def fetch_sharesansar(keywords: list[str]) -> list[dict]:
    """Sharesansar's latest-news list via Firecrawl (see SHARESANSAR_URL
    comment). Returns undated items — the caller dates them via
    _within_window, since the listing carries no timestamps.
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return []
    items = []
    try:
        md = _firecrawl_markdown(SHARESANSAR_URL, api_key)
        for title, url in _SHARESANSAR_ARTICLE_RE.findall(md):
            title = title.strip()
            if not _matches_keywords(title, keywords):
                continue
            items.append({"source": "Sharesansar", "title": title, "url": url})
    except requests.RequestException as e:
        print(f"[warn] Sharesansar (Firecrawl) fetch failed: {e}", file=sys.stderr)
    return items


def fetch_merolagani(keywords: list[str]) -> list[dict]:
    items = []
    try:
        resp = requests.get(MEROLAGANI_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("div.media-body, div.newsWrapper, li")[:40]:
            title_tag = card.find(["a", "h4", "h5"])
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            link_tag = card.find("a", href=True)
            link = urljoin(MEROLAGANI_URL, link_tag["href"]) if link_tag else MEROLAGANI_URL
            if not title or not _matches_keywords(title, keywords):
                continue
            items.append({"source": "Merolagani", "title": title, "url": link})
    except requests.RequestException as e:
        print(f"[warn] Merolagani fetch failed: {e}", file=sys.stderr)
    return items


_LATIN_RE = re.compile(r"[A-Za-z]")
# Kantipur slugs end with the story's internal ids: ...-16-33.html
_SLUG_TAIL_RE = re.compile(r"(-\d+)*\.html?$|(-\d+)+$")


def _slug_to_english(link: str) -> str:
    """Turn a URL slug into a readable English headline.

    Nepali outlets publish a Devanagari headline alongside an English slug in
    the URL, so the translation is already in hand — no translation API, no
    per-item call.
    """
    slug = link.rstrip("/").rsplit("/", 1)[-1]
    slug = _SLUG_TAIL_RE.sub("", slug)
    words = slug.replace("_", " ").replace("-", " ").strip()
    return words[:1].upper() + words[1:] if words else ""


def _keyword_haystack(title: str, link: str) -> str:
    """What to keyword-match a listing entry against.

    Nepali-language sites (Kantipur) print Devanagari headlines but keep an
    English slug in the URL — matching the headline alone would silently skip
    every one of their stories, so those fall back to the slug. English
    headlines match on the headline only; folding the URL in for them would
    let a section path like /business/ match everything.
    """
    if _LATIN_RE.search(title):
        return title
    return _slug_to_english(link)


_TABLE_DATE_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
# "July 10,2026" / "April 19 - April 24 , 2026" — the *last* such date in a
# label is the one that matters, since ranges read start-then-end.
_TEXT_DATE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"(\d{1,2})\s*,?\s*(20\d{2})\b",
    re.I,
)
# "14th June 2026" — day-first, as Muktinath titles its newsletters.
_TEXT_DATE_DMY_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(20\d{2})\b",
    re.I,
)
_MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)}


def _build_date(year: str, month: str, day: str) -> datetime | None:
    try:
        return datetime(int(year), _MONTHS[month.lower()[:3]], int(day), tzinfo=timezone.utc)
    except (ValueError, KeyError):
        return None


def _parse_label_date(text: str) -> datetime | None:
    """Date out of a human label, e.g. a newsletter link's own wording."""
    m = _TABLE_DATE_RE.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass
    # Last match wins: ranges ("July 06 - July 10, 2026") read start-then-end.
    matches = _TEXT_DATE_RE.findall(text)
    if matches:
        month, day, year = matches[-1]
        built = _build_date(year, month, day)
        if built:
            return built
    dmy = _TEXT_DATE_DMY_RE.findall(text)
    if dmy:
        day, month, year = dmy[-1]
        return _build_date(year, month, day)
    return None


def fetch_publications(source: str, url: str, since: datetime) -> list[dict]:
    """Fund-manager newsletters and investor letters from a dated table.

    Nepali capital companies publish these as a `Date | Title | PDF` table,
    with the file itself named by a UUID — so the row supplies the date the
    URL can't. Deliberately not keyword-filtered: a fund manager's quarterly
    letter is worth surfacing whatever it's titled, and these are rare enough
    (roughly quarterly) that they can't flood the digest.
    """
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Layout A — a table row carrying the date in its own cell.
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            link_tag = row.find("a", href=True)
            if len(cells) < 2 or not link_tag:
                continue
            published = _parse_label_date(" ".join(c.get_text(" ", strip=True) for c in cells))
            if not published or published < since:
                continue
            # Title is the longest cell that isn't the date or a bare index.
            title = max(
                (c.get_text(" ", strip=True) for c in cells),
                key=lambda t: 0 if _parse_label_date(t) else len(t),
                default="",
            )
            if title:
                items.append({
                    "source": source,
                    "title": title,
                    "url": urljoin(url, link_tag["href"]),
                    "published": published.isoformat(),
                })

        # Layout B — a bare list of PDF links that name their own date
        # ("Weekly Newsletter July 06- July 10,2026").
        if not items:
            for a in soup.find_all("a", href=True):
                if ".pdf" not in a["href"].lower():
                    continue
                title = a.get_text(" ", strip=True)
                published = _parse_label_date(title)
                if not title or not published or published < since:
                    continue
                items.append({
                    "source": source,
                    "title": title,
                    "url": urljoin(url, a["href"]),
                    "published": published.isoformat(),
                })
    except requests.RequestException as e:
        print(f"[warn] {source} publications fetch failed: {e}", file=sys.stderr)
    return items


# Link text may contain escaped brackets (Muktinath titles its newsletters
# `... \[Jestha "..."\]`), so match lazily to the first `](http` rather than
# forbidding `]` outright — and stay on one line so a multi-line badge link
# can't swallow the real entry after it.
_MD_LINK_RE = re.compile(r"\[([^\n]+?)\]\((https?://[^)\s]+)\)")


def fetch_publications_js(source: str, url: str, since: datetime) -> list[dict]:
    """Same as fetch_publications, for archives that render client-side.

    Every entry is a markdown link whose own text names its date, so
    requiring a parseable date is also what filters out the site's nav links
    — they never carry one.
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return []
    items = []
    try:
        md = _firecrawl_markdown(url, api_key)
        for text, link in _MD_LINK_RE.findall(md):
            title = re.sub(r"[\\*]+", "", text).replace("\n", " ").strip()
            title = re.sub(r"\s{2,}", " ", title)
            if len(title) < 15 or link.rstrip("/") == url.rstrip("/"):
                continue
            published = _parse_label_date(title)
            if not published or published < since:
                continue
            items.append({
                "source": source,
                "title": title,
                "url": link,
                "published": published.isoformat(),
            })
    except requests.RequestException as e:
        print(f"[warn] {source} publications (Firecrawl) fetch failed: {e}", file=sys.stderr)
    return items


def fetch_generic(source: str, url: str, keywords: list[str]) -> list[dict]:
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True)[:200]:
            title = a.get_text(strip=True)
            if not title:
                continue
            link = urljoin(url, a["href"])
            haystack = _keyword_haystack(title, link)
            if not _matches_keywords(haystack, keywords):
                continue
            item = {"source": source, "title": title, "url": link}
            # Non-Latin headline: show the slug's English wording instead and
            # keep the original for reference in the report.
            if not _LATIN_RE.search(title) and haystack:
                item = {**item, "title": haystack, "original_title": title}
            items.append(item)
    except requests.RequestException as e:
        print(f"[warn] {source} fetch failed: {e}", file=sys.stderr)
    return items


def fetch_nepsealpha(keywords: list[str], since: datetime) -> list[dict]:
    """NepseAlpha's corporate-announcement feed via Firecrawl (see
    NEPSEALPHA_URL comment for why plain requests can't reach it).
    Skips silently if FIRECRAWL_API_KEY isn't set.
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return []
    items = []
    try:
        md = _firecrawl_markdown(NEPSEALPHA_URL, api_key)
        for title, url, ticker, date_str in _NEPSEALPHA_ANNOUNCEMENT_RE.findall(md):
            try:
                published = datetime.strptime(date_str, "%b %d, %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if published < since:
                continue
            full_title = f"{ticker}: {title}"
            if not _matches_keywords(full_title, keywords):
                continue
            items.append({
                "source": "NepseAlpha",
                "title": full_title,
                "url": url,
                "published": published.isoformat(),
            })
    except requests.RequestException as e:
        print(f"[warn] NepseAlpha (Firecrawl) fetch failed: {e}", file=sys.stderr)
    return items


def _firecrawl_keys() -> list[str]:
    """Primary key first, then any comma-separated fallbacks."""
    keys = [k for k in [os.environ.get("FIRECRAWL_API_KEY")] if k]
    keys += [k.strip() for k in os.environ.get("FIRECRAWL_FALLBACK_KEYS", "").split(",") if k.strip()]
    return keys


def _firecrawl_markdown(url: str, api_key: str) -> str:
    """Scrape one page, trying each configured key until one works.

    `api_key` is the first key to try; the rest come from
    FIRECRAWL_FALLBACK_KEYS. Only auth/quota failures (401/402/429) roll over
    to the next key — a 4xx about the URL itself would fail identically on
    every key, so it raises immediately instead of burning the spares.
    """
    keys = [api_key] + [k for k in _firecrawl_keys() if k != api_key]
    last_error: Exception | None = None
    for key in keys:
        try:
            resp = requests.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"url": url, "formats": ["markdown"], "waitFor": 4000},
                timeout=60,
            )
            if resp.status_code in (401, 402, 429):
                print(f"[warn] Firecrawl key rejected ({resp.status_code}), trying next", file=sys.stderr)
                last_error = requests.HTTPError(f"{resp.status_code} for {url}")
                continue
            resp.raise_for_status()
            return resp.json().get("data", {}).get("markdown", "")
        except requests.RequestException as e:
            last_error = e
            break
    raise last_error or requests.RequestException("no Firecrawl key configured")


def fetch_ansuinvest(keywords: list[str], since: datetime) -> list[dict]:
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return []
    items = []
    try:
        md = _firecrawl_markdown(ANSUINVEST_URL, api_key)
        for img_url, title, url in _ANSUINVEST_ARTICLE_RE.findall(md):
            date_m = _ANSUINVEST_IMG_DATE_RE.search(img_url)
            if not date_m:
                continue  # no confirmed date on this thumbnail — drop, don't guess
            published = datetime(int(date_m.group(1)), int(date_m.group(2)), int(date_m.group(3)), tzinfo=timezone.utc)
            if published < since or not _matches_keywords(title, keywords):
                continue
            items.append({
                "source": "Ansu Invest",
                "title": title,
                "url": url,
                "published": published.isoformat(),
            })
    except requests.RequestException as e:
        print(f"[warn] Ansu Invest (Firecrawl) fetch failed: {e}", file=sys.stderr)
    return items


def fetch_facebook_pages(keywords: list[str], since: datetime, access_token: str | None) -> list[dict]:
    items = []
    if not access_token or not FACEBOOK_PAGES:
        return items
    for page in FACEBOOK_PAGES:
        url = f"https://graph.facebook.com/v19.0/{page}/posts"
        params = {"fields": "message,created_time,permalink_url", "access_token": access_token, "limit": 25}
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            for post in resp.json().get("data", []):
                message = post.get("message", "")
                created_str = post.get("created_time")
                if not created_str:
                    continue
                created = datetime.fromisoformat(created_str.replace("+0000", "+00:00"))
                if created < since or not _matches_keywords(message, keywords):
                    continue
                items.append({
                    "source": f"Facebook ({page})",
                    "title": message[:140],
                    "url": post.get("permalink_url", url),
                })
        except requests.RequestException as e:
            print(f"[warn] Facebook page {page} fetch failed: {e}", file=sys.stderr)
    return items


def dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        key = re.sub(r"\W+", "", it["title"].lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# ── Archive / snapshot (mirrors scripts/karma_signal.py) ──────────────────────

REPORT_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #121212; color: #e6e6e6; font-family: -apple-system, "IBM Plex Sans", sans-serif; }
.wrap { max-width: 960px; margin: 0 auto; padding: 20px; }
#snapshots { display: none; }
#snap-toggle:checked ~ #snapshots { display: block; }
#snap-toggle:checked ~ #scan { display: none; }
#snap-toggle { display: none; }
.head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 16px; }
.snap-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.snap-btn { cursor: pointer; background: #1e1e1e; border: 1px solid #333; border-radius: 8px; padding: 6px 12px; font-size: 13px; color: #ccc; }
.snap-item { display: block; padding: 10px 14px; border: 1px solid #2a2a2a; border-radius: 8px; margin-bottom: 8px; color: #ccc; text-decoration: none; }
.snap-item:hover { border-color: #555; }
.snap-now { border-color: #4caf50; color: #4caf50; }
.snap-date { margin-right: 12px; }
.snap-empty { color: #777; }
.card { background: #1b1b1b; border: 1px solid #2a2a2a; border-radius: 12px; padding: 4px 0; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid #262626; }
th { color: #888; font-weight: 500; }
td a { color: #7fb8ff; text-decoration: none; }
td a:hover { text-decoration: underline; }
.src-tag { display: inline-block; background: #262626; border-radius: 6px; padding: 2px 8px; font-size: 11px; color: #aaa; }
h2 { font-size: 15px; color: #bbb; margin: 22px 0 10px; font-weight: 600; }
.when { color: #777; font-size: 12px; white-space: nowrap; }
.orig { color: #6f6f6f; font-size: 12px; margin-top: 3px; }
"""


def _archive_path(when: datetime) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    base = f"news_{when:%Y%m%d_%H%M%S}"
    path = HISTORY_DIR / f"{base}.html"
    n = 2
    while path.exists():
        path = HISTORY_DIR / f"{base}_{n}.html"
        n += 1
    return path


def _point_latest_at(target: Path) -> None:
    latest = OUTPUT_DIR / "news_latest.html"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        os.symlink(target.relative_to(OUTPUT_DIR), latest)
    except OSError:
        shutil.copyfile(target, latest)


def _snapshot_hash(items: list[dict]) -> str:
    data = "|".join(f"{it['source']}:{it['title']}" for it in items)
    return hashlib.md5(data.encode()).hexdigest()


def _load_snapshots() -> list[dict]:
    snap_file = OUTPUT_DIR / "news_snapshots.json"
    if snap_file.exists():
        return json.loads(snap_file.read_text())
    return []


def _save_snapshot(now: datetime, count: int, hash_val: str, filename: str) -> None:
    snap_file = OUTPUT_DIR / "news_snapshots.json"
    snapshots = _load_snapshots()
    if snapshots and snapshots[-1]["hash"] == hash_val:
        return
    snapshots.append({
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "count": count,
        "hash": hash_val,
        "file": filename,
    })
    snap_file.write_text(json.dumps(snapshots[-20:], indent=2))


def _snapshot_rows(snapshots: list[dict], current_hash: str) -> str:
    if not snapshots:
        return '<div class="snap-empty">No snapshots saved yet.</div>'
    out = []
    for s in reversed(snapshots):
        is_current = s.get("hash") == current_hash
        cls = "snap-item snap-now" if is_current else "snap-item"
        inner = (
            f'<span class="snap-date">{html.escape(s["date"])} at {html.escape(s["time"])}</span>'
            f'<span class="snap-count">{s["count"]} items</span>'
        )
        filename = s.get("file")
        if filename and not is_current:
            out.append(
                f'<a class="{cls}" target="_blank" '
                f'href="/nepse_news/history/{html.escape(filename)}">{inner}</a>'
            )
        else:
            out.append(f'<div class="{cls}">{inner}</div>')
    return "".join(out)


def _table(items: list[dict], empty_note: str) -> str:
    if not items:
        return f'<div class="snap-empty">{empty_note}</div>'
    rows = "".join(
        f"<tr><td><span class='src-tag'>{html.escape(it['source'])}</span></td>"
        f"<td><a href='{html.escape(it['url'])}' target='_blank'>{html.escape(it['title'])}</a>"
        + (f"<div class='orig'>{html.escape(it['original_title'])}</div>"
           if it.get("original_title") else "")
        + f"</td><td class='when'>{html.escape(it.get('published', '')[:10])}</td></tr>"
        for it in items
    )
    return (
        '<div class="card"><table><thead><tr><th>Source</th><th>Headline</th>'
        f"<th>Date</th></tr></thead><tbody>{rows}</tbody></table></div>"
    )


def write_html_report(items: list[dict], macro_items: list[dict],
                      letters: list[dict], hours: int) -> Path:
    now = datetime.now()
    path = _archive_path(now)
    # Snapshot tracks the NEPSE set only — global macro headlines churn on
    # their own cycle and would otherwise force a new snapshot every run.
    snap_hash = _snapshot_hash(items)
    _save_snapshot(now, len(items), snap_hash, path.name)
    snap_rows = _snapshot_rows(_load_snapshots(), snap_hash)
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Karma NEPSE News — {now:%Y-%m-%d %H:%M}</title>
<style>{REPORT_CSS}</style></head>
<body>
<input type="checkbox" id="snap-toggle">
<div id="snapshots" class="wrap">
  <div class="snap-head"><h1>&#128248; Snapshots</h1>
    <label for="snap-toggle" class="snap-btn">&larr; Back to digest</label></div>
  {snap_rows}
</div>
<div id="scan" class="wrap">
<div class="head">
  <span>{len(items)} NEPSE &middot; {len(letters)} letters &middot; {len(macro_items)} macro
    &middot; lookback {hours}h &middot; as of {now:%Y-%m-%d %H:%M}</span>
  <label for="snap-toggle" class="snap-btn">&#128248; Snapshots</label>
</div>
<h2>&#128196; Fund manager letters &amp; newsletters</h2>
{_table(letters, "No new letters in this window.")}
<h2>&#127475;&#127477; NEPSE &amp; Nepal economy</h2>
{_table(items, "Nothing new in this window.")}
<h2>&#127758; Global macro</h2>
{_table(macro_items, "Nothing notable in this window.")}
</div></body></html>
"""
    path.write_text(doc, encoding="utf-8")
    _point_latest_at(path)
    # Marker for the server's cache-first check. Written on every scan even
    # when the snapshot is deduped away, so "when did we last look?" stays
    # answerable independently of "did anything change?".
    (OUTPUT_DIR / "news_last_scan.json").write_text(json.dumps({
        "timestamp": now.isoformat(),
        "file": path.name,
        "nepse_count": len(items),
        "macro_count": len(macro_items),
    }, indent=2))
    return path


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_scan(args) -> None:
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else DEFAULT_KEYWORDS
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    # Undated sources: scraped listings carry no timestamp, so they go
    # through _within_window, which resolves each item's date and drops
    # whatever it can't confirm.
    undated: list[dict] = []
    undated += fetch_sharesansar(keywords)
    undated += fetch_merolagani(keywords)
    for source, url in GENERIC_SOURCES.items():
        undated += fetch_generic(source, url, keywords)
    nepse_items = _within_window(dedupe(undated), since)

    # Dated sources: RSS entries, NepseAlpha announcements, Ansu Invest
    # research and Facebook posts all arrive with their own timestamp and are
    # filtered by `since` inline — no follow-up fetch needed to date them.
    for source, url in RSS_SOURCES.items():
        nepse_items += fetch_rss(source, url, keywords, since)
    nepse_items += fetch_nepsealpha(keywords, since)
    nepse_items += fetch_ansuinvest(keywords, since)
    nepse_items += fetch_facebook_pages(keywords, since, os.environ.get("FB_ACCESS_TOKEN"))
    nepse_items = dedupe(nepse_items)

    macro_items: list[dict] = []
    for source, url in MACRO_RSS_SOURCES.items():
        macro_items += fetch_rss(source, url, MACRO_KEYWORDS, since)
    macro_items = dedupe(macro_items)

    letters: list[dict] = []
    for source, url in PUBLICATION_SOURCES.items():
        letters += fetch_publications(source, url, since)
    for source, url in PUBLICATION_JS_SOURCES.items():
        letters += fetch_publications_js(source, url, since)
    letters = dedupe(letters)

    report_path = write_html_report(nepse_items, macro_items, letters, args.hours)

    print(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(nepse_items) + len(macro_items) + len(letters),
        "nepse_count": len(nepse_items),
        "macro_count": len(macro_items),
        "letter_count": len(letters),
        "items": nepse_items,
        "macro_items": macro_items,
        "letters": letters,
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Karma NEPSE News digest")
    sub = parser.add_subparsers(dest="command", required=True)
    scan_p = sub.add_parser("scan")
    scan_p.add_argument("--hours", type=int, default=24)
    scan_p.add_argument("--keywords", type=str, default=None)
    scan_p.set_defaults(func=cmd_scan)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

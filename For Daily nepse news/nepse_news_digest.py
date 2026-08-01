#!/usr/bin/env python3
"""
nepse_news_digest.py

Standalone NEPSE market news digest builder — designed to be called from
n8n (Execute Command node) or run standalone via cron.

Sources:
  - News portals (Sharesansar, Merolagani) via HTML scraping
  - Reddit (public JSON endpoints, no auth required) — searches configured
    subreddits for NEPSE-related keywords
  - Facebook PAGES only, optional (requires a Graph API access token) —
    NOTE: Facebook GROUPS cannot be scraped. There is no public/ToS-compliant
    way to pull group posts via API, and Meta actively blocks unauthorized
    scraping of groups. If you need group content, the realistic path is
    manually copying posts, or an internal group member exporting them —
    not something a script can do reliably or safely long-term.

Output:
  - Prints a single JSON object to stdout: {"items": [...], "generated_at": ...}
    so n8n can parse it directly downstream (e.g. into an email/Telegram node).
  - Also writes a human-readable markdown digest to OUTPUT_MD.

Usage:
  python3 nepse_news_digest.py
  python3 nepse_news_digest.py --keywords "NEPSE,IPO,rights share" --hours 24

Dependencies:
  pip install requests beautifulsoup4 --break-system-packages
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config — edit these to taste, or override keywords/hours via CLI flags
# ---------------------------------------------------------------------------

DEFAULT_KEYWORDS = [
    "nepse", "share market", "sharesansar", "ipo", "rights share",
    "bonus share", "dividend", "nrb", "sebon", "kitta",
]

# Subreddits to search (public JSON endpoints, no login needed)
REDDIT_SUBREDDITS = ["NepalStock", "Nepal", "NepalFinance"]

# Facebook PAGES only (public pages, not groups). Fill in page IDs/usernames
# you want tracked and set FB_ACCESS_TOKEN via environment variable if used.
FACEBOOK_PAGES = [
    # "sharesansar", "merolagani"  # example usernames — add your own
]

OUTPUT_MD = "nepse_digest.md"
USER_AGENT = "Mozilla/5.0 (compatible; NepseDigestBot/1.0; personal use)"
TIMEOUT = 15

HEADERS = {"User-Agent": USER_AGENT}


# ---------------------------------------------------------------------------
# News portal scrapers
# ---------------------------------------------------------------------------

def fetch_sharesansar(keywords, since):
    """Scrape latest news headlines from Sharesansar's news listing page."""
    items = []
    url = "https://www.sharesansar.com/category/latest"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("div.featured-news, div.news-box, article")[:40]:
            title_tag = card.find(["h2", "h3", "a"])
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            link_tag = card.find("a", href=True)
            link = urljoin(url, link_tag["href"]) if link_tag else url

            if not title or not _matches_keywords(title, keywords):
                continue

            items.append({
                "source": "Sharesansar",
                "title": title,
                "url": link,
                "published": None,  # portal doesn't expose reliable timestamps in listing view
            })
    except requests.RequestException as e:
        print(f"[warn] Sharesansar fetch failed: {e}", file=sys.stderr)
    return items


def fetch_merolagani(keywords, since):
    """Scrape latest news headlines from Merolagani's news listing page."""
    items = []
    url = "https://merolagani.com/NewsList.aspx"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("div.media-body, div.newsWrapper, li")[:40]:
            title_tag = card.find(["a", "h4", "h5"])
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            link_tag = card.find("a", href=True)
            link = urljoin(url, link_tag["href"]) if link_tag else url

            if not title or not _matches_keywords(title, keywords):
                continue

            items.append({
                "source": "Merolagani",
                "title": title,
                "url": link,
                "published": None,
            })
    except requests.RequestException as e:
        print(f"[warn] Merolagani fetch failed: {e}", file=sys.stderr)
    return items


# ---------------------------------------------------------------------------
# Reddit (public JSON endpoints — no API key required)
# ---------------------------------------------------------------------------

def fetch_reddit(keywords, since, subreddits=REDDIT_SUBREDDITS):
    items = []
    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                title = p.get("title", "")
                created = datetime.fromtimestamp(p.get("created_utc", 0), tz=timezone.utc)

                if created < since:
                    continue
                if not _matches_keywords(title, keywords):
                    continue

                items.append({
                    "source": f"Reddit r/{sub}",
                    "title": title,
                    "url": "https://www.reddit.com" + p.get("permalink", ""),
                    "published": created.isoformat(),
                })
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] Reddit r/{sub} fetch failed: {e}", file=sys.stderr)
    return items


# ---------------------------------------------------------------------------
# Facebook PAGES (optional — requires FB_ACCESS_TOKEN env var + Graph API)
# Groups are intentionally NOT supported — see module docstring.
# ---------------------------------------------------------------------------

def fetch_facebook_pages(keywords, since, pages=FACEBOOK_PAGES, access_token=None):
    items = []
    if not access_token or not pages:
        return items  # silently skip if not configured

    for page in pages:
        url = f"https://graph.facebook.com/v19.0/{page}/posts"
        params = {
            "fields": "message,created_time,permalink_url",
            "access_token": access_token,
            "limit": 25,
        }
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            for post in data.get("data", []):
                message = post.get("message", "")
                created_str = post.get("created_time")
                if not created_str:
                    continue
                created = datetime.fromisoformat(created_str.replace("+0000", "+00:00"))
                if created < since:
                    continue
                if not _matches_keywords(message, keywords):
                    continue

                items.append({
                    "source": f"Facebook ({page})",
                    "title": message[:140],
                    "url": post.get("permalink_url", url),
                    "published": created.isoformat(),
                })
        except requests.RequestException as e:
            print(f"[warn] Facebook page {page} fetch failed: {e}", file=sys.stderr)
    return items


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches_keywords(text, keywords):
    text_l = text.lower()
    return any(kw.lower() in text_l for kw in keywords)


def dedupe(items):
    seen = set()
    out = []
    for it in items:
        key = re.sub(r"\W+", "", it["title"].lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def write_markdown(items, path):
    now = datetime.now(timezone.utc)
    lines = [f"# NEPSE News Digest — {now.strftime('%Y-%m-%d %H:%M UTC')}\n"]
    if not items:
        lines.append("_Nothing matched today._\n")
    else:
        by_source = {}
        for it in items:
            by_source.setdefault(it["source"], []).append(it)
        for source, group in by_source.items():
            lines.append(f"## {source}\n")
            for it in group:
                lines.append(f"- [{it['title']}]({it['url']})")
            lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="NEPSE news digest")
    parser.add_argument("--keywords", type=str, default=None,
                         help="Comma-separated keyword override")
    parser.add_argument("--hours", type=int, default=24,
                         help="Lookback window in hours (default 24)")
    parser.add_argument("--fb-token", type=str, default=None,
                         help="Facebook Graph API access token (for FACEBOOK_PAGES only)")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else DEFAULT_KEYWORDS
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    all_items = []
    all_items += fetch_sharesansar(keywords, since)
    all_items += fetch_merolagani(keywords, since)
    all_items += fetch_reddit(keywords, since)
    all_items += fetch_facebook_pages(keywords, since, access_token=args.fb_token)

    all_items = dedupe(all_items)
    write_markdown(all_items, OUTPUT_MD)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": keywords,
        "lookback_hours": args.hours,
        "count": len(all_items),
        "items": all_items,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

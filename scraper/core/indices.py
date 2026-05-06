"""
indices.py
==========
Scrape NEPSE main + sub-index history from sharesansar's /datewise-indices.
Returns a 17-row table per date (4 main + 13 sectoral indices).

Output: data/indices/{INDEX_SLUG}.csv with columns:
  date, current, point_change, percent_change, turnover
"""
from __future__ import annotations

import csv
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

log = logging.getLogger("indices")

ROOT = Path(__file__).resolve().parent.parent.parent
INDICES_DIR = ROOT / "data" / "indices"

ENDPOINT = "https://www.sharesansar.com/datewise-indices"

INDEX_FIELDS = ["date", "current", "point_change", "percent_change", "turnover"]


def slugify_index(name: str) -> str:
    """'Banking SubIndex' -> 'banking', 'NEPSE Index' -> 'nepse'."""
    s = name.lower()
    for noise in ["subindex", "sub index", "sub-index", "index"]:
        s = s.replace(noise, "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        # Without XHR header, sharesansar always returns latest snapshot regardless of `date`.
        "X-Requested-With": "XMLHttpRequest",
        "Referer": ENDPOINT,
    })
    return s


def _parse_num(s):
    return s.replace(",", "").strip()


def fetch_indices_for_date(session, target: date, retries: int = 4):
    """Return list of dicts for one date. Empty if market was closed."""
    url = f"{ENDPOINT}?date={target.isoformat()}"
    last_err = None
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            break
        except requests.exceptions.RequestException as e:
            last_err = e
            log.warning(f"  {target} attempt {attempt+1}/{retries} failed: {e}")
            time.sleep(2 ** attempt)  # 1, 2, 4, 8 sec backoff
    else:
        log.error(f"  {target} giving up after {retries} retries: {last_err}")
        raise last_err
    if resp.status_code != 200:
        return []

    body = resp.text
    tables = re.findall(r"<table[^>]*>(.*?)</table>", body, re.S)
    rows_out = []
    for tbl in tables:
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S):
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.S)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if len(cells) != 5:
                continue
            name, current, point_change, percent_change, turnover = cells
            if name.lower() == "index":  # header
                continue
            rows_out.append({
                "name": name,
                "slug": slugify_index(name),
                "date": target.isoformat(),
                "current":        _parse_num(current),
                "point_change":   _parse_num(point_change),
                "percent_change": _parse_num(percent_change),
                "turnover":       _parse_num(turnover),
            })
    return rows_out


def _read_existing(path: Path):
    if not path.exists():
        return [], set()
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows, {r["date"] for r in rows}


def _write_csv(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def update_indices(start: date | None = None, end: date | None = None, max_misses: int = 90):
    """
    Append new daily index rows to data/indices/{slug}.csv for each index.

    `start` defaults to "day after the last date already saved" (incremental).
    `end` defaults to today.
    `max_misses` aborts the loop after that many consecutive empty days.
    Default 90 covers Dashain+Tihar (~3 weeks) and the 2020 COVID closure (~60 days).
    """
    INDICES_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing dates from any one index file (they all share the same dates).
    existing_dates = set()
    for f in INDICES_DIR.glob("*.csv"):
        with open(f, newline="", encoding="utf-8") as fh:
            existing_dates.update(r["date"] for r in csv.DictReader(fh) if r.get("date"))
        break  # only need one — all files have same date set

    if start is None:
        start = max((date.fromisoformat(d) for d in existing_dates), default=date(2010, 1, 1)) + timedelta(days=1)
    if end is None:
        end = date.today()

    log.info(f"Indices: scrape {start} -> {end}")
    session = _make_session()

    per_slug: dict[str, list[dict]] = {}     # slug -> list of new rows for this run
    name_by_slug: dict[str, str] = {}

    def _checkpoint():
        """Merge accumulated rows into CSVs so a later crash doesn't lose them."""
        for slug, new_rows in per_slug.items():
            out = INDICES_DIR / f"{slug}.csv"
            old, old_dates = _read_existing(out)
            fresh = [r for r in new_rows if r["date"] not in old_dates]
            if not fresh:
                continue
            merged = old + fresh
            merged.sort(key=lambda r: r["date"])
            _write_csv(out, merged)
        per_slug.clear()

    cur = start
    misses = 0
    days_since_ckpt = 0
    try:
        while cur <= end:
            if cur.weekday() >= 5:  # Sat/Sun — NEPSE closed
                cur += timedelta(days=1); continue
            if cur.isoformat() in existing_dates:
                cur += timedelta(days=1); continue

            try:
                rows = fetch_indices_for_date(session, cur)
            except requests.exceptions.RequestException:
                log.warning(f"  {cur} skipped (network error after retries); continuing")
                rows = []
            if rows:
                misses = 0
                for r in rows:
                    per_slug.setdefault(r["slug"], []).append(r)
                    name_by_slug[r["slug"]] = r["name"]
                log.info(f"  {cur} -> {len(rows)} indices")
            else:
                misses += 1
                if misses >= max_misses:
                    log.info(f"  {misses} consecutive empty days; stopping at {cur}")
                    break
            cur += timedelta(days=1)
            days_since_ckpt += 1
            if days_since_ckpt >= 100:
                _checkpoint()
                days_since_ckpt = 0
            time.sleep(0.4)
    finally:
        _checkpoint()

    # Drop a metadata file mapping slug -> human name
    if name_by_slug:
        meta_path = INDICES_DIR / "_index_names.csv"
        old_map: dict[str, str] = {}
        if meta_path.exists():
            with open(meta_path, newline="", encoding="utf-8") as f:
                old_map = {r["slug"]: r["name"] for r in csv.DictReader(f)}
        old_map.update(name_by_slug)
        with open(meta_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["slug", "name"])
            for s in sorted(old_map): w.writerow([s, old_map[s]])

    log.info("Indices: done.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    update_indices()

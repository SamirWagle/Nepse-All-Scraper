"""Scrape full BTC-USD daily history from Yahoo Finance into data/btc/history.csv.

Yahoo's BTC-USD series starts 2014-09-17. Earlier cycles (Bull 1 & 2) are
covered by an approximate monthly seed so the chart can shade 2010-2014.
Run daily via cron; each run rewrites the CSV from a fresh range=max fetch.
"""

import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# range=max silently downgrades to 1mo granularity; explicit periods keep 1d.
YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD"
    "?period1=1279314000&period2={now}&interval=1d"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
OUT_CSV = Path(__file__).resolve().parent.parent / "data" / "btc" / "history.csv"
MIN_EXPECTED_ROWS = 1000

# Approximate monthly closes (USD) pre-Yahoo coverage — log-scale visual only.
PRE_YAHOO_SEED = [
    ("2010-07-31", 0.06), ("2010-08-31", 0.06), ("2010-09-30", 0.06),
    ("2010-10-31", 0.19), ("2010-11-30", 0.25), ("2010-12-31", 0.30),
    ("2011-01-31", 0.45), ("2011-02-28", 0.90), ("2011-03-31", 0.79),
    ("2011-04-30", 3.00), ("2011-05-31", 8.70), ("2011-06-30", 15.40),
    ("2011-07-31", 13.00), ("2011-08-31", 8.20), ("2011-09-30", 5.00),
    ("2011-10-31", 3.20), ("2011-11-30", 3.00), ("2011-12-31", 4.25),
    ("2012-01-31", 5.50), ("2012-02-29", 4.90), ("2012-03-31", 4.90),
    ("2012-04-30", 4.90), ("2012-05-31", 5.10), ("2012-06-30", 6.70),
    ("2012-07-31", 9.40), ("2012-08-31", 10.00), ("2012-09-30", 12.40),
    ("2012-10-31", 11.20), ("2012-11-30", 12.60), ("2012-12-31", 13.50),
    ("2013-01-31", 20.40), ("2013-02-28", 33.40), ("2013-03-31", 93.00),
    ("2013-04-30", 139.00), ("2013-05-31", 128.00), ("2013-06-30", 97.00),
    ("2013-07-31", 106.00), ("2013-08-31", 141.00), ("2013-09-30", 141.00),
    ("2013-10-31", 204.00), ("2013-11-30", 1130.00), ("2013-12-31", 754.00),
    ("2014-01-31", 800.00), ("2014-02-28", 550.00), ("2014-03-31", 458.00),
    ("2014-04-30", 445.00), ("2014-05-31", 628.00), ("2014-06-30", 640.00),
    ("2014-07-31", 583.00), ("2014-08-31", 478.00),
]


def fetch_yahoo_rows():
    """Return [(iso_date, close), ...] from Yahoo's chart API."""
    resp = requests.get(YAHOO_URL.format(now=int(time.time())), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    result = payload.get("chart", {}).get("result")
    if not result:
        err = payload.get("chart", {}).get("error")
        raise RuntimeError(f"Yahoo returned no result: {err}")
    timestamps = result[0].get("timestamp") or []
    closes = result[0]["indicators"]["quote"][0].get("close") or []
    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((day, round(float(close), 2)))
    if len(rows) < MIN_EXPECTED_ROWS:
        raise RuntimeError(f"Suspiciously few rows from Yahoo: {len(rows)}")
    return rows


def merge_rows(yahoo_rows):
    """Seed rows before Yahoo coverage + Yahoo rows, deduped by date, sorted."""
    first_yahoo = yahoo_rows[0][0]
    merged = {d: c for d, c in PRE_YAHOO_SEED if d < first_yahoo}
    merged.update(dict(yahoo_rows))
    return sorted(merged.items())


def write_csv(rows, out_path=OUT_CSV):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "close"])
        writer.writerows(rows)
    tmp.replace(out_path)


def main():
    rows = merge_rows(fetch_yahoo_rows())
    write_csv(rows)
    print(f"[btc_scraper] wrote {len(rows)} rows -> {OUT_CSV} (last: {rows[-1]})")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"[btc_scraper] FAILED: {ex}", file=sys.stderr)
        sys.exit(1)

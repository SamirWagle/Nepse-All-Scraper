"""One-off full-universe fundamentals refresh (all data/companies.csv symbols)."""
import csv
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.core.fundamentals import MerolaganiFundamentalsScraper

logging.basicConfig(level=logging.WARNING)

BASE = Path(__file__).resolve().parent.parent
symbols = [row["symbol"] for row in csv.DictReader(open(BASE / "data" / "companies.csv"))]
force = "--force" in sys.argv

scraper = MerolaganiFundamentalsScraper()
ok, failed = 0, []
for i, sym in enumerate(symbols, 1):
    try:
        data = scraper.get(sym, force_refresh=force)
        if "error" in data:
            failed.append(sym)
        else:
            ok += 1
        print(f"[{i}/{len(symbols)}] {sym}: pbv={data.get('pbv')}")
    except Exception as exc:
        failed.append(sym)
        print(f"[{i}/{len(symbols)}] {sym}: FAILED {exc}")
    time.sleep(0.8)

print(f"\nDone. ok={ok} failed={len(failed)}")
if failed:
    print("Failed symbols:", ", ".join(failed))

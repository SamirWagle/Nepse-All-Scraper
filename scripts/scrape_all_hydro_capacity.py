"""Full hydropower-sector installed-capacity (MW) refresh from Chukul.

Incremental by default (respects 30-day cache) — pass --force to refetch everything.
"""
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.core.hydro_capacity import ChukulCapacityScraper

logging.basicConfig(level=logging.WARNING)

BASE = Path(__file__).resolve().parent.parent
COMPANY_DIR = BASE / "data" / "company-wise"

symbols = []
for fundamentals_path in COMPANY_DIR.glob("*/fundamentals.json"):
    try:
        data = json.loads(fundamentals_path.read_text())
    except (json.JSONDecodeError, OSError):
        continue
    if (data.get("sector") or "").strip().lower() == "hydro power":
        symbols.append(data["symbol"])
symbols.sort()

force = "--force" in sys.argv

scraper = ChukulCapacityScraper()
ok, failed = 0, []
for i, sym in enumerate(symbols, 1):
    try:
        result = scraper.get(sym, force_refresh=force)
        if "error" in result:
            failed.append(sym)
        else:
            ok += 1
        print(f"[{i}/{len(symbols)}] {sym}: capacity_mw={result.get('capacity_mw')}")
    except Exception as exc:
        failed.append(sym)
        print(f"[{i}/{len(symbols)}] {sym}: FAILED {exc}")
    time.sleep(0.5)

print(f"\nDone. ok={ok} failed={len(failed)}")
if failed:
    print("Failed symbols:", ", ".join(failed))

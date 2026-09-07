#!/usr/bin/env python3
"""Precompute the NEPSE Bubbles data as static JSON for the public site.

The extension's bubbles page asks the local engine (localhost:5758) to compute
returns on demand, which a shared website obviously can't do. Every period is
cheap to compute ahead of time though — 75 companies each — so this writes one
JSON per period into docs/data/ and GitHub Pages serves them as plain files.
No server, no API keys, nothing to keep running.

Run after the nightly scrape so the site reflects the latest session:
  python3 scripts/build_bubbles_site.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from nepse_cagr_server import (  # noqa: E402
    BUBBLE_PERIOD_DAYS,
    get_bubbles_data,
    get_bubbles_mc_data,
)

OUT_DIR = REPO / "docs" / "data"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periods": [],
    }

    for period in list(BUBBLE_PERIOD_DAYS) + ["mc"]:
        rows = get_bubbles_mc_data() if period == "mc" else get_bubbles_data(period)
        payload = {"period": period, "data": rows}
        (OUT_DIR / f"bubbles_{period}.json").write_text(json.dumps(payload, separators=(",", ":")))

        manifest["periods"].append(period)
        # Every row carries the same session date; surface it so the page can
        # say how fresh it is rather than implying it's live.
        if rows and not manifest.get("last_session"):
            manifest["last_session"] = rows[0].get("last_date")
        print(f"  {period:>4}: {len(rows):3} companies", flush=True)

    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote {len(manifest['periods'])} files to {OUT_DIR}")
    print(f"Last session in data: {manifest.get('last_session')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

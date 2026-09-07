#!/usr/bin/env python3
"""Pick which year the nightly floorsheet backfill should work on next.

Walks backward from 2025 (2026 was filled manually) looking for the most
recent year that isn't fully covered yet, and prints the --since date the
nightly job should hand to backfill_floorsheet.py for that year. Printing
nothing (exit code 0) means every year back to the index's earliest data is
done — the nightly job checks for that and skips launching workers.

One year per night by design: each year is ~225 trading days and the site
only sustains 3 concurrent crawlers cleanly (see backfill_floorsheet.py), so
one year already runs most of the night. Running it as "walk backward from
2025" rather than a fixed list also makes it self-terminating.

There is no hardcoded floor date. Individual days as far back as 2015-2016
return zero rows with no visible pattern to it (2015-07-01 works, 2015-08-01
doesn't, 2015-09-01 works again) — this isn't a clean "no data before date X"
cutoff, so picking one would either stop early or retry unreachable days
forever. backfill_floorsheet.py handles that instead: a day still empty after
retries gets a .nodata marker, which already_have() treats as resolved. So
"a year is done" here genuinely means every trading day in it now has either
a CSV or a confirmed-empty marker — the walk goes all the way back to the
oldest year in our own index history (2011), not a guess about the source.
"""

import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd  # noqa: E402
from backfill_floorsheet import already_have, INDEX_HISTORY  # noqa: E402

START_YEAR = 2025  # 2026 was already backfilled by hand before this existed


def earliest_index_year() -> int:
    df = pd.read_csv(INDEX_HISTORY, parse_dates=["date"])
    return int(df["date"].min().year)


def year_trading_days(year: int) -> list:
    df = pd.read_csv(INDEX_HISTORY, parse_dates=["date"])
    lo, hi = date(year, 1, 1), date(year, 12, 31)
    return sorted({d.date() for d in df["date"] if lo <= d.date() <= hi})


def main() -> int:
    have = already_have()
    floor_year = earliest_index_year()
    for year in range(START_YEAR, floor_year - 1, -1):
        days = year_trading_days(year)
        missing = [d for d in days if d not in have]
        if missing:
            print(date(year, 1, 1).isoformat())
            return 0
    return 0  # every year back to the index's earliest data is complete


if __name__ == "__main__":
    sys.exit(main())

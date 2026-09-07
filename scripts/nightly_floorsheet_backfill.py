#!/usr/bin/env python3
"""Nightly floorsheet backfill: one year per night, walking backward from 2025.

2026 was backfilled by hand (3 workers, ~5h). Doing every prior year in one
sitting would be ~15h/year with no natural stopping point, so this runs one
year per night instead — 2025 tonight, 2024 the next, 2023 the one after,
down to the source's floor (2022-05-10) — then keeps firing harmlessly (a few
seconds) once there's nothing left, since backfill_floorsheet_year_picker.py's
own year range is what determines when to stop.

launchd (not cron) fires this at 23:30 daily, so a run interrupted by sleep
resumes on wake. A run takes up to ~15h — still going when the next night's
23:30 arrives — so this holds an flock for its lifetime rather than trusting
launchd to skip an overlapping fire on its own.
"""

import fcntl
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def main() -> int:
    lock_path = REPO / ".floorsheet_backfill.lock"
    lock = open(lock_path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("Floorsheet backfill: previous run still going — skipping tonight.")
        return 0

    picker = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "backfill_floorsheet_year_picker.py")],
        capture_output=True, text=True, check=True,
    )
    since = picker.stdout.strip()

    if not since:
        log("Floorsheet backfill: nothing left back to the source floor. Done.")
        return 0

    log(f"Floorsheet backfill: starting from {since} (3 workers)")
    workers = [
        subprocess.Popen([
            sys.executable, str(REPO / "scripts" / "backfill_floorsheet.py"),
            "--since", since, "--workers", "3", "--worker-id", str(i),
        ])
        for i in range(3)
    ]
    for w in workers:
        w.wait()

    log("Floorsheet backfill: night's run finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

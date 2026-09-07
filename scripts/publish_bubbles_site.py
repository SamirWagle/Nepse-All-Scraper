#!/usr/bin/env python3
"""Rebuild the public NEPSE Bubbles data and push it to GitHub Pages.

Runs at the end of the nightly scrape: regenerate docs/data/*.json from the
freshly scraped prices, then commit and push just that directory. GitHub Pages
redeploys on its own from the push, so there's nothing to deploy or restart.

Deliberately narrow: it only ever stages docs/, so an unrelated work-in-progress
in the working tree can't be swept into an automated commit. A push that fails
(remote moved on) is logged and left alone rather than force-resolved — the
17:15 `git pull` cron reconciles it and the next night's push carries both.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def git(*args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=check)


def main() -> int:
    build = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_bubbles_site.py")],
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        print("WARNING: bubbles site build failed; site left at previous data.")
        print(build.stdout[-2000:])
        print(build.stderr[-2000:])
        return 1
    print(build.stdout.strip().splitlines()[-1] if build.stdout.strip() else "built")

    # manifest.json carries a build timestamp, so it changes on every run even
    # when no price moved — committing on that alone would put a meaningless
    # commit in the history every night, holidays included. Publish only when
    # actual bubble data changed, and drop the timestamp-only churn.
    changed = [
        line[3:] for line in git("status", "--porcelain", "docs").stdout.splitlines() if line[3:]
    ]
    if not any(not p.endswith("manifest.json") for p in changed):
        git("checkout", "--", "docs/data/manifest.json", check=False)
        print("Bubbles site: data unchanged, nothing to publish.")
        return 0

    git("add", "docs")
    git("commit", "-m", "chore: refresh NEPSE Bubbles site data")
    push = git("push", "origin", "HEAD:main", check=False)
    if push.returncode != 0:
        print("WARNING: bubbles site push failed (commit is local, will retry next run):")
        print(push.stderr.strip()[-500:])
        return 1

    print("Bubbles site: published to https://karmataklu-bot.github.io/Nepse-CAGR/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

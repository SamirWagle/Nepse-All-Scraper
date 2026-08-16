#!/usr/bin/env python3
"""
Build one ticker's DATA.prices[SYM] + DATA.meta[SYM] JSON block for the
"NEPSE Ticker Cycles" artifact (claude.ai/code/artifact/ce245072-fd44-42e5-a7fc-b6239aac6a2d).

Reuses nepse_cagr.py's own CSV loaders (load_prices, load_dividends,
load_right_shares) so the artifact's numbers always match the CLI's.

Usage:
    python3 scripts/ticker_cycles_entry.py SBI

Output: one JSON object on stdout —
    {"prices": {"dates": [...], "prices": [...]},
     "meta": {"name": ..., "bonusEvents": [[date, pct], ...],
               "hasRights": bool, "dividendEvents": [[date, bonusPct, cashPct], ...]}}

hasRights is informational only (drives a text note in the artifact) — the
artifact does not yet do rights-share unit/price adjustment math.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nepse_cagr import load_prices, load_dividends, load_right_shares  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def company_name(symbol: str) -> str:
    names_path = DATA_DIR / "company_names.json"
    if names_path.exists():
        names = json.loads(names_path.read_text())
        if symbol in names:
            raw = names[symbol]
            # Collapse "Name (\n   SYM )" whitespace artifacts down to "Name"
            name = raw.split("(")[0].strip()
            return name or raw.strip()
    return symbol


def build(symbol: str) -> dict:
    symbol = symbol.upper()
    prices_df = load_prices(symbol, DATA_DIR)
    dividends_df = load_dividends(symbol, DATA_DIR)
    rights_df = load_right_shares(symbol, DATA_DIR)

    dates = [d.strftime("%Y-%m-%d") for d in prices_df["date"]]
    prices = [round(float(p), 2) for p in prices_df["close"]]

    bonus_events, dividend_events = [], []
    for _, row in dividends_df.iterrows():
        if row["book_closure_date"] is None or row["book_closure_date"] != row["book_closure_date"]:
            continue
        iso_date = row["book_closure_date"].strftime("%Y-%m-%d")
        bonus_pct = round(float(row.get("bonus_share", 0) or 0) * 100, 4)
        cash_pct = round(float(row.get("cash_dividend", 0) or 0) * 100, 4)
        if bonus_pct > 0:
            bonus_events.append([iso_date, bonus_pct])
        if bonus_pct > 0 or cash_pct > 0:
            dividend_events.append([iso_date, bonus_pct, cash_pct])

    # newest first, matching HDL's existing ordering in the artifact
    bonus_events.sort(key=lambda e: e[0], reverse=True)
    dividend_events.sort(key=lambda e: e[0], reverse=True)

    has_rights = not rights_df.empty

    return {
        "prices": {"dates": dates, "prices": prices},
        "meta": {
            "name": company_name(symbol),
            "bonusEvents": bonus_events,
            "hasRights": has_rights,
            "dividendEvents": dividend_events,
        },
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 scripts/ticker_cycles_entry.py TICKER")
    print(json.dumps(build(sys.argv[1]), separators=(",", ":")))

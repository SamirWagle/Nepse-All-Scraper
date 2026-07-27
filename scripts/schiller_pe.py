#!/usr/bin/env python3
"""Shiller PE (CAPE) + historical PE band for a NEPSE company.

Usage: python3 scripts/schiller_pe.py TICKER [--years N]

Reads data/company-wise/{TICKER}/eps_history.csv and prices.csv.
Historical PE = price on the trading day nearest each fiscal year-end (mid-July)
divided by that fiscal year's EPS.
"""
import argparse
import csv
import json
import statistics
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "company-wise"


def bs_end_year_to_ad(fiscal_year: str) -> int:
    """076-077 -> mid-July 2020 (BS end year 077 -> AD 2020)."""
    end_bs = int(fiscal_year.split("-")[1])
    return end_bs + 1943


def load_eps_history(symbol: str) -> list[tuple[str, float]]:
    path = DATA_DIR / symbol / "eps_history.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        rows = [(r["fiscal_year"], float(r["eps"])) for r in csv.DictReader(f) if r["eps"]]
    rows.sort(key=lambda r: r[0])
    return rows


def load_prices(symbol: str) -> list[tuple[date, float]]:
    path = DATA_DIR / symbol / "prices.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        rows = [
            (date.fromisoformat(r["date"]), float(r["ltp"]))
            for r in csv.DictReader(f)
            if r.get("ltp")
        ]
    rows.sort(key=lambda r: r[0])
    return rows


def current_price(symbol: str) -> float | None:
    """Prefer fundamentals.json's live-scraped market_price (refreshed independently
    of prices.csv, which only updates on the scraper's EOD cadence and can lag by
    several trading days). Falls back to prices.csv's last row if unavailable."""
    fundamentals_path = DATA_DIR / symbol / "fundamentals.json"
    if fundamentals_path.exists():
        try:
            data = json.loads(fundamentals_path.read_text())
            if data.get("market_price"):
                return float(data["market_price"])
        except (json.JSONDecodeError, ValueError):
            pass
    prices = load_prices(symbol)
    return prices[-1][1] if prices else None


def nearest_price(prices: list[tuple[date, float]], target: date) -> float | None:
    if not prices:
        return None
    best = min(prices, key=lambda p: abs((p[0] - target).days))
    if abs((best[0] - target).days) > 45:
        return None
    return best[1]


def historical_pe_series(symbol: str) -> list[dict]:
    eps_rows = load_eps_history(symbol)
    prices = load_prices(symbol)
    out = []
    for fy, eps in eps_rows:
        if eps <= 0:
            continue
        target = date(bs_end_year_to_ad(fy), 7, 16)
        price = nearest_price(prices, target)
        if price is None:
            continue
        out.append({"fiscal_year": fy, "price": price, "eps": eps, "pe": round(price / eps, 2)})
    return out


def shiller_pe(symbol: str, years: int = 10) -> dict | None:
    eps_rows = load_eps_history(symbol)
    price = current_price(symbol)
    if not eps_rows or not price:
        return None
    recent = [eps for _, eps in eps_rows[-years:]]
    avg_eps = sum(recent) / len(recent)
    if avg_eps <= 0:
        return None
    return {
        "current_price": price,
        "avg_eps": round(avg_eps, 2),
        "years": len(recent),
        "shiller_pe": round(price / avg_eps, 2),
    }


def present_pe(symbol: str) -> dict | None:
    eps_rows = load_eps_history(symbol)
    price = current_price(symbol)
    if not eps_rows or not price:
        return None
    fy, eps = eps_rows[-1]
    if eps <= 0:
        return None
    return {"fiscal_year": fy, "eps": eps, "current_price": price, "pe": round(price / eps, 2)}


PE_OUTLIER_CAP = 100  # near-zero-EPS years (mergers, writeoffs) distort avg/median; excluded from stats


def summarize(symbol: str, years: int = 10) -> dict:
    hist = historical_pe_series(symbol)
    hist_pes = [h["pe"] for h in hist if h["pe"] <= PE_OUTLIER_CAP]
    return {
        "symbol": symbol,
        "present_pe": present_pe(symbol),
        "shiller_pe": shiller_pe(symbol, years),
        "historical_pe_series": hist,
        "historical_pe_avg": round(statistics.mean(hist_pes), 2) if hist_pes else None,
        "historical_pe_median": round(statistics.median(hist_pes), 2) if hist_pes else None,
        "historical_pe_min": round(min(hist_pes), 2) if hist_pes else None,
        "historical_pe_max": round(max(hist_pes), 2) if hist_pes else None,
        "historical_pe_excluded_outliers": len(hist) - len(hist_pes),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--years", type=int, default=10)
    args = parser.parse_args()

    result = summarize(args.symbol.upper(), args.years)
    print(f"\n=== {result['symbol']} ===")
    print(f"Present PE:  {result['present_pe']}")
    print(f"Shiller PE:  {result['shiller_pe']}")
    print(f"Historical PE  avg={result['historical_pe_avg']}  median={result['historical_pe_median']}  "
          f"min={result['historical_pe_min']}  max={result['historical_pe_max']}  "
          f"(n={len(result['historical_pe_series'])} years)")
    print("\nFY-by-FY:")
    for h in result["historical_pe_series"]:
        print(f"  {h['fiscal_year']}: price={h['price']}  eps={h['eps']}  pe={h['pe']}")

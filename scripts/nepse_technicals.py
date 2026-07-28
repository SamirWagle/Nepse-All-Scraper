#!/usr/bin/env python3
"""MA(50/200), RSI(14), support/resistance from local prices.csv. No external feed."""
import csv
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "company-wise"


def load_closes(ticker: str) -> list[float]:
    path = DATA_DIR / ticker / "prices.csv"
    if not path.exists():
        raise FileNotFoundError(f"No prices.csv for {ticker} at {path}")
    with path.open() as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r["date"])  # oldest -> newest
    return [float(r["ltp"]) for r in rows if r["ltp"]]


def sma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def rsi(closes: list[float], window: int = 14) -> float | None:
    if len(closes) < window + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(-window, 0)]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def support_resistance(closes: list[float], window: int = 60) -> tuple[float, float]:
    recent = closes[-window:] if len(closes) >= window else closes
    return min(recent), max(recent)


def analyse(ticker: str) -> dict:
    closes = load_closes(ticker)
    if not closes:
        raise ValueError(f"No price data for {ticker}")
    support, resistance = support_resistance(closes)
    return {
        "ticker": ticker,
        "last_price": closes[-1],
        "ma50": sma(closes, 50),
        "ma200": sma(closes, 200),
        "rsi14": rsi(closes),
        "support_60d": support,
        "resistance_60d": resistance,
        "n_days": len(closes),
    }


def demo():
    # ponytail: smoke test only, needs a ticker with local price history
    sample = next((d.name for d in DATA_DIR.iterdir() if (d / "prices.csv").exists()), None)
    if not sample:
        print("no local ticker data found, skipping demo")
        return
    result = analyse(sample)
    assert result["last_price"] > 0
    assert result["n_days"] > 0
    print(f"demo ok: {sample} -> {result}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        demo()
    else:
        import json

        print(json.dumps(analyse(sys.argv[1].upper()), indent=2))

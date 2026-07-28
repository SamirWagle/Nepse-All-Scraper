"""Karma Nepse Trading Signal — technical swing signal for NEPSE.

Horizon: 2 weeks minimum, 3 months maximum. Long-only (NEPSE has no shorting).

Two modes:
  scan      — rank today's BUY candidates across all tickers
  backtest  — measure the actual hit rate of the rules on history

The backtest exists because a signal's win rate is a measured number, not a
claimed one. Every accuracy statement about this signal must come from
`backtest`, run on the target/stop pair actually being used.

Prices are backward-adjusted for bonus shares and right shares. Unadjusted
NEPSE series gap down 20-50% on ex-bonus dates, which fabricates stop-outs
and destroys any backtest built on them.

Usage:
    python3 scripts/karma_signal.py scan
    python3 scripts/karma_signal.py scan --top 20
    python3 scripts/karma_signal.py signal NABIL
    python3 scripts/karma_signal.py backtest
    python3 scripts/karma_signal.py backtest --target 0.25 --stop 0.10
    python3 scripts/karma_signal.py backtest --grid
    python3 scripts/karma_signal.py selftest
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COMPANY_DIR = DATA_DIR / "company-wise"
NEPSE_INDEX = DATA_DIR / "index" / "nepse" / "history.csv"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
HISTORY_DIR = OUTPUT_DIR / "history"

# ── Tunables ─────────────────────────────────────────────────────────────────
MIN_MEDIAN_TURNOVER = 2_000_000.0  # NPR/day over 60d — exit liquidity floor
MIN_HISTORY_DAYS = 260             # need a year+ for MA200 and 52w high
MAX_EXTENSION = 1.20               # close vs MA20 — don't chase a circuit run
MAX_STALE_DAYS = 15                # a scan candidate must have traded recently

# ── Transaction costs ────────────────────────────────────────────────────────
# NEPSE round trip: broker commission both sides + SEBON fee + DP charge, then
# capital-gains tax on the profit. Every trade this signal produces is held
# under 365 days, so the short-term individual CGT rate applies — the long-term
# 5% rate is unreachable inside a 3-month mandate.
BROKER_COMMISSION = 0.0031   # ~0.31% per side, mid-tier slab
SEBON_FEE = 0.00015          # per side
DP_CHARGE = 25.0             # NPR flat, per side, per script
DEFAULT_POSITION = 100_000.0  # NPR — only used to express DP charge as a %
SHORT_TERM_CGT = 0.075       # individuals, holding < 365 days
LONG_TERM_CGT = 0.05         # individuals, holding >= 365 days — buy-and-hold only
TRADING_DAYS_PER_YEAR = 240  # NEPSE: Sun-Thu, minus public holidays


def net_return(gross: float, position_size: float = DEFAULT_POSITION) -> float:
    """Gross return -> after commission, fees, and CGT on any profit.

    Applied to the return, not the price, so it composes with any target/stop.
    """
    round_trip = 2 * (BROKER_COMMISSION + SEBON_FEE) + 2 * DP_CHARGE / position_size
    after_fees = gross - round_trip
    return after_fees * (1 - SHORT_TERM_CGT) if after_fees > 0 else after_fees


def buy_hold_net(gross: float, position_size: float = DEFAULT_POSITION) -> float:
    """Same costs, but paid once and taxed at the long-term rate.

    Buy-and-hold is not cost-free, and comparing a net strategy to a gross
    benchmark flatters the strategy. It is, however, genuinely cheaper: one
    round trip instead of dozens, and 5% CGT instead of 7.5%.
    """
    round_trip = 2 * (BROKER_COMMISSION + SEBON_FEE) + 2 * DP_CHARGE / position_size
    after_fees = gross - round_trip
    return after_fees * (1 - LONG_TERM_CGT) if after_fees > 0 else after_fees
RSI_CEILING = 75.0
VOL_EXPANSION = 1.3                # 20d avg qty vs 60d avg qty
BUY_SCORE = 70                     # score >= this = BUY


@dataclass(frozen=True)
class Mode:
    """Swing and position differ in hold length, so every level scales with it.

    A 40% target on a 2-week hold and a 40% target on a 3-month hold are not
    the same bet — the shorter one demands a move the market rarely delivers
    in that window. Targets and stops are sized to the horizon, not copied
    across it.
    """

    name: str
    min_hold: int      # trading days — no exit before this
    max_hold: int      # trading days — time stop
    target: float      # reference only; the default exit is the trailing stop
    stop: float
    atr_mult: float    # initial stop floor in ATRs
    trail_atr: float   # ratcheting stop distance in ATRs
    near_high: float   # min fraction of the 250-day high
    adx_floor: float


MODES = {
    # 2 weeks to ~6 weeks. Breakout continuation, tight stop.
    "swing": Mode("swing", 10, 30, 0.18, 0.08, 1.5, 2.0, 0.92, 22.0),
    # ~1 to 3 months. Rides an established trend, wider stop for the noise.
    "position": Mode("position", 20, 63, 0.40, 0.12, 2.5, 2.0, 0.85, 20.0),
}
DEFAULT_MODE = "position"

# The winners are the whole edge here: the median trade loses and the mean
# trade wins. A fixed profit target truncates exactly the outcomes that pay
# for the losses, so the default exit is an uncapped trailing stop. Measured
# out-of-sample, trailing roughly doubles net return per trade in both modes.
DEFAULT_EXIT = "trail"

# Measured out-of-sample (entries from 2023-01-01, trailing exit, net of costs
# and CGT). Refresh with `backtest --mode both` after any rule change.
#
# These are BASE RATES for the mode, not per-stock forecasts. Nothing measured
# here predicts which name does better — the `tiers` test showed the signal
# score has no monotonic relationship to outcome. A per-ticker probability
# would therefore be invented, so `scan` prints the same odds against every
# row and the only column that genuinely varies by stock is the reward:risk
# its own ATR-derived stop implies.
MEASURED_ODDS = {
    "swing": {"p_win": 0.408, "avg_win": 0.1234, "avg_loss": 0.0650, "n": 725},
    "position": {"p_win": 0.419, "avg_win": 0.1511, "avg_loss": 0.0739, "n": 911},
}


def mode_odds(mode_name: str) -> dict:
    """Frequency odds and money odds for a mode, from the measured base rates.

    Two different ratios, and conflating them is the classic way to talk
    yourself into a bad bet: you win LESS often than you lose (frequency odds
    below 1), and you still profit because the wins are twice the size (money
    odds above 1).
    """
    m = MEASURED_ODDS[mode_name]
    p_win, p_loss = m["p_win"], 1 - m["p_win"]
    return {
        "p_win": p_win,
        "freq_ratio": p_win / p_loss,
        "payoff": m["avg_win"] / m["avg_loss"],
        "money_ratio": (p_win * m["avg_win"]) / (p_loss * m["avg_loss"]),
        "ev": p_win * m["avg_win"] - p_loss * m["avg_loss"],
        "avg_win": m["avg_win"],
        "avg_loss": m["avg_loss"],
        "n": m["n"],
    }


# ── Data loading ─────────────────────────────────────────────────────────────
def _corporate_action_factors(ticker: str) -> list[tuple[pd.Timestamp, float]]:
    """(ex_date, unit_multiplier) for bonus + right issues.

    A 1:1 bonus returns 2.0 — every price BEFORE that date is divided by 2.0
    to sit on the same per-share basis as prices after it.
    """
    actions: list[tuple[pd.Timestamp, float]] = []

    div = COMPANY_DIR / ticker / "dividend.csv"
    if div.exists():
        df = pd.read_csv(div)
        for _, row in df.iterrows():
            bonus = pd.to_numeric(row.get("bonus_share"), errors="coerce")
            if pd.isna(bonus) or bonus <= 0:
                continue
            raw_date = str(row.get("book_closure_date", "")).split(" ")[0]
            date = pd.to_datetime(raw_date, errors="coerce")
            if pd.isna(date):
                continue
            actions.append((date, 1.0 + float(bonus) / 100.0))

    rights = COMPANY_DIR / ticker / "right-share.csv"
    if rights.exists():
        df = pd.read_csv(rights)
        for _, row in df.iterrows():
            date = pd.to_datetime(str(row.get("closing_date", "")), errors="coerce")
            if pd.isna(date):
                continue
            try:
                held, new = (float(x) for x in str(row.get("ratio", "")).split(":"))
                if held <= 0:
                    continue
            except (ValueError, TypeError):
                continue
            actions.append((date, 1.0 + new / held))

    return sorted(actions)


def load_prices(ticker: str) -> pd.DataFrame | None:
    """Ascending, corporate-action-adjusted OHLC + volume. None if unusable."""
    path = COMPANY_DIR / ticker / "prices.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty or "ltp" not in df.columns:
        return None

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["ltp"] = pd.to_numeric(df["ltp"], errors="coerce")
    df = df.dropna(subset=["date", "ltp"]).sort_values("date").reset_index(drop=True)
    df = df[df["ltp"] > 0].reset_index(drop=True)
    if len(df) < MIN_HISTORY_DAYS:
        return None

    # Backward adjustment: divide every price strictly before an ex-date by the
    # cumulative multiplier of all actions from that date onward.
    factor = pd.Series(1.0, index=df.index)
    for ex_date, mult in _corporate_action_factors(ticker):
        factor.loc[df["date"] < ex_date] *= mult

    out = pd.DataFrame({"date": df["date"]})
    for col in ("open", "high", "low"):
        src = pd.to_numeric(df[col], errors="coerce") if col in df else df["ltp"]
        out[col] = src.fillna(df["ltp"]).to_numpy() / factor.to_numpy()
    out["close"] = df["ltp"].to_numpy() / factor.to_numpy()
    out["qty"] = pd.to_numeric(df.get("qty", 0), errors="coerce").fillna(0.0).to_numpy()
    out["turnover"] = pd.to_numeric(df.get("turnover", 0), errors="coerce").fillna(0.0).to_numpy()
    # High/low can invert if a source row carried only ltp; clamp so ranges stay sane.
    ohlc = out[["open", "high", "low", "close"]]
    out["high"], out["low"] = ohlc.max(axis=1), ohlc.min(axis=1)

    # Raw (un-adjusted) high/close, kept alongside the rights/bonus-adjusted
    # series above. A 52-week-high check must compare against the price the
    # stock actually traded at, not a rights-deflated synthetic value — every
    # broker/data site (ShareSansar, Merolagani) quotes the raw traded high.
    raw_high = pd.to_numeric(df["high"], errors="coerce") if "high" in df else df["ltp"]
    out["high_raw"] = raw_high.fillna(df["ltp"]).to_numpy()
    out["close_raw"] = df["ltp"].to_numpy()
    return out.reset_index(drop=True)


def load_index() -> pd.DataFrame:
    df = pd.read_csv(NEPSE_INDEX)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    df["ma200"] = df["close"].rolling(200).mean()
    df["regime_ok"] = df["close"] > df["ma200"]
    return df[["date", "close", "ma200", "regime_ok"]]


# ── Indicators ───────────────────────────────────────────────────────────────
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ADX — trend strength, direction-agnostic."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(df, period).replace(0, np.nan)
    alpha = 1 / period
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / tr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False).mean().fillna(0.0)


def macd_hist(close: pd.Series) -> pd.Series:
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    return line - line.ewm(span=9, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ma20"] = out["close"].rolling(20).mean()
    out["ma50"] = out["close"].rolling(50).mean()
    out["ma200"] = out["close"].rolling(200).mean()
    out["ma50_slope"] = out["ma50"] - out["ma50"].shift(20)
    out["rsi14"] = rsi(out["close"])
    out["adx14"] = adx(out)
    out["macd_hist"] = macd_hist(out["close"])
    out["atr14"] = atr(out)
    out["high250"] = out.get("high_raw", out["high"]).rolling(250).max()
    out["roc60"] = out["close"] / out["close"].shift(60) - 1
    out["vol20"] = out["qty"].rolling(20).mean()
    out["vol60"] = out["qty"].rolling(60).mean()
    out["turnover60"] = out["turnover"].rolling(60).median()
    return out


# ── Signal rules ─────────────────────────────────────────────────────────────
@dataclass
class Signal:
    ticker: str
    date: pd.Timestamp
    close: float
    score: int
    mode: Mode
    gates: dict[str, bool]
    detail: dict[str, float]

    @property
    def is_buy(self) -> bool:
        return all(self.gates.values()) and self.score >= BUY_SCORE

    def levels(self, target: float | None = None, stop: float | None = None) -> dict[str, float]:
        # Stop is the WIDER of the fixed % and N x ATR — a stop tighter than the
        # stock's own daily noise is a guaranteed loss, not risk control.
        target = self.mode.target if target is None else target
        stop = self.mode.stop if stop is None else stop
        stop_pct = max(stop, self.mode.atr_mult * self.detail["atr14"] / self.close)
        return {
            "entry": self.close,
            "stop": self.close * (1 - stop_pct),
            "stop_pct": stop_pct,
            # Reference only — the default exit is the trailing stop below.
            "target": self.close * (1 + target),
            "trail_atr": self.mode.trail_atr,
            "trail_distance": self.mode.trail_atr * self.detail["atr14"],
        }


def evaluate(ticker: str, ind: pd.DataFrame, i: int, regime_ok: bool, mode: Mode) -> Signal | None:
    """Evaluate the rules at row i. None if indicators aren't warm yet."""
    r = ind.iloc[i]
    if pd.isna(r["ma200"]) or pd.isna(r["high250"]) or pd.isna(r["turnover60"]):
        return None
    close_raw = r["close_raw"] if "close_raw" in r.index else r["close"]

    gates = {
        # Can you actually get out of a position in this name? NEPSE's tail of
        # illiquid counters shows beautiful charts you cannot sell into.
        "liquidity": bool(r["turnover60"] >= MIN_MEDIAN_TURNOVER),
        # NEPSE is a high-beta single-factor market: most names follow the index.
        "market_regime": bool(regime_ok),
        "uptrend": bool(r["close"] > r["ma50"] > r["ma200"] and r["ma50_slope"] > 0),
        "near_high": bool(close_raw >= mode.near_high * r["high250"]),
        "not_extended": bool(r["rsi14"] <= RSI_CEILING and r["close"] <= MAX_EXTENSION * r["ma20"]),
        "trend_strength": bool(r["adx14"] >= mode.adx_floor),
        "volume_expansion": bool(r["vol20"] >= VOL_EXPANSION * r["vol60"]),
    }

    score = 100 if all(gates.values()) else 10 * sum(gates.values())
    if all(gates.values()):
        # Deductions inside the qualified set — ranking, not gating.
        if not 45 <= r["rsi14"] <= 65:
            score -= 10
        if r["macd_hist"] <= 0:
            score -= 15
        if not pd.isna(r["roc60"]) and r["roc60"] < 0.05:
            score -= 10
        if r["turnover60"] < 5 * MIN_MEDIAN_TURNOVER:
            score -= 5

    return Signal(
        ticker=ticker,
        date=r["date"],
        close=float(r["close"]),
        score=int(max(0, min(100, score))),
        mode=mode,
        gates=gates,
        detail={
            "rsi14": float(r["rsi14"]),
            "adx14": float(r["adx14"]),
            "atr14": float(r["atr14"]),
            "macd_hist": float(r["macd_hist"]),
            "roc60": 0.0 if pd.isna(r["roc60"]) else float(r["roc60"]),
            "pct_of_high250": float(close_raw / r["high250"]),
            "turnover60": float(r["turnover60"]),
        },
    )


# ── Trade simulation ─────────────────────────────────────────────────────────
def simulate_trailing(ind: pd.DataFrame, entry_i: int, mode: Mode,
                      trail_atr: float = 3.0, stop: float | None = None) -> dict | None:
    """Forward-test one entry with no profit cap — a ratcheting ATR stop only.

    A fixed target caps the right tail. This strategy already has a set-mining
    payoff shape (negative median, positive mean), so the winners are the whole
    edge and capping them at +40% truncates exactly the outcomes that pay for
    the losses. Here the stop ratchets up behind the highest close and the
    trade runs until it is taken out or the time stop fires.
    """
    if entry_i + 1 >= len(ind):
        return None
    entry = float(ind["open"].iloc[entry_i + 1])
    if entry <= 0:
        return None
    stop = mode.stop if stop is None else stop
    stop_pct = max(stop, mode.atr_mult * float(ind["atr14"].iloc[entry_i]) / entry)

    window = ind.iloc[entry_i + 1 : entry_i + 1 + mode.max_hold]
    if len(window) < mode.min_hold:
        return None

    stop_px = entry * (1 - stop_pct)
    peak = entry
    entry_date = window["date"].iloc[0]
    for held, (_, bar) in enumerate(window.iterrows(), start=1):
        if held >= mode.min_hold and bar["low"] <= stop_px:
            return {"outcome": "trail_stop", "ret": stop_px / entry - 1, "days": held,
                    "entry_date": entry_date, "exit_date": bar["date"]}
        if bar["close"] > peak:
            peak = float(bar["close"])
            # Ratchet only upward — a trailing stop that can loosen is not a stop.
            stop_px = max(stop_px, peak - trail_atr * float(bar["atr14"]))
    exit_px = float(window["close"].iloc[-1])
    return {"outcome": "time", "ret": exit_px / entry - 1, "days": len(window),
            "entry_date": entry_date, "exit_date": window["date"].iloc[-1]}


def simulate(ind: pd.DataFrame, entry_i: int, mode: Mode,
             target: float | None = None, stop: float | None = None) -> dict | None:
    """Forward-test one entry. Entry at next bar's open (no same-bar fills)."""
    if entry_i + 1 >= len(ind):
        return None
    entry = float(ind["open"].iloc[entry_i + 1])
    if entry <= 0:
        return None
    target = mode.target if target is None else target
    stop = mode.stop if stop is None else stop
    stop_pct = max(stop, mode.atr_mult * float(ind["atr14"].iloc[entry_i]) / entry)
    stop_px, target_px = entry * (1 - stop_pct), entry * (1 + target)

    window = ind.iloc[entry_i + 1 : entry_i + 1 + mode.max_hold]
    if len(window) < mode.min_hold:
        return None  # forward window runs off the end of the data — not a trade

    entry_date = window["date"].iloc[0]
    for held, (_, bar) in enumerate(window.iterrows(), start=1):
        if held < mode.min_hold:
            continue  # minimum hold for the mode
        # Both levels touched intrabar: assume the stop filled first. Optimistic
        # tie-breaking is how backtests manufacture win rates that never arrive.
        if bar["low"] <= stop_px:
            return {"outcome": "stop", "ret": -stop_pct, "days": held,
                    "entry_date": entry_date, "exit_date": bar["date"]}
        if bar["high"] >= target_px:
            return {"outcome": "target", "ret": target, "days": held,
                    "entry_date": entry_date, "exit_date": bar["date"]}
    exit_px = float(window["close"].iloc[-1])
    return {"outcome": "time", "ret": exit_px / entry - 1, "days": len(window),
            "entry_date": entry_date, "exit_date": window["date"].iloc[-1]}


def all_tickers() -> list[str]:
    return sorted(p.name for p in COMPANY_DIR.iterdir() if (p / "prices.csv").exists())


def _universe_last_date() -> pd.Timestamp:
    """Latest bar across every ticker — the market's real last trading day."""
    dates = []
    for t in all_tickers():
        try:
            col = pd.read_csv(COMPANY_DIR / t / "prices.csv", usecols=["date"])["date"]
        except (ValueError, pd.errors.EmptyDataError):
            continue
        d = pd.to_datetime(col, errors="coerce").max()
        if not pd.isna(d):
            dates.append(d)
    return max(dates)


def _prepare(ticker: str, index: pd.DataFrame) -> pd.DataFrame | None:
    px = load_prices(ticker)
    if px is None:
        return None
    ind = add_indicators(px)
    merged = ind.merge(index[["date", "regime_ok"]], on="date", how="left")
    # Merge yields object dtype (NaN on dates the index lacks); the nullable
    # boolean dtype carries those NaNs through ffill without a downcast.
    merged["regime_ok"] = merged["regime_ok"].astype("boolean").ffill().fillna(False).astype(bool)
    return merged


# ── HTML report ──────────────────────────────────────────────────────────────
REPORT_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 40px 24px; background: #1b1b1b; color: #ededed;
       font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
.wrap { max-width: 1000px; margin: 0 auto; }
.head { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; flex-wrap: wrap; }
.head .regime-note { font-size: 17px; color: #ededed; }
.head .asof { color: #8f8f8f; font-size: 14px; font-weight: 500; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 13px;
        border-radius: 8px; font-size: 15px; font-weight: 600; }
.pill.on  { background: #102b1b; color: #4ade80; }
.pill.off { background: #33161a; color: #f87171; }
.card { border: 1px solid #333; border-radius: 12px; overflow-x: auto; scrollbar-width: thin; }
.card::-webkit-scrollbar { height: 8px; }
.card::-webkit-scrollbar-thumb { background: #444; border-radius: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 14.5px; }
th, td { padding: 12px 9px; text-align: right; white-space: nowrap;
         border-bottom: 1px solid #333; }
tbody tr:last-child td { border-bottom: none; }
th { color: #ededed; font-weight: 600; cursor: pointer; user-select: none; }
th:hover { color: #fff; }
th:nth-child(-n+3), td:nth-child(-n+3) { text-align: left; }
tbody tr:hover { background: #232323; }
td.ticker { font-weight: 700; }
td.rr { font-weight: 700; }
.badge { display: inline-block; padding: 4px 12px; border-radius: 8px;
         font-size: 15px; font-weight: 500; }
.badge.position { background: #16304d; color: #60a5fa; }
.badge.swing    { background: #2c2c2c; color: #d4d4d4; }
.score { display: inline-flex; align-items: center; gap: 12px; }
.score .bar { width: 46px; height: 6px; background: #2c2c2c; border-radius: 3px; overflow: hidden; }
.score .fill { display: block; height: 100%; background: #4a90e2; border-radius: 3px; }
.hot { color: #f87171; }
.cold { color: #4ade80; }
.callout { display: flex; gap: 12px; margin: 26px 0 0; padding: 20px 24px;
           border-radius: 12px; background: #3a2e07; border: 1px solid #6b5712; }
.callout .icon { color: #fbbf24; font-size: 18px; line-height: 1.5; }
.callout p { margin: 0; color: #fbbf24; font-size: 16px; font-weight: 600; line-height: 1.6; }
.snap-btn { padding: 6px 16px; background: #2c2c2c; color: #ededed; border: 1px solid #444;
            border-radius: 8px; font-size: 14px; font-weight: 500; cursor: pointer;
            margin-left: auto; text-decoration: none; display: inline-block; }
.snap-btn:hover { background: #333; border-color: #555; }
/* ponytail: checkbox toggle, not JS or :target — the extension CSP blocks scripts in
   this iframe, and srcdoc has no base URL so fragment links never fire :target. */
#snap-toggle { display: none; }
#snapshots { display: none; }
#snap-toggle:checked ~ #snapshots { display: block; }
#snap-toggle:checked ~ #scan { display: none; }
#snapshots h1 { font-size: 24px; margin: 0; }
.snap-head { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; }
.snap-item { padding: 14px 18px; margin-bottom: 10px; background: #232323;
             border: 1px solid #333; border-radius: 10px;
             display: flex; align-items: center; justify-content: space-between; }
.snap-date { font-size: 16px; font-weight: 600; }
.snap-count { font-size: 14px; color: #8f8f8f; }
.snap-now { border-color: #2f6b45; }
.snap-now .snap-date::after { content: " CURRENT"; color: #4ade80; font-size: 12px; }
.snap-empty { color: #8f8f8f; padding: 20px 0; }
@media print { body { background: #fff; color: #000; padding: 0; }
                .callout { background: #fdf6e0; } th, td { border-color: #ccc; } }
"""

REPORT_JS = """
document.querySelectorAll('th').forEach(function (th, i) {
  th.addEventListener('click', function () {
    var tb = th.closest('table').tBodies[0];
    var rows = Array.prototype.slice.call(tb.rows);
    var desc = th.dataset.desc !== 'true';
    rows.sort(function (a, b) {
      var x = a.cells[i].dataset.v, y = b.cells[i].dataset.v;
      var nx = parseFloat(x), ny = parseFloat(y);
      var c = (isNaN(nx) || isNaN(ny)) ? String(x).localeCompare(String(y)) : nx - ny;
      return desc ? -c : c;
    });
    th.dataset.desc = desc;
    rows.forEach(function (r) { tb.appendChild(r); });
  });
});
"""

# Column key -> (header label, sortable raw value extractor). Percent/ratio
# columns arrive as pre-formatted strings, so the raw value is stripped back to
# a number for the sort only.
REPORT_COLUMNS = [
    ("ticker", "Ticker"), ("mode", "Mode"), ("score", "Score"), ("close", "Close"),
    ("stop", "Stop"), ("target", "Target"), ("rewd:risk", "Rwd:risk"), ("rsi", "RSI"),
    ("adx", "ADX"), ("%of52wH", "%of52wH"),
]


def _sort_value(raw) -> str:
    """Numeric prefix of a display string, for the client-side sort."""
    s = str(raw).replace("%", "").replace("M", "")
    s = s.split(":")[0] if ":" in s else s
    try:
        return str(float(s))
    except ValueError:
        return str(raw)


def _report_row(row: dict) -> str:
    cells = []
    for key, _ in REPORT_COLUMNS:
        val = row[key]
        sort_v = html.escape(_sort_value(val), quote=True)
        if key == "ticker":
            inner, cls = html.escape(str(val)), ' class="ticker"'
        elif key == "mode":
            inner = f'<span class="badge {html.escape(str(val))}">{html.escape(str(val))}</span>'
            cls = ""
        elif key == "score":
            pct = max(0.0, min(100.0, float(val)))
            inner = (f'<span class="score"><span class="bar">'
                     f'<span class="fill" style="width:{pct:.0f}%"></span></span>{val}</span>')
            cls = ""
        elif key == "rsi":
            rsi_v = float(val)
            tone = "hot" if rsi_v >= 70 else "cold" if rsi_v <= 30 else ""
            inner, cls = html.escape(str(val)), f' class="{tone}"' if tone else ""
        elif key == "rewd:risk":
            inner, cls = html.escape(str(val)), ' class="rr"'
        else:
            inner, cls = html.escape(str(val)), ""
        cells.append(f'<td{cls} data-v="{sort_v}">{inner}</td>')
    return "<tr>" + "".join(cells) + "</tr>"


def _odds_block(mode_names: list[str]) -> str:
    """One amber warning paragraph: per-mode base rates, then the caveat."""
    stats = []
    for name in mode_names:
        o = mode_odds(name)
        stats.append(
            f"{name.capitalize()} mode: {o['p_win']:.0%} win rate, "
            f"{o['money_ratio']:.2f}:1 money odds, {o['ev']:+.2%} EV/trade "
            f"over {o['n']} trades (avg win {o['avg_win']:+.1%}, "
            f"avg loss -{o['avg_loss']:.1%}, frequency odds {o['freq_ratio']:.2f}:1 against)."
        )
    body = (
        "Odds are strategy-level, not per-stock. " + " ".join(stats) +
        " Every row above shares these same odds — score does not predict which "
        "name outperforms; rwd:risk varies only because it reflects each stock's "
        "own ATR stop width."
    )
    return f'<div class="icon">&#9888;</div><p>{html.escape(body)}</p>'


def _archive_path(mode: str, when: datetime) -> Path:
    """A never-overwritten path under output/history/, suffixed on collision."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    base = f"scan_{mode}_{when:%Y%m%d_%H%M%S}"
    path = HISTORY_DIR / f"{base}.html"
    n = 2
    while path.exists():
        path = HISTORY_DIR / f"{base}_{n}.html"
        n += 1
    return path


def _point_latest_at(target: Path) -> None:
    latest = OUTPUT_DIR / "latest.html"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        os.symlink(target.relative_to(OUTPUT_DIR), latest)
    except OSError:
        # ponytail: filesystems without symlinks (or a locked file) get a copy.
        shutil.copyfile(target, latest)


def _snapshot_hash(out: pd.DataFrame) -> str:
    """Hash of current scan (ticker + score), for dedup."""
    data = "|".join(f"{r['ticker']}:{r['score']}" for _, r in out.iterrows())
    return hashlib.md5(data.encode()).hexdigest()


def _load_snapshots() -> list[dict]:
    """Load snapshots.json; return empty list if not found."""
    snap_file = OUTPUT_DIR / "snapshots.json"
    if snap_file.exists():
        return json.loads(snap_file.read_text())
    return []


def _save_snapshot(now: datetime, count: int, hash_val: str) -> None:
    """Store snapshot if different from last. Keep 20 most recent."""
    snap_file = OUTPUT_DIR / "snapshots.json"
    snapshots = _load_snapshots()
    if snapshots and snapshots[-1]["hash"] == hash_val:
        return  # Skip duplicate
    snapshots.append({
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "count": count,
        "hash": hash_val,
    })
    snap_file.write_text(json.dumps(snapshots[-20:], indent=2))


def _snapshot_rows(snapshots: list[dict], current_hash: str) -> str:
    """Static HTML list of snapshots, newest first. No JS — extension CSP blocks it."""
    if not snapshots:
        return '<div class="snap-empty">No snapshots saved yet.</div>'
    out = []
    for s in reversed(snapshots):
        cls = "snap-item snap-now" if s.get("hash") == current_hash else "snap-item"
        out.append(
            f'<div class="{cls}">'
            f'<span class="snap-date">{html.escape(s["date"])} at {html.escape(s["time"])}</span>'
            f'<span class="snap-count">{s["count"]} rows</span></div>'
        )
    return "".join(out)


def write_html_report(out: pd.DataFrame, mode_names: list[str], regime: bool,
                      latest_bar, cutoff, stale: int) -> Path:
    """Archive the scan as a self-contained dark-theme HTML file.

    Returns the timestamped archive path; output/latest.html is repointed at it.
    """
    now = datetime.now()
    ranked = out.sort_values("score", ascending=False)
    rows = "".join(_report_row(r) for r in ranked.to_dict("records"))
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in REPORT_COLUMNS)
    badge = ('<span class="pill on">&#8599; Risk-on</span>' if regime
             else '<span class="pill off">&#8600; Risk-off</span>')
    snap_hash = _snapshot_hash(ranked)
    _save_snapshot(now, len(ranked), snap_hash)
    snap_rows = _snapshot_rows(_load_snapshots(), snap_hash)
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Karma NEPSE Signal — {now:%Y-%m-%d %H:%M}</title>
<style>{REPORT_CSS}</style></head>
<body>
<input type="checkbox" id="snap-toggle">
<div id="snapshots" class="wrap">
  <div class="snap-head"><h1>&#128248; Snapshots</h1>
    <label for="snap-toggle" class="snap-btn">&larr; Back to scan</label></div>
  {snap_rows}
</div>
<div id="scan" class="wrap">
<div class="head">{badge}
  <span class="regime-note">NEPSE index {'above' if regime else 'below'} MA200</span>
  <span class="asof">as of {latest_bar.date()} &middot; {stale} tickers skipped (stale, no bar since {cutoff.date()})</span>
  <label for="snap-toggle" class="snap-btn">&#128248; Snapshots</label>
</div>
<div class="card"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>
<div class="callout">{_odds_block(mode_names)}</div>
</div><script>{REPORT_JS}</script></body></html>
"""
    path = _archive_path("_".join(mode_names) if len(mode_names) > 1 else mode_names[0], now)
    path.write_text(doc, encoding="utf-8")
    _point_latest_at(path)
    return path


# ── Commands ─────────────────────────────────────────────────────────────────
def _modes(args) -> list[Mode]:
    return list(MODES.values()) if args.mode == "both" else [MODES[args.mode]]


def cmd_scan(args) -> None:
    index = load_index()
    regime = bool(index["regime_ok"].iloc[-1])
    print(f"NEPSE regime: {'RISK-ON (index > MA200)' if regime else 'RISK-OFF (index < MA200)'}")
    if not regime:
        print("Market gate is shut. Every name fails `market_regime`.\n")

    # Newest bar anywhere in the universe = the market's last trading day.
    # Anything lagging it is suspended, delisted, or a stale file — its
    # indicators are frozen in the past and would rank as live signals.
    latest = _universe_last_date()
    cutoff = latest - pd.Timedelta(days=MAX_STALE_DAYS)
    index_lag = (latest - index["date"].max()).days
    if index_lag > MAX_STALE_DAYS:
        print(
            f"WARNING: index history ends {index['date'].max().date()}, {index_lag} days behind "
            f"prices. The market_regime gate is reading a stale index — refresh "
            f"data/index/nepse/history.csv before trusting these signals."
        )

    rows, stale = [], 0
    for t in all_tickers():
        ind = _prepare(t, index)
        if ind is None:
            continue
        if ind["date"].iloc[-1] < cutoff:
            stale += 1
            continue
        for mode in _modes(args):
            sig = evaluate(t, ind, len(ind) - 1, bool(ind["regime_ok"].iloc[-1]), mode)
            if not (sig and sig.is_buy):
                continue
            lv = sig.levels(args.target, args.stop)
            odds = mode_odds(mode.name)
            # The one genuinely per-stock ratio: what this name's own ATR stop
            # offers. Wider stop = worse odds on the same expected move.
            rr = odds["avg_win"] / lv["stop_pct"]
            rows.append(
                {
                    "ticker": t,
                    "mode": mode.name,
                    "score": sig.score,
                    "close": round(sig.close, 1),
                    "stop": round(lv["stop"], 1),
                    "stop%": f"{lv['stop_pct']:.1%}",
                    "target": round(lv["target"], 1),
                    "up:down": f"{odds['money_ratio']:.2f}:1",
                    "win%": f"{odds['p_win']:.0%}",
                    "rewd:risk": f"{rr:.2f}:1",
                    "trail": round(lv["trail_distance"], 1),
                    "rsi": round(sig.detail["rsi14"], 1),
                    "adx": round(sig.detail["adx14"], 1),
                    "%of52wH": f"{sig.detail['pct_of_high250']:.0%}",
                    "turnover60": f"{sig.detail['turnover60'] / 1e6:.1f}M",
                    "asof": str(sig.date.date()),
                }
            )
    print(f"Universe as of {latest.date()}; skipped {stale} tickers with no bar since {cutoff.date()}.")
    if not rows:
        print("No BUY signals today.")
        return
    out = pd.DataFrame(rows).sort_values(["mode", "score"], ascending=[True, False])
    shown = out.groupby("mode", group_keys=False).head(args.top)
    print(shown.to_string(index=False))

    mode_names = [m.name for m in _modes(args)]
    try:
        report = write_html_report(shown, mode_names, regime, latest, cutoff, stale)
        print(f"\nHTML report: {report}\n  stable link: {OUTPUT_DIR / 'latest.html'}")
    except OSError as ex:
        print(f"\nWARNING: could not write HTML report: {ex}")

    print("\nOdds (measured out-of-sample, net of costs and 7.5% CGT):")
    for mode in _modes(args):
        o = mode_odds(mode.name)
        print(
            f"  {mode.name:9s} wins {o['p_win']:.0%} of trades — you LOSE more often than you win.\n"
            f"            frequency odds {o['freq_ratio']:.2f}:1 against you, "
            f"money odds {o['money_ratio']:.2f}:1 in your favour.\n"
            f"            avg win {o['avg_win']:+.1%}, avg loss -{o['avg_loss']:.1%} "
            f"(payoff {o['payoff']:.2f}:1), EV {o['ev']:+.2%}/trade over {o['n']} trades."
        )
    print(
        "  These odds are the SAME for every row. Nothing measured predicts which\n"
        "  name does better — `tiers` showed score has no monotonic link to outcome.\n"
        "  A per-ticker probability would be fabricated. `rewd:risk` is the only\n"
        "  column that truly varies by stock: it is that name's own ATR stop width."
    )


def cmd_signal(args) -> None:
    index = load_index()
    ticker = args.ticker.upper()
    ind = _prepare(ticker, index)
    if ind is None:
        print(f"{ticker}: no usable price history (need {MIN_HISTORY_DAYS}+ days).")
        return

    for mode in _modes(args):
        sig = evaluate(ticker, ind, len(ind) - 1, bool(ind["regime_ok"].iloc[-1]), mode)
        if sig is None:
            print(f"{ticker}: indicators not warm.")
            return
        print(f"\n=== {mode.name.upper()} ({mode.min_hold}-{mode.max_hold} trading days) ===")
        print(f"{sig.ticker}  as of {sig.date.date()}  close {sig.close:,.1f}")
        print(f"VERDICT: {'BUY' if sig.is_buy else 'NO TRADE'}   score {sig.score}/100\n")
        for name, ok in sig.gates.items():
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        print()
        for k, v in sig.detail.items():
            print(f"  {k:16s} {v:,.2f}")
        if sig.is_buy:
            lv = sig.levels(args.target, args.stop)
            print(
                f"\n  entry {lv['entry']:,.1f}   initial stop {lv['stop']:,.1f} "
                f"({lv['stop_pct']:.1%})"
                f"\n  exit: trailing stop {lv['trail_atr']:.0f}xATR "
                f"= {lv['trail_distance']:,.1f} below the highest close. No profit cap."
                f"\n  reference target {lv['target']:,.1f} (not an exit — capping the "
                f"winners is what the trailing stop exists to avoid)."
                f"\n  time stop: {mode.max_hold} trading days; no exit before {mode.min_hold}."
            )


def _run_backtest(mode: Mode, tickers: list[str], index: pd.DataFrame,
                  target: float | None = None, stop: float | None = None,
                  trail_atr: float | None = None) -> pd.DataFrame:
    trades = []
    for t in tickers:
        ind = _prepare(t, index)
        if ind is None:
            continue
        i, n = MIN_HISTORY_DAYS, len(ind)
        while i < n - 1:
            sig = evaluate(t, ind, i, bool(ind["regime_ok"].iloc[i]), mode)
            if sig and sig.is_buy:
                res = (simulate_trailing(ind, i, mode, trail_atr, stop)
                       if trail_atr else simulate(ind, i, mode, target, stop))
                if res:
                    trades.append(
                        {"ticker": t, "date": ind["date"].iloc[i], "score": sig.score,
                         "rsi14": sig.detail["rsi14"], "adx14": sig.detail["adx14"],
                         "roc60": sig.detail["roc60"],
                         "pct_of_high250": sig.detail["pct_of_high250"], **res}
                    )
                    i += res["days"] + 1  # non-overlapping: one position at a time
                    continue
            i += 1
    return pd.DataFrame(trades)


def _report(trades: pd.DataFrame, mode: Mode, target: float, stop: float) -> dict:
    if trades.empty:
        return {"mode": mode.name, "target": f"{target:.0%}", "stop": f"{stop:.0%}", "trades": 0}
    wins = trades[trades["ret"] > 0]
    net = trades["ret"].map(net_return)
    return {
        "mode": mode.name,
        "target": f"{target:.0%}",
        "stop": f"{stop:.0%}",
        "trades": len(trades),
        "hit_target": f"{(trades['outcome'] == 'target').mean():.1%}",
        "win_rate": f"{len(wins) / len(trades):.1%}",
        "avg_ret": f"{trades['ret'].mean():.2%}",
        "net_avg_ret": f"{net.mean():.2%}",
        "net_win_rate": f"{(net > 0).mean():.1%}",
        "median_ret": f"{trades['ret'].median():.2%}",
        "avg_days": round(trades["days"].mean(), 1),
        "stopped": f"{(trades['outcome'] == 'stop').mean():.1%}",
        "timed_out": f"{(trades['outcome'] == 'time').mean():.1%}",
    }


def cmd_backtest(args) -> None:
    index = load_index()
    tickers = all_tickers()[: args.limit] if args.limit else all_tickers()
    print(f"Backtesting {len(tickers)} tickers...", file=sys.stderr)

    if args.grid:
        rows = [
            _report(_run_backtest(mode, tickers, index, tgt, stp), mode, tgt, stp)
            for mode in _modes(args)
            for tgt in (0.15, 0.20, 0.25, 0.30, 0.40)
            for stp in (0.08, 0.10, 0.15)
        ]
        print(pd.DataFrame(rows).to_string(index=False))
        print("\nhit_target = share of trades that reached the profit target.")
        print("Read that column, not win_rate, when judging the +40% mandate.")
        return

    for mode in _modes(args):
        target = mode.target if args.target is None else args.target
        stop = mode.stop if args.stop is None else args.stop
        trail = mode.trail_atr if args.exit_style == "trail" else None
        trades = _run_backtest(mode, tickers, index, target, stop, trail)
        print(f"\n=== {mode.name.upper()} (exit: {args.exit_style}) ===")
        for k, v in _report(trades, mode, target, stop).items():
            print(f"{k:12s} {v}")
        if not trades.empty:
            print("Worst 5 trades:")
            print(trades.nsmallest(5, "ret")[["ticker", "date", "outcome", "ret", "days"]].to_string(index=False))


def _tail_stats(trades: pd.DataFrame, label: str) -> dict:
    net = trades["ret"].map(net_return)
    return {
        "exit": label,
        "trades": len(trades),
        "win_rate": f"{(trades['ret'] > 0).mean():.1%}",
        "net_avg": f"{net.mean():.2%}",
        "net_median": f"{net.median():.2%}",
        "best": f"{trades['ret'].max():.1%}",
        "top10%_avg": f"{trades['ret'].nlargest(max(1, len(trades) // 10)).mean():.1%}",
        "avg_days": round(trades["days"].mean(), 1),
    }


def cmd_tail(args) -> None:
    """Fixed target vs uncapped trailing stop — does the right tail pay?

    The strategy's median trade loses and its mean trade wins, so the winners
    are the entire edge. A fixed target truncates them by construction. This
    compares capping at the target against letting winners run behind a
    ratcheting ATR stop, judged out-of-sample only.
    """
    index = load_index()
    tickers = all_tickers()[: args.limit] if args.limit else all_tickers()
    split = pd.Timestamp(args.split)

    for mode in _modes(args):
        rows = []
        capped = _run_backtest(mode, tickers, index, args.target, args.stop)
        if not capped.empty:
            oos = capped[capped["date"] >= split]
            if not oos.empty:
                rows.append(_tail_stats(oos, f"target +{mode.target:.0%}"))
        for mult in (2.0, 3.0, 4.0):
            trailed = _run_backtest(mode, tickers, index, stop=args.stop, trail_atr=mult)
            if trailed.empty:
                continue
            oos = trailed[trailed["date"] >= split]
            if not oos.empty:
                rows.append(_tail_stats(oos, f"trail {mult:.0f}xATR"))

        print(f"\n=== {mode.name.upper()} — out-of-sample only (after {split.date()}) ===")
        print(pd.DataFrame(rows).to_string(index=False) if rows else "No trades.")

    print(
        "\nIf trailing beats the fixed target on net_avg, the +40% cap was "
        "costing money.\nWatch top10%_avg — that is the size of the pot when "
        "the setup actually works."
    )


def cmd_tiers(args) -> None:
    """Does being pickier actually pay? Slice outcomes by score and by setup.

    The premise behind any selectivity rule is that the best-looking setups win
    more often than the merely acceptable ones. That is an assumption, not a
    fact, and this is the command that checks it. If the top tier does not beat
    the bottom tier, the score is decoration and folding to it is superstition.
    """
    index = load_index()
    tickers = all_tickers()[: args.limit] if args.limit else all_tickers()
    split = pd.Timestamp(args.split)

    for mode in _modes(args):
        trades = _run_backtest(mode, tickers, index, args.target, args.stop)
        if trades.empty:
            continue
        trades = trades.assign(net=trades["ret"].map(net_return))
        oos = trades[trades["date"] >= split]
        print(f"\n=== {mode.name.upper()} — out-of-sample only (after {split.date()}) ===")
        if oos.empty:
            print("No out-of-sample trades.")
            continue

        rows = []
        for lo, hi in ((70, 84), (85, 94), (95, 100)):
            part = oos[(oos["score"] >= lo) & (oos["score"] <= hi)]
            if part.empty:
                continue
            rows.append({
                "score": f"{lo}-{hi}",
                "trades": len(part),
                "share": f"{len(part) / len(oos):.0%}",
                "hit_target": f"{(part['outcome'] == 'target').mean():.1%}",
                "win_rate": f"{(part['ret'] > 0).mean():.1%}",
                "net_avg": f"{part['net'].mean():.2%}",
                "net_median": f"{part['net'].median():.2%}",
            })
        print(pd.DataFrame(rows).to_string(index=False))

        # The "set or better" tier: the most selective slice that still trades
        # often enough to matter. Poker reference: a pocket pair flops a set
        # 11.8% of the time, so this targets a comparable frequency.
        cutoff = oos["score"].quantile(0.88)
        best = oos[oos["score"] >= cutoff]
        print(
            f"\nTop {len(best) / len(oos):.0%} by score (score >= {cutoff:.0f}), n={len(best)}: "
            f"hit {(best['outcome'] == 'target').mean():.1%}, "
            f"win {(best['ret'] > 0).mean():.1%}, net avg {best['net'].mean():.2%}"
        )
        print(
            f"All out-of-sample trades, n={len(oos)}: "
            f"hit {(oos['outcome'] == 'target').mean():.1%}, "
            f"win {(oos['ret'] > 0).mean():.1%}, net avg {oos['net'].mean():.2%}"
        )
        edge = best["net"].mean() - oos["net"].mean()
        print(
            f"Selectivity edge: {edge:+.2%} per trade. "
            + ("Being pickier pays." if edge > 0.005 else
               "Being pickier does NOT pay — the score is not predictive.")
        )


def _index_window_return(idx: pd.Series, start, end) -> float | None:
    """NEPSE return between two dates, using the last close at or before each.

    `asof` rather than exact lookup: the index series can miss a date the stock
    traded on, and a missing benchmark must not silently drop a trade.
    """
    start_px, end_px = idx.asof(start), idx.asof(end)
    if pd.isna(start_px) or pd.isna(end_px) or start_px <= 0:
        return None
    return end_px / start_px - 1


def _t_stat(series: pd.Series) -> float:
    spread = series.std(ddof=1)
    n = len(series)
    return series.mean() / (spread / np.sqrt(n)) if n > 1 and spread > 0 else float("nan")


def _avg_concurrent(trades: pd.DataFrame) -> float:
    """Mean number of positions open per trading day across the sample.

    Counted by stepping a running total over entry/exit events rather than
    scanning every date against every trade — same answer, and it stays fast
    on the full universe.
    """
    events = pd.concat([
        pd.Series(1, index=pd.DatetimeIndex(trades["entry_date"])),
        pd.Series(-1, index=pd.DatetimeIndex(trades["exit_date"])),
    ]).groupby(level=0).sum().sort_index()
    open_count = events.cumsum()
    # Weight each level by the days it persisted — a count that held for a
    # year must not carry the same weight as one that held for a day.
    spans = open_count.index.to_series().diff().shift(-1).dt.days.fillna(1)
    return float((open_count * spans).sum() / spans.sum())


def cmd_benchmark(args) -> None:
    """The only test that can kill this strategy: is it edge, or is it beta?

    Every gate here is a long-only trend filter, and NEPSE rose across most of
    the sample. So a positive average trade proves nothing on its own. The
    honest question is whether holding these names over these exact windows
    beat holding the index over the same windows — and whether either beat
    simply buying the index once and sleeping through the whole period.
    """
    index = load_index()
    idx = pd.Series(index["close"].to_numpy(), index=index["date"]).sort_index()
    tickers = all_tickers()[: args.limit] if args.limit else all_tickers()
    print(f"Benchmarking {len(tickers)} tickers against NEPSE...", file=sys.stderr)

    for mode in _modes(args):
        trail = mode.trail_atr if args.exit_style == "trail" else None
        trades = _run_backtest(mode, tickers, index, mode.target, mode.stop, trail)
        print(f"\n=== {mode.name.upper()} (exit: {args.exit_style}) ===")
        if trades.empty:
            print("no trades")
            continue

        if args.since:
            trades = trades[trades["entry_date"] >= pd.Timestamp(args.since)]
            if trades.empty:
                print(f"no trades after {args.since}")
                continue
        trades = trades.assign(
            bench=[_index_window_return(idx, a, b)
                   for a, b in zip(trades["entry_date"], trades["exit_date"])]
        ).dropna(subset=["bench"])
        trades = trades.assign(net=trades["ret"].map(net_return))
        alpha = trades["net"] - trades["bench"]
        n = len(trades)

        # Trades overlap heavily in calendar time — dozens can be open at once,
        # all riding the same market. Treating them as independent draws is the
        # single easiest way to manufacture significance that isn't there, so
        # the honest test collapses each month to one observation first.
        naive_t = _t_stat(alpha)
        monthly = alpha.groupby(trades["entry_date"].dt.to_period("M")).mean()
        quarterly = alpha.groupby(trades["entry_date"].dt.to_period("Q")).mean()

        # Per-day figures are capital-time-weighted (total return over total
        # days held), not an average of per-trade rates, which would let a
        # 10-day trade outvote a 60-day one.
        days = trades["days"].sum()
        strat_per_day = trades["net"].sum() / days
        bench_per_day = trades["bench"].sum() / days

        span_start, span_end = trades["entry_date"].min(), trades["exit_date"].max()
        years = (span_end - span_start).days / 365.25
        bh_gross = _index_window_return(idx, span_start, span_end)
        bh_cagr = (1 + buy_hold_net(bh_gross)) ** (1 / years) - 1 if years > 0 else float("nan")

        print(f"period       {span_start:%Y-%m-%d} to {span_end:%Y-%m-%d}  ({years:.1f} yrs)")
        print(f"trades       {n}")
        print(f"net avg      {trades['net'].mean():+.2%}   per trade, after costs and 7.5% CGT")
        print(f"nepse avg    {trades['bench'].mean():+.2%}   same windows, gross")
        print(f"alpha        {alpha.mean():+.2%}   per trade")
        print(f"beat index   {(alpha > 0).mean():.1%}   of trades")
        print(f"t-stat       {naive_t:.2f} per-trade (INFLATED — trades overlap)  "
              f"{_t_stat(monthly):.2f} monthly  {_t_stat(quarterly):.2f} quarterly")
        print(f"alpha months {(monthly > 0).mean():.0%} positive ({len(monthly)})   "
              f"quarters {(quarterly > 0).mean():.0%} positive ({len(quarterly)})")
        # How many positions were actually open at once. The annualized figure
        # assumes capital is continuously redeployed, which is only true if the
        # signal produces enough concurrent candidates to keep every slot full.
        # If it averages fewer than `slots`, idle cash drags the real return
        # down and the annualized number is fiction.
        concurrent = _avg_concurrent(trades)
        fill = min(1.0, concurrent / args.slots)

        print(f"per day      strategy {strat_per_day:+.3%}  vs  nepse {bench_per_day:+.3%}")
        print(f"annualized   {(1 + strat_per_day) ** TRADING_DAYS_PER_YEAR - 1:+.1%}   "
              f"if kept fully deployed ({TRADING_DAYS_PER_YEAR} trading days)")
        print(f"concurrent   {concurrent:.1f} positions open on an average day "
              f"({fill:.0%} of {args.slots} slots filled)")
        deployed = (1 + strat_per_day * fill) ** TRADING_DAYS_PER_YEAR - 1
        print(f"realistic    {deployed:+.1%}   annualized with idle cash earning nothing")
        print(f"buy & hold   {bh_cagr:+.1%} CAGR   one round trip, 5% CGT, always invested")

        # A higher return with a t-stat under 2 is a difference we cannot
        # distinguish from luck, and saying "beats" there is how a backtest
        # talks someone into risking money on noise.
        if deployed <= bh_cagr:
            verdict = "LOSES to buy-and-hold"
        elif _t_stat(quarterly) >= 2.0:
            verdict = "BEATS buy-and-hold, alpha significant"
        else:
            verdict = "higher return, but alpha NOT significant — cannot rule out luck"
        print(f"verdict      {verdict}")
        print("note         NEPSE index is price-return: buy-and-hold also collects "
              "~2-4%/yr in dividends this comparison ignores.")


def cmd_regime(args) -> None:
    """Where does the alpha live — falling markets or rising ones?

    PRE-REGISTERED HYPOTHESIS (stated before this was first run): alpha should
    be LARGER when NEPSE fell during the hold, because a ratcheting stop exits
    a decline the index has to sit through. If instead the alpha sits in rising
    windows, the strategy is leveraged beta and the stop is not earning its
    keep. Written down first so the result cannot be reinterpreted after the
    fact — with only ~13 independent quarters, a hypothesis invented after
    seeing the split would be indistinguishable from curve-fitting.

    The `market_regime` gate blocks entries below the index MA200, so there are
    no RISK-OFF entries to split on. The split is on what the market did during
    the hold, which is the part the exit logic actually has to survive.
    """
    index = load_index()
    idx = pd.Series(index["close"].to_numpy(), index=index["date"]).sort_index()
    tickers = all_tickers()[: args.limit] if args.limit else all_tickers()
    print(f"Regime split across {len(tickers)} tickers...", file=sys.stderr)

    for mode in _modes(args):
        trail = mode.trail_atr if args.exit_style == "trail" else None
        trades = _run_backtest(mode, tickers, index, mode.target, mode.stop, trail)
        if args.since:
            trades = trades[trades["entry_date"] >= pd.Timestamp(args.since)]
        print(f"\n=== {mode.name.upper()} (exit: {args.exit_style}) ===")
        if trades.empty:
            print("no trades")
            continue

        trades = trades.assign(
            bench=[_index_window_return(idx, a, b)
                   for a, b in zip(trades["entry_date"], trades["exit_date"])]
        ).dropna(subset=["bench"])
        trades = trades.assign(
            net=trades["ret"].map(net_return),
            quarter=trades["entry_date"].dt.to_period("Q"),
        )
        trades = trades.assign(alpha=trades["net"] - trades["bench"])

        rows = []
        for label, sel in (("index FELL", trades["bench"] < 0),
                           ("index ROSE", trades["bench"] >= 0)):
            g = trades[sel]
            if g.empty:
                continue
            q = g.groupby("quarter")["alpha"].mean()
            rows.append({
                "window": label,
                "trades": len(g),
                "share": f"{len(g) / len(trades):.0%}",
                "strategy": f"{g['net'].mean():+.2%}",
                "nepse": f"{g['bench'].mean():+.2%}",
                "alpha": f"{g['alpha'].mean():+.2%}",
                "t_quarterly": f"{_t_stat(q):.2f}",
                "quarters": len(q),
            })
        print(pd.DataFrame(rows).to_string(index=False))


def cmd_size(args) -> None:
    """Position size from risk-per-trade, not from gut feel.

    The number that matters is risk per trade (bankroll lost if the stop
    fills), not position size. They differ by the stop width: a 12% stop turns
    1% risk into an 8% position. Confusing the two is how a "5% position"
    quietly becomes a 5%-of-bankroll loss.
    """
    mode = MODES[args.mode]
    stop = mode.stop if args.stop is None else args.stop
    position = args.bankroll * (args.risk / stop)

    print(f"Bankroll {args.bankroll:,.0f}   mode {mode.name}   stop {stop:.0%}")
    print(f"Risk per trade {args.risk:.1%} = {args.bankroll * args.risk:,.0f}")
    print(f"-> position size {position:,.0f} ({position / args.bankroll:.1%} of bankroll)\n")

    # NEPSE is close to a single-factor market: in a real drawdown every open
    # position falls together, so concurrent positions do not diversify risk
    # the way the arithmetic suggests. Total heat is the binding constraint.
    max_concurrent = int(args.heat / args.risk)
    print(f"Total heat cap {args.heat:.1%} -> at most {max_concurrent} concurrent positions.")
    print(
        "NEPSE positions are highly correlated; treat that cap as a hard limit, "
        "not a target.\n"
    )

    # Losing streaks are the real risk, and they are longer than intuition says.
    win = 0.40  # out-of-sample position-mode win rate, rounded down
    for streak in (5, 10, 15):
        odds = (1 - win) ** streak
        dd = 1 - (1 - args.risk) ** streak
        print(
            f"  {streak} straight losses: {odds:.1%} likely per {streak}-trade window, "
            f"drawdown {dd:.1%} (needs {1 / (1 - dd) - 1:+.1%} to recover)"
        )


def cmd_walkforward(args) -> None:
    """Split trades by entry date and compare the two halves.

    The gates were chosen from published swing-trading research and NEPSE
    market structure, not fitted to this data — so a large in-sample /
    out-of-sample gap would mean the rules are riding a regime, not an edge.
    This is the test that can actually embarrass the strategy, which is why
    it exists.
    """
    index = load_index()
    tickers = all_tickers()[: args.limit] if args.limit else all_tickers()
    split = pd.Timestamp(args.split)
    print(f"Walk-forward split at {split.date()} across {len(tickers)} tickers...", file=sys.stderr)

    rows = []
    for mode in _modes(args):
        target = mode.target if args.target is None else args.target
        stop = mode.stop if args.stop is None else args.stop
        trail = mode.trail_atr if args.exit_style == "trail" else None
        trades = _run_backtest(mode, tickers, index, target, stop, trail)
        if trades.empty:
            continue
        for label, part in (
            ("in-sample", trades[trades["date"] < split]),
            ("out-of-sample", trades[trades["date"] >= split]),
        ):
            rows.append({"period": label, **_report(part, mode, target, stop)})

    if not rows:
        print("No trades in either period.")
        return
    print(pd.DataFrame(rows).to_string(index=False))
    print(
        "\nA large drop from in-sample to out-of-sample means the rules were "
        "riding a past regime.\nSimilar numbers mean the edge, such as it is, "
        "is stable. Judge on hit_target and net_avg_ret."
    )


def cmd_selftest(_args) -> None:
    """Smallest check that fails if the core logic breaks."""
    n = 400
    dates = pd.bdate_range("2020-01-01", periods=n)
    close = pd.Series(np.linspace(100, 200, n)) * (1 + 0.002 * np.sin(np.arange(n)))
    df = pd.DataFrame(
        {"date": dates, "open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "qty": 10_000.0, "turnover": close * 10_000}
    )
    ind = add_indicators(df)
    r = ind.iloc[-1]
    assert 0 <= r["rsi14"] <= 100, "RSI out of bounds"
    assert r["rsi14"] > 60, f"RSI should be high in a clean uptrend, got {r['rsi14']:.1f}"
    assert r["adx14"] > 20, f"ADX should confirm a trend, got {r['adx14']:.1f}"
    assert r["close"] > r["ma50"] > r["ma200"], "MA stack wrong in an uptrend"

    pos = MODES["position"]
    sig = evaluate("TEST", ind, len(ind) - 1, True, pos)
    assert sig is not None and sig.gates["uptrend"], "uptrend gate failed on an uptrend"
    assert not evaluate("TEST", ind, len(ind) - 1, False, pos).is_buy, "risk-off must veto"

    # A crash right after entry must resolve as a stop, never as a target.
    crash = ind.copy()
    crash.loc[crash.index[-40:], ["open", "high", "low", "close"]] *= 0.5
    res = simulate(crash, len(crash) - 45, pos)
    assert res and res["outcome"] == "stop", f"crash should stop out, got {res}"

    # Stop must never be tighter than the mode's ATR floor.
    lv = sig.levels(target=0.40, stop=0.01)
    assert lv["stop_pct"] >= pos.atr_mult * sig.detail["atr14"] / sig.close - 1e-9, "ATR floor not applied"

    # Swing must never hold past its own time stop.
    sw = MODES["swing"]
    flat = ind.copy()
    flat.loc[:, ["open", "high", "low", "close"]] = 100.0
    res = simulate(flat, 300, sw)
    assert res and sw.min_hold <= res["days"] <= sw.max_hold, f"swing hold out of range: {res}"
    # Truncated forward window must not be scored as a trade.
    assert simulate(flat, len(flat) - 3, sw) is None, "incomplete trade leaked into results"
    assert sw.max_hold < pos.max_hold, "swing must be shorter than position"

    # Costs must always reduce a gain and always deepen a loss — never flatter.
    assert net_return(0.40) < 0.40, "CGT and fees not applied to a gain"
    assert net_return(-0.10) < -0.10, "fees not applied to a loss"
    assert net_return(0.0) < 0.0, "a flat trade still pays commission"
    # A gain smaller than the round trip is a net loss — CGT must not apply.
    assert net_return(0.001) > -0.02, f"CGT charged on a losing trade: {net_return(0.001)}"

    # Trailing stop must ratchet up only, and must never cap a runaway winner
    # at the fixed target the way `simulate` does.
    runaway = ind.copy()
    runaway.loc[runaway.index[-50:], ["open", "high", "low", "close"]] *= 3.0
    capped = simulate(runaway, len(runaway) - 55, pos, target=0.40)
    trailed = simulate_trailing(runaway, len(runaway) - 55, pos)
    assert capped and abs(capped["ret"] - 0.40) < 1e-9, f"fixed target should cap at 40%: {capped}"
    assert trailed and trailed["ret"] > 0.40, f"trailing should beat the cap: {trailed}"
    assert simulate_trailing(flat, len(flat) - 3, pos) is None, "incomplete trailing trade leaked"

    # Every trade must carry the exact window the benchmark reads, or the
    # comparison silently comes from the wrong dates.
    assert trailed["exit_date"] >= trailed["entry_date"], f"exit before entry: {trailed}"
    assert capped["entry_date"] == runaway["date"].iloc[len(runaway) - 54], "entry date off by one"

    # Frequency odds and money odds must not be confused: this strategy loses
    # more often than it wins and still has positive EV.
    for name in MODES:
        o = mode_odds(name)
        assert o["freq_ratio"] < 1.0, f"{name}: win rate above 50% — check MEASURED_ODDS"
        assert o["money_ratio"] > 1.0, f"{name}: money odds not favourable — {o}"
        assert o["ev"] > 0, f"{name}: negative EV — {o}"
        assert abs(o["money_ratio"] - o["freq_ratio"] * o["payoff"]) < 1e-9, \
            f"{name}: money odds must equal frequency odds x payoff"

    # Buy-and-hold is cheaper than trading, but never free.
    assert buy_hold_net(0.40) < 0.40, "buy-and-hold pays costs too"
    assert buy_hold_net(0.40) > net_return(0.40), "long-term CGT must beat short-term"

    # asof must reach back to the last close at or before a non-trading date.
    idx = pd.Series([100.0, 110.0], index=pd.to_datetime(["2024-01-01", "2024-02-01"]))
    gap = _index_window_return(idx, pd.Timestamp("2024-01-15"), pd.Timestamp("2024-02-15"))
    assert abs(gap - 0.10) < 1e-9, f"asof lookup wrong: {gap}"
    assert _index_window_return(idx, pd.Timestamp("2023-01-01"), pd.Timestamp("2024-02-01")) is None, \
        "a date before the index history must not fabricate a benchmark"
    print("selftest OK")


def main() -> None:
    p = argparse.ArgumentParser(description="Karma Nepse Trading Signal")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_levels(sp):
        sp.add_argument("--mode", choices=[*MODES, "both"], default=DEFAULT_MODE)
        # Unset means "use the mode's own sizing" — see Mode docstring.
        sp.add_argument("--target", type=float, default=None)
        sp.add_argument("--stop", type=float, default=None)
        sp.add_argument("--exit", choices=("trail", "target"), default=DEFAULT_EXIT,
                        dest="exit_style")

    s = sub.add_parser("scan"); add_levels(s); s.add_argument("--top", type=int, default=10)
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("signal"); s.add_argument("ticker"); add_levels(s)
    s.set_defaults(func=cmd_signal)

    s = sub.add_parser("backtest"); add_levels(s)
    s.add_argument("--grid", action="store_true", help="sweep target/stop pairs")
    s.add_argument("--limit", type=int, default=0, help="cap tickers (fast smoke run)")
    s.set_defaults(func=cmd_backtest)

    s = sub.add_parser("tail"); add_levels(s)
    s.add_argument("--split", default="2023-01-01")
    s.add_argument("--limit", type=int, default=0)
    s.set_defaults(func=cmd_tail)

    s = sub.add_parser("tiers"); add_levels(s)
    s.add_argument("--split", default="2023-01-01")
    s.add_argument("--limit", type=int, default=0)
    s.set_defaults(func=cmd_tiers)

    s = sub.add_parser("benchmark"); add_levels(s)
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--since", default=None, help="only trades entered on/after this date")
    s.add_argument("--slots", type=int, default=6, help="concurrent positions your heat cap allows")
    s.set_defaults(func=cmd_benchmark)

    s = sub.add_parser("regime"); add_levels(s)
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--since", default="2023-01-01")
    s.set_defaults(func=cmd_regime)

    s = sub.add_parser("size")
    s.add_argument("--bankroll", type=float, required=True)
    s.add_argument("--risk", type=float, default=0.01, help="bankroll fraction risked per trade")
    s.add_argument("--heat", type=float, default=0.06, help="max total bankroll at risk at once")
    s.add_argument("--mode", choices=list(MODES), default=DEFAULT_MODE)
    s.add_argument("--stop", type=float, default=None)
    s.set_defaults(func=cmd_size)

    s = sub.add_parser("walkforward"); add_levels(s)
    s.add_argument("--split", default="2023-01-01", help="in-sample / out-of-sample boundary")
    s.add_argument("--limit", type=int, default=0)
    s.set_defaults(func=cmd_walkforward)

    s = sub.add_parser("selftest"); s.set_defaults(func=cmd_selftest)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

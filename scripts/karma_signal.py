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
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COMPANY_DIR = DATA_DIR / "company-wise"
NEPSE_INDEX = DATA_DIR / "index" / "nepse" / "history.csv"

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
    out["high250"] = out["high"].rolling(250).max()
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

    gates = {
        # Can you actually get out of a position in this name? NEPSE's tail of
        # illiquid counters shows beautiful charts you cannot sell into.
        "liquidity": bool(r["turnover60"] >= MIN_MEDIAN_TURNOVER),
        # NEPSE is a high-beta single-factor market: most names follow the index.
        "market_regime": bool(regime_ok),
        "uptrend": bool(r["close"] > r["ma50"] > r["ma200"] and r["ma50_slope"] > 0),
        "near_high": bool(r["close"] >= mode.near_high * r["high250"]),
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
            "pct_of_high250": float(r["close"] / r["high250"]),
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
            rows.append(
                {
                    "ticker": t,
                    "mode": mode.name,
                    "score": sig.score,
                    "close": round(sig.close, 1),
                    "stop": round(lv["stop"], 1),
                    "stop%": f"{lv['stop_pct']:.1%}",
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
    print(out.groupby("mode", group_keys=False).head(args.top).to_string(index=False))


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

    s = sub.add_parser("scan"); add_levels(s); s.add_argument("--top", type=int, default=15)
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

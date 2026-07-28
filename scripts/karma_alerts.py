"""Karma Nepse position tracker + Telegram alarm.

Records open positions with their stop/target/time-stop, then checks the
latest bar against those levels and pushes a Telegram message when one trips.

    export KARMA_TELEGRAM_TOKEN=...      # from @BotFather
    export KARMA_TELEGRAM_CHAT_ID=...    # from getUpdates

    python3 scripts/karma_alerts.py open NABIL --mode position
    python3 scripts/karma_alerts.py list
    python3 scripts/karma_alerts.py watch
    python3 scripts/karma_alerts.py close NABIL
    python3 scripts/karma_alerts.py selftest

IMPORTANT — this alarm is only as fresh as `data/company-wise/`. It reads the
last scraped bar, not a live quote. If the daily scraper has not run, `watch`
raises a stale-data warning instead of a false all-clear. Never treat it as a
real-time stop: NEPSE moves 15% in a day, and a day-late stop alarm is worse
than no alarm because it feels like protection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from karma_signal import (  # noqa: E402
    DATA_DIR,
    MAX_STALE_DAYS,
    MODES,
    add_indicators,
    evaluate,
    load_prices,
)

POSITIONS_FILE = DATA_DIR / "karma_positions.json"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
REQUEST_TIMEOUT = 15


# ── Position store (immutable — every writer returns a new list) ─────────────
def load_positions() -> list[dict]:
    if not POSITIONS_FILE.exists():
        return []
    try:
        data = json.loads(POSITIONS_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{POSITIONS_FILE} is corrupt: {exc}. Fix or delete it.") from exc
    if not isinstance(data, list):
        raise SystemExit(f"{POSITIONS_FILE} must contain a list, got {type(data).__name__}.")
    return data


def save_positions(positions: list[dict]) -> None:
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2))


def with_status(positions: list[dict], ticker: str, status: str) -> list[dict]:
    """New list with `ticker`'s open position marked `status`."""
    return [
        {**p, "status": status, "closed": str(date.today())}
        if p["ticker"] == ticker and p["status"] == "open"
        else p
        for p in positions
    ]


# ── Telegram ─────────────────────────────────────────────────────────────────
def send_telegram(text: str) -> bool:
    """Push a message. Returns False (with a printed reason) if it did not go."""
    token = os.environ.get("KARMA_TELEGRAM_TOKEN")
    chat_id = os.environ.get("KARMA_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram not configured (KARMA_TELEGRAM_TOKEN / KARMA_TELEGRAM_CHAT_ID unset).")
        print(f"Would have sent:\n{text}")
        return False
    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        # A silent send failure means a stop trips and nobody hears it.
        print(f"ALERT DELIVERY FAILED: {exc}\nUndelivered message:\n{text}", file=sys.stderr)
        return False
    if not resp.ok:
        print(f"ALERT DELIVERY FAILED: HTTP {resp.status_code} {resp.text}", file=sys.stderr)
        return False
    return True


# ── Commands ─────────────────────────────────────────────────────────────────
def cmd_open(args) -> None:
    ticker = args.ticker.upper()
    mode = MODES[args.mode]
    positions = load_positions()
    if any(p["ticker"] == ticker and p["status"] == "open" for p in positions):
        print(f"{ticker} already has an open position. Close it first.")
        return

    px = load_prices(ticker)
    if px is None:
        print(f"{ticker}: no usable price history.")
        return
    ind = add_indicators(px)
    sig = evaluate(ticker, ind, len(ind) - 1, True, mode)
    if sig is None:
        print(f"{ticker}: indicators not warm.")
        return

    entry = args.entry if args.entry else sig.close
    # ATR-derived stop width from the signal bar, applied to the actual fill.
    stop_pct = sig.levels()["stop_pct"]
    record = {
        "ticker": ticker,
        "mode": mode.name,
        "entry": round(entry, 2),
        "stop": round(entry * (1 - stop_pct), 2),
        "target": round(entry * (1 + mode.target), 2),
        "stop_pct": round(stop_pct, 4),
        "opened": str(args.opened or date.today()),
        "max_hold": mode.max_hold,
        "status": "open",
    }
    save_positions([*positions, record])
    print(json.dumps(record, indent=2))
    if not sig.is_buy:
        failed = [k for k, ok in sig.gates.items() if not ok]
        print(f"\nNote: {ticker} does NOT currently pass the signal. Failed: {', '.join(failed)}")
        print("Recorded anyway — tracking your trade is not the same as endorsing it.")


def cmd_list(_args) -> None:
    positions = load_positions()
    if not positions:
        print("No positions recorded.")
        return
    print(pd.DataFrame(positions).to_string(index=False))


def cmd_close(args) -> None:
    ticker = args.ticker.upper()
    positions = load_positions()
    if not any(p["ticker"] == ticker and p["status"] == "open" for p in positions):
        print(f"No open position in {ticker}.")
        return
    save_positions(with_status(positions, ticker, "closed_manual"))
    print(f"{ticker} marked closed.")


def _check(position: dict, bar: pd.Series, held_days: int) -> tuple[str, str] | None:
    """(status, message) if a level tripped, else None."""
    t, entry = position["ticker"], position["entry"]
    ret = bar["close"] / entry - 1

    # Stop is tested first: a bar that breached both must never report the
    # happier outcome, same tie-break the backtest uses.
    if bar["low"] <= position["stop"]:
        return "stopped", (
            f"🔴 <b>STOP HIT — {t}</b>\n"
            f"Stop {position['stop']:,.1f} breached (low {bar['low']:,.1f}).\n"
            f"Entry {entry:,.1f} → close {bar['close']:,.1f} ({ret:+.1%})\n"
            f"Bar date {bar['date'].date()}. Exit."
        )
    if bar["high"] >= position["target"]:
        return "target", (
            f"🟢 <b>TARGET HIT — {t}</b>\n"
            f"Target {position['target']:,.1f} reached (high {bar['high']:,.1f}).\n"
            f"Entry {entry:,.1f} → close {bar['close']:,.1f} ({ret:+.1%})\n"
            f"Bar date {bar['date'].date()}. Take the profit."
        )
    if held_days >= position["max_hold"]:
        return "timed_out", (
            f"⏱ <b>TIME STOP — {t}</b>\n"
            f"Held {held_days} trading days (max {position['max_hold']}).\n"
            f"Entry {entry:,.1f} → close {bar['close']:,.1f} ({ret:+.1%})\n"
            f"Exit regardless of price. Most trades end here, not at target."
        )
    return None


def cmd_watch(args) -> None:
    positions = load_positions()
    open_positions = [p for p in positions if p["status"] == "open"]
    if not open_positions:
        print("No open positions to watch.")
        return

    updated, alerts = positions, []
    for pos in open_positions:
        px = load_prices(pos["ticker"])
        if px is None:
            print(f"{pos['ticker']}: no price data — cannot check. This is NOT an all-clear.")
            continue

        bar = px.iloc[-1]
        lag = (pd.Timestamp.today().normalize() - bar["date"]).days
        if lag > MAX_STALE_DAYS:
            msg = (
                f"⚠️ <b>STALE DATA — {pos['ticker']}</b>\n"
                f"Last bar {bar['date'].date()} is {lag} days old. Levels NOT checked.\n"
                f"Run the daily scraper. Treat this as no protection, not as safe."
            )
            print(msg)
            alerts.append(msg)
            continue

        held = int((px["date"] > pd.Timestamp(pos["opened"])).sum())
        hit = _check(pos, bar, held)
        if hit:
            status, msg = hit
            updated = with_status(updated, pos["ticker"], status)
            alerts.append(msg)
            print(msg)
        else:
            ret = bar["close"] / pos["entry"] - 1
            print(
                f"{pos['ticker']}: open, {ret:+.1%}, close {bar['close']:,.1f} "
                f"(stop {pos['stop']:,.1f} / target {pos['target']:,.1f}), "
                f"day {held}/{pos['max_hold']}"
            )

    if alerts and not args.dry_run:
        send_telegram("\n\n".join(alerts))
    if updated != positions:
        save_positions(updated)


def cmd_test_telegram(_args) -> None:
    print("Sent." if send_telegram("✅ Karma Nepse alerts wired up correctly.") else "Not sent.")


def cmd_selftest(_args) -> None:
    pos = {"ticker": "TEST", "entry": 100.0, "stop": 90.0, "target": 140.0, "max_hold": 63}

    def bar(low, high, close):
        return pd.Series({"low": low, "high": high, "close": close,
                          "date": pd.Timestamp("2026-07-27")})

    assert _check(pos, bar(89.0, 105.0, 95.0), 5)[0] == "stopped", "stop not detected"
    assert _check(pos, bar(95.0, 141.0, 138.0), 5)[0] == "target", "target not detected"
    assert _check(pos, bar(95.0, 105.0, 100.0), 5) is None, "false alarm on a quiet bar"
    assert _check(pos, bar(95.0, 105.0, 100.0), 63)[0] == "timed_out", "time stop not detected"
    # A bar that breaches both must report the stop, never the happier outcome.
    assert _check(pos, bar(89.0, 141.0, 120.0), 5)[0] == "stopped", "target won an ambiguous bar"

    # Status update must not mutate its input.
    original = [{"ticker": "A", "status": "open"}, {"ticker": "B", "status": "open"}]
    snapshot = json.dumps(original)
    result = with_status(original, "A", "stopped")
    assert json.dumps(original) == snapshot, "with_status mutated its input"
    assert result[0]["status"] == "stopped" and result[1]["status"] == "open", "wrong row updated"
    print("selftest OK")


def main() -> None:
    p = argparse.ArgumentParser(description="Karma Nepse position alarms")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("open"); s.add_argument("ticker")
    s.add_argument("--mode", choices=list(MODES), default="position")
    s.add_argument("--entry", type=float, default=None, help="actual fill price")
    s.add_argument("--opened", default=None, help="entry date YYYY-MM-DD")
    s.set_defaults(func=cmd_open)

    s = sub.add_parser("list"); s.set_defaults(func=cmd_list)
    s = sub.add_parser("close"); s.add_argument("ticker"); s.set_defaults(func=cmd_close)

    s = sub.add_parser("watch")
    s.add_argument("--dry-run", action="store_true", help="print alerts, do not send")
    s.set_defaults(func=cmd_watch)

    s = sub.add_parser("test-telegram"); s.set_defaults(func=cmd_test_telegram)
    s = sub.add_parser("selftest"); s.set_defaults(func=cmd_selftest)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

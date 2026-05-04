#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
nepse_cagr_server.py — Local HTTP server for NEPSE CAGR Extension
Runs on localhost:5758, accepts CAGR calculation requests from the browser extension.
"""

import json, os, sys, re
from datetime import date, datetime, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────
PORT       = 5758
FACE_VALUE = 100
DEFAULT_INVESTMENT = 100_000
DATA_DIR   = Path(__file__).parent / "data"


# ── Data loading ──────────────────────────────────────────────────────────────
def load_prices(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / "company-wise" / symbol.upper() / "prices.csv"
    if not path.exists():
        raise FileNotFoundError(f"prices.csv not found for {symbol}")
    df = pd.read_csv(path, parse_dates=["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    if "ltp" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"ltp": "close"})
    return df


def load_dividends(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / "company-wise" / symbol.upper() / "dividend.csv"
    if not path.exists():
        return pd.DataFrame(columns=["fiscal_year", "bonus_share", "cash_dividend", "total_dividend", "book_closure_date"])
    df = pd.read_csv(path)
    df["book_closure_date"] = df["book_closure_date"].astype(str).str.extract(r"(\d{4}-\d{2}-\d{2})", expand=False)
    df["book_closure_date"] = pd.to_datetime(df["book_closure_date"], format="%Y-%m-%d", errors="coerce")
    df.sort_values("book_closure_date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    for col in ["bonus_share", "cash_dividend", "total_dividend"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
                .replace("", "0").replace("nan", "0")
                .astype(float) / 100.0
            )
    return df


def nearest_price(prices: pd.DataFrame, target_date: date, direction: str = "forward") -> pd.Series:
    prices_dates = prices["date"].dt.date
    if direction == "forward":
        mask = prices_dates >= target_date
        subset = prices[mask]
        if subset.empty:
            subset = prices
        return subset.iloc[0]
    else:
        mask = prices_dates <= target_date
        subset = prices[mask]
        if subset.empty:
            subset = prices
        return subset.iloc[-1]


# ── CAGR calculation ──────────────────────────────────────────────────────────
def calculate_cagr(symbol: str, start_date: date, initial_investment: float) -> dict:
    today = date.today()
    if start_date >= today:
        return {"error": "Start date must be before today."}

    try:
        prices = load_prices(symbol)
    except FileNotFoundError as e:
        return {"error": str(e)}

    dividends = load_dividends(symbol)

    # Initial purchase
    start_row = nearest_price(prices, start_date, direction="forward")
    actual_start_date = start_row["date"].date()
    start_price = float(start_row["close"])
    units = initial_investment / start_price

    # Corporate actions — collect events for display
    total_cash_dividends = 0.0
    events = []

    for _, row in dividends.iterrows():
        action_date = row["book_closure_date"]
        if pd.isna(action_date):
            continue
        action_date = action_date.date()
        if action_date <= actual_start_date or action_date > today:
            continue

        bonus_pct = float(row.get("bonus_share", 0) or 0)
        cash_pct  = float(row.get("cash_dividend", 0) or 0)
        fiscal_yr = str(row.get("fiscal_year", ""))

        if bonus_pct > 0:
            units += units * bonus_pct
            events.append({
                "date": str(action_date),
                "type": "bonus",
                "pct": bonus_pct,
                "fiscal_year": fiscal_yr,
                "units_after": round(units, 4),
                "cash_rs": 0
            })

        if cash_pct > 0:
            cash_rs = units * FACE_VALUE * cash_pct
            total_cash_dividends += cash_rs
            events.append({
                "date": str(action_date),
                "type": "cash",
                "pct": cash_pct,
                "fiscal_year": fiscal_yr,
                "units_after": round(units, 4),
                "cash_rs": round(cash_rs, 2)
            })

    # Current value
    latest_row  = nearest_price(prices, today, direction="backward")
    latest_date = latest_row["date"].date()
    ltp         = float(latest_row["close"])
    market_value = units * ltp
    todays_value = market_value + total_cash_dividends
    years = (latest_date - actual_start_date).days / 365.25
    cagr  = (todays_value / initial_investment) ** (1 / years) - 1

    return {
        "symbol":               symbol.upper(),
        "start_date":           str(actual_start_date),
        "end_date":             str(latest_date),
        "years":                round(years, 4),
        "initial_investment":   initial_investment,
        "start_price":          start_price,
        "units_bought":         round(initial_investment / start_price, 4),
        "total_units_today":    round(units, 4),
        "ltp":                  ltp,
        "market_value":         round(market_value, 2),
        "total_cash_dividends": round(total_cash_dividends, 2),
        "todays_value":         round(todays_value, 2),
        "cagr_pct":             round(cagr * 100, 2),
        "events":               events,
    }


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Silence request logs

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            self._send_json({"status": "ok"})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        if self.path == "/cagr":
            symbol     = body.get("symbol", "").strip().upper()
            investment = float(body.get("investment", DEFAULT_INVESTMENT))
            years      = body.get("years")
            start_date_str = body.get("start_date")

            if not symbol:
                self._send_json({"error": "No symbol provided."})
                return

            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                except ValueError:
                    self._send_json({"error": "Invalid start_date format. Use YYYY-MM-DD."})
                    return
            elif years:
                start_date = date.today() - timedelta(days=int(float(years) * 365.25))
            else:
                self._send_json({"error": "Provide either years or start_date."})
                return

            result = calculate_cagr(symbol, start_date, investment)
            self._send_json(result)
        else:
            self.send_response(404)
            self.end_headers()


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    server = None
    for p in range(PORT, PORT + 10):
        try:
            server = HTTPServer(("localhost", p), Handler)
            PORT = p
            break
        except OSError as e:
            if e.errno == 48:
                continue
            raise

    if not server:
        print(f"❌ Could not bind to any port in range {PORT}-{PORT+9}")
        sys.exit(1)

    print(f"✅ NEPSE CAGR Server running on http://localhost:{PORT}")
    server.serve_forever()

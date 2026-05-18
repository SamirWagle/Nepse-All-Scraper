#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
nepse_cagr_server.py — Local HTTP server for NEPSE CAGR Extension
Runs on localhost:5758, accepts CAGR calculation requests from the browser extension.

POST /cagr
  Body: {"symbol": "NABIL", "years": 5}
     or {"symbol": "NABIL", "start_date": "2020-01-01"}
  Optional: {"end_date": "2023-01-01", "investment": 200000}
  Response: cagr result dict or {"error": "..."}

GET /ping
  Response: {"status": "ok"}
"""

import errno
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── Import core calculation from nepse_cagr.py ───────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from nepse_cagr import (
    calculate_cagr as _core_calculate_cagr,
    load_dividends,
    load_right_shares,
    FACE_VALUE,
    DAYS_PER_YEAR,
)

import pandas as pd
from scraper.core.listing_date import ShareHubListingDateScraper
_listing_scraper = ShareHubListingDateScraper()

# ── Config ────────────────────────────────────────────────────────────────────
PORT               = 5758
DEFAULT_INVESTMENT = 100_000
DATA_DIR           = Path(__file__).parent / "data"

# NEPSE symbols are 1-15 uppercase alphanumeric characters.
# Validated before any filesystem access to prevent path traversal.
_SYMBOL_RE = re.compile(r'^[A-Z0-9]{1,15}$')


# ── Events list builder (server-only, for extension UI display) ───────────────
def _build_events(symbol: str, initial_units: float,
                  actual_start: date, effective_end: date) -> list:
    """
    Reconstruct the chronological corporate-action event list for a symbol.
    Tracks running unit count so every event carries a valid units_after float.
    Used only by the extension popup for display — not part of CAGR maths.
    """
    dividends = load_dividends(symbol, DATA_DIR)
    rights    = load_right_shares(symbol, DATA_DIR)

    actions = []
    for _, row in dividends.iterrows():
        action_date = row["book_closure_date"]
        if pd.isna(action_date):
            continue
        action_date = action_date.date()
        if action_date <= actual_start or action_date > effective_end:
            continue
        actions.append((action_date, "dividend", row))

    for _, row in rights.iterrows():
        action_date = row["closing_date"]
        if pd.isna(action_date):
            continue
        action_date = action_date.date()
        if action_date <= actual_start or action_date > effective_end:
            continue
        actions.append((action_date, "right", row))

    actions.sort(key=lambda x: x[0])

    units  = initial_units
    events = []

    for action_date, action_type, row in actions:
        if action_type == "right":
            ratio_multiplier = float(row.get("ratio_multiplier", 0) or 0)
            units += units * ratio_multiplier
            events.append({
                "date":        str(action_date),
                "type":        "right",
                "ratio":       str(row.get("ratio", "")),
                "issue_price": float(row.get("issue_price", 0)),
                "pct":         0,
                "fiscal_year": "",
                "units_after": round(units, 4),
                "cash_rs":     0,
            })
        elif action_type == "dividend":
            bonus_pct = float(row.get("bonus_share", 0) or 0)
            cash_pct  = float(row.get("cash_dividend", 0) or 0)
            fiscal_yr = str(row.get("fiscal_year", ""))
            # Cash is paid on pre-bonus units (matching nepse_cagr.py ordering)
            if cash_pct > 0:
                cash_rs = round(units * FACE_VALUE * cash_pct, 2)
                events.append({
                    "date":        str(action_date),
                    "type":        "cash",
                    "pct":         cash_pct,
                    "fiscal_year": fiscal_yr,
                    "units_after": round(units, 4),
                    "cash_rs":     cash_rs,
                })
            if bonus_pct > 0:
                units += units * bonus_pct
                events.append({
                    "date":        str(action_date),
                    "type":        "bonus",
                    "pct":         bonus_pct,
                    "fiscal_year": fiscal_yr,
                    "units_after": round(units, 4),
                    "cash_rs":     0,
                })

    return events


# ── NEPSE index CAGR (price-only, no corporate actions) ──────────────────────
def calculate_index_cagr(start_date: date, initial_investment: float,
                         end_date: date = None) -> dict:
    csv_path = DATA_DIR / "index" / "nepse" / "history.csv"
    try:
        df = pd.read_csv(csv_path, parse_dates=["date"])
    except FileNotFoundError:
        return {"error": "NEPSE index history not found"}

    df = df.sort_values("date").reset_index(drop=True)

    today         = date.today()
    effective_end = end_date if (end_date and end_date < today) else today

    start_rows = df[df["date"].dt.date >= start_date]
    if start_rows.empty:
        return {"error": f"No NEPSE data on or after {start_date}"}
    start_row    = start_rows.iloc[0]
    actual_start = start_row["date"].date()
    start_price  = float(start_row["close"])

    end_rows = df[df["date"].dt.date <= effective_end]
    if end_rows.empty:
        return {"error": f"No NEPSE data on or before {effective_end}"}
    end_row    = end_rows.iloc[-1]
    actual_end = end_row["date"].date()
    end_price  = float(end_row["close"])

    years = (actual_end - actual_start).days / DAYS_PER_YEAR
    if years <= 0:
        return {"error": "End date must be after start date"}

    final_value = initial_investment * (end_price / start_price)
    cagr_pct    = ((final_value / initial_investment) ** (1.0 / years) - 1) * 100

    return {
        "symbol":               "NEPSE",
        "is_index":             True,
        "start_date":           str(actual_start),
        "end_date":             str(actual_end),
        "years":                round(years, 2),
        "start_price":          round(start_price, 2),
        "ltp":                  round(end_price, 2),
        "initial_investment":   round(initial_investment, 2),
        "total_invested":       round(initial_investment, 2),
        "units_bought":         0,
        "total_units_today":    0,
        "market_value":         round(final_value, 2),
        "total_cash_dividends": 0,
        "todays_value":         round(final_value, 2),
        "cagr_pct":             round(cagr_pct, 4),
        "events":               [],
    }


# ── Server-facing CAGR wrapper ────────────────────────────────────────────────
def calculate_cagr(symbol: str, start_date: date,
                   initial_investment: float, end_date: date = None) -> dict:
    """
    Thin wrapper around nepse_cagr.calculate_cagr().
    Adds 'events' list for the extension UI. Returns error dict on failure.
    """
    today         = date.today()
    effective_end = end_date if (end_date and end_date < today) else today

    try:
        result = _core_calculate_cagr(
            symbol=symbol,
            start_date=start_date,
            initial_investment=initial_investment,
            data_dir=DATA_DIR,
            verbose=False,
            end_date=effective_end,
        )
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}

    actual_start = result["start_date"]  # date object from core
    result["events"] = _build_events(symbol, result["units_bought"], actual_start, effective_end)
    return result


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Silence request logs

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
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
        elif self.path.startswith("/listing_date"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            symbol = qs.get("symbol", [""])[0].strip().upper()
            if symbol == "NEPSE":
                self._send_json({"symbol": "NEPSE", "listing_date": None})
            elif symbol and _SYMBOL_RE.match(symbol):
                listing_date = _listing_scraper.get(symbol)
                self._send_json({"symbol": symbol, "listing_date": listing_date})
            else:
                self._send_json({"error": "Invalid symbol"})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = 0
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        if self.path == "/cagr":
            symbol     = body.get("symbol", "").strip().upper()
            investment = float(body.get("investment", DEFAULT_INVESTMENT))
            years      = body.get("years")
            start_date_str = body.get("start_date")

            if not symbol or not _SYMBOL_RE.match(symbol):
                self._send_json({"error": "Invalid symbol. Use letters and digits only (e.g. NABIL)."})
                return

            if symbol == "NEPSE":
                if start_date_str:
                    try:
                        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        self._send_json({"error": "Invalid start_date format. Use YYYY-MM-DD."})
                        return
                elif years:
                    start_date = date.today() - timedelta(days=int(float(years) * DAYS_PER_YEAR))
                else:
                    self._send_json({"error": "Provide either years or start_date."})
                    return
                end_date = None
                end_date_str = body.get("end_date")
                if end_date_str:
                    try:
                        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        self._send_json({"error": "Invalid end_date format. Use YYYY-MM-DD."})
                        return
                self._send_json(calculate_index_cagr(start_date, investment, end_date))
                return

            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                except ValueError:
                    self._send_json({"error": "Invalid start_date format. Use YYYY-MM-DD."})
                    return
            elif years:
                start_date = date.today() - timedelta(days=int(float(years) * DAYS_PER_YEAR))
            else:
                self._send_json({"error": "Provide either years or start_date."})
                return

            end_date = None
            end_date_str = body.get("end_date")
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                except ValueError:
                    self._send_json({"error": "Invalid end_date format. Use YYYY-MM-DD."})
                    return

            result = calculate_cagr(symbol, start_date, investment, end_date)
            self._send_json(result)
        else:
            self.send_response(404)
            self.end_headers()


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    server = None
    bound_port = PORT
    for p in range(PORT, PORT + 10):
        try:
            server = ThreadingHTTPServer(("localhost", p), Handler)
            bound_port = p
            break
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                continue
            raise

    if not server:
        print(f"❌ Could not bind to any port in range {PORT}-{PORT+9}")
        sys.exit(1)

    print(f"✅ NEPSE CAGR Server running on http://localhost:{bound_port}")
    server.serve_forever()

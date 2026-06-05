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
import os
import re
import sys
import threading
import time
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
from scraper.core.fundamentals import MerolaganiFundamentalsScraper
_listing_scraper = ShareHubListingDateScraper()
_fundamentals_scraper = MerolaganiFundamentalsScraper()
_merger_meta_cache = None

# ── Known listing dates (overrides scraper data) ───────────────────────────────
LISTING_DATE_OVERRIDES = {
    "SPIL": "2023-04-03",
}

# ── Sub-index ticker aliases → data/index/{slug}/history.csv ──────────────────
INDEX_ALIASES = {
    "NEPSE":             "nepse",
    "NEPSEIND":          "nepse",
    "SENSITIVE":         "sensitive",
    "SENSITIVEIND":      "sensitive",
    "SENSITIVEFLOAT":    "sensitive_float",
    "SFLOAT":            "sensitive_float",
    "SFLOATIND":         "sensitive_float",
    "FLOAT":             "float",
    "FLOATIND":          "float",
    "BANKEX":            "banking",
    "BANKING":           "banking",
    "BANKINGIND":        "banking",
    "DEVBANKEX":         "development_bank",
    "DEVBANK":           "development_bank",
    "DEVBANKIND":        "development_bank",
    "FINEX":             "finance",
    "FINANCE":           "finance",
    "FINANCEIND":        "finance",
    "HOTLEX":            "hotels_tourism",
    "HOTEL":             "hotels_tourism",
    "HOTELIND":          "hotels_tourism",
    "HYDROEX":           "hydropower",
    "HYDRO":             "hydropower",
    "HYDROIND":          "hydropower",
    "HYDROPOWERIND":     "hydropower",
    "HYDROPOWIND":       "hydropower",
    "INSURE":            "insurance",
    "INSURANCE":         "insurance",
    "INSURANCEIND":      "insurance",
    "INVEST":            "investment",
    "INVESTMENT":        "investment",
    "INVESTMENTIND":     "investment",
    "LIFEINSURE":        "life_insurance",
    "LIFEINSURANCE":     "life_insurance",
    "LIFEINSURANCEIND":  "life_insurance",
    "LIFEINSUIND":       "life_insurance",
    "LIFEIND":           "life_insurance",
    "MANUIND":           "manufacturing",
    "MANUFACTUREIND":    "manufacturing",
    "MANUFACTURING":     "manufacturing",
    "MANUFACTURINGIND":  "manufacturing",
    "MICROEX":           "microfinance",
    "MICROFINANCE":      "microfinance",
    "MICROFINANCEIND":   "microfinance",
    "MFEX":              "mutual_fund",
    "MUTUALFUND":        "mutual_fund",
    "MUTUALFUNDIND":     "mutual_fund",
    "NONLIFEINSURE":     "non_life_insurance",
    "NONLIFEINSURANCE":  "non_life_insurance",
    "NONLIFEIND":        "non_life_insurance",
    "OTHERS":            "others",
    "OTHERSIND":         "others",
    "TRADING":           "trading",
    "TRADINGIND":        "trading",
}

INDEX_DISPLAY_NAMES = {
    "nepse":              "NEPSE",
    "sensitive":          "Sensitive Index",
    "sensitive_float":    "Sensitive Float Index",
    "float":              "Float Index",
    "banking":            "Banking SubIndex",
    "development_bank":   "Development Bank Index",
    "finance":            "Finance Index",
    "hotels_tourism":     "Hotels & Tourism",
    "hydropower":         "HydroPower Index",
    "insurance":          "Insurance",
    "investment":         "Investment",
    "life_insurance":     "Life Insurance",
    "manufacturing":      "Manufacturing & Processing",
    "microfinance":       "Microfinance Index",
    "mutual_fund":        "Mutual Fund",
    "non_life_insurance": "Non Life Insurance",
    "others":             "Others Index",
    "trading":            "Trading Index",
}

def _load_merger_meta() -> dict:
    global _merger_meta_cache
    if _merger_meta_cache is not None:
        return _merger_meta_cache
    path = Path(__file__).parent / "data" / "company_mergers.json"
    if not path.exists():
        _merger_meta_cache = {}
        return _merger_meta_cache
    try:
        raw = json.loads(path.read_text())
        if isinstance(raw, dict) and "entries" in raw and isinstance(raw["entries"], dict):
            _merger_meta_cache = raw["entries"]
        elif isinstance(raw, dict):
            _merger_meta_cache = raw
        else:
            _merger_meta_cache = {}
    except Exception:
        _merger_meta_cache = {}
    return _merger_meta_cache

def get_merger_info(symbol: str) -> dict | None:
    info = _load_merger_meta().get(symbol.upper())
    return info if isinstance(info, dict) else None

def resolve_final_survivor(symbol: str) -> dict | None:
    """Walk the merger chain to the terminal surviving entity still trading.

    Many NEPSE symbols merged in multiple steps (e.g. BOK -> BOKL -> GBIME).
    Returns {"symbol", "name", "chain"} of the final survivor, or None if the
    given symbol did not merge. The final survivor is the last symbol in the
    chain that has no further merger entry.
    """
    meta = _load_merger_meta()
    info = meta.get(symbol.upper())
    if not isinstance(info, dict):
        return None

    chain = []
    seen = {symbol.upper()}
    from_info = info  # entity that merges INTO the next hop (carries the merge date)
    final_symbol = from_info.get("surviving_symbol") or from_info.get("merged_into")
    final_name = from_info.get("surviving_name") or from_info.get("merged_into_name")

    while final_symbol and final_symbol.upper() not in seen:
        seen.add(final_symbol.upper())
        # Date of this hop = merge date of the entity that merged into final_symbol.
        chain.append({
            "symbol": final_symbol,
            "name": final_name,
            "merged_date": from_info.get("merged_date"),
        })
        nxt = meta.get(final_symbol.upper())
        if not isinstance(nxt, dict) or nxt.get("status") != "closed":
            break  # terminal: not in chain or still trading
        from_info = nxt
        final_symbol = nxt.get("surviving_symbol") or nxt.get("merged_into")
        final_name = nxt.get("surviving_name") or nxt.get("merged_into_name")

    if not chain:
        return None
    return {
        "symbol": chain[-1]["symbol"],
        "name": chain[-1]["name"],
        "chain": chain,
    }

# ── Company search ────────────────────────────────────────────────────────────
_companies_cache: list | None = None

def _load_companies() -> list:
    global _companies_cache
    if _companies_cache is not None:
        return _companies_cache

    data_dir = Path(__file__).parent / "data"
    mapping_path = data_dir / "company_id_mapping.json"
    names_path = data_dir / "company_names.json"
    companies_csv = data_dir / "companies.csv"

    mapping = {}
    names = {}
    if mapping_path.exists():
        try:
            mapping = json.loads(mapping_path.read_text())
        except Exception:
            mapping = {}
    if names_path.exists():
        try:
            names = json.loads(names_path.read_text())
        except Exception:
            names = {}

    companies = []
    seen = set()

    # Primary source: full mapping, including merged/delisted companies.
    for sym in sorted(mapping.keys()):
        name = names.get(sym)
        if not name and companies_csv.exists():
            try:
                df = pd.read_csv(companies_csv)
                match = df[df["symbol"].astype(str).str.upper() == sym]
                if not match.empty:
                    name = str(match.iloc[0]["name"])
            except Exception:
                pass
        companies.append({"symbol": sym, "name": name or sym})
        seen.add(sym)

    # Backfill any names that exist in company_names.json but not mapping.
    for sym, name in names.items():
        if sym not in seen:
            companies.append({"symbol": sym, "name": name or sym})
            seen.add(sym)

    _companies_cache = companies
    return _companies_cache

def search_companies(q: str, max_results: int = 10, offset: int = 0) -> list:
    """Return companies matching q by exact ticker, ticker prefix, or name substring."""
    q_up = q.strip().upper()
    q_low = q.strip().lower()
    q_norm = re.sub(r'[^a-z0-9]+', '', q_low)
    q_tokens = [t for t in re.split(r'[^a-z0-9]+', q_low) if t]
    companies = _load_companies()

    exact = [c for c in companies if c["symbol"] == q_up]
    if exact:
        return exact

    scored = []
    for idx, c in enumerate(companies):
        symbol = c["symbol"]
        name_low = c["name"].lower()
        name_norm = re.sub(r'[^a-z0-9]+', '', name_low)
        name_tokens = [t for t in re.split(r'[^a-z0-9]+', name_low) if t]
        token_match = any(
            any(nt.startswith(qt) or qt.startswith(nt) for nt in name_tokens)
            for qt in q_tokens
        ) if q_tokens else False
        name_exact = q_low == name_low
        name_sub = q_low in name_low
        name_norm_match = bool(q_norm and q_norm in name_norm)
        symbol_prefix = symbol.startswith(q_up)
        symbol_sub = q_up in symbol

        score = None
        if name_exact:
          score = 0
        elif name_sub:
          score = 1
        elif name_norm_match:
          score = 2
        elif token_match:
          score = 3
        elif symbol == q_up:
          score = 4
        elif symbol_prefix:
          score = 5
        elif symbol_sub:
          score = 6

        if score is not None:
          scored.append((score, idx, c))

    scored.sort(key=lambda t: (t[0], t[1]))
    results = []
    seen = set()
    for _, _, c in scored:
        sym = c["symbol"]
        if sym in seen:
            continue
        seen.add(sym)
        results.append(c)
    return results[offset:offset + max_results]

# ── Config ────────────────────────────────────────────────────────────────────
PORT               = 5758
DEFAULT_INVESTMENT = 100_000
DATA_DIR           = Path(__file__).parent / "data"

# NEPSE symbols are 1-15 uppercase alphanumeric characters.
# Validated before any filesystem access to prevent path traversal.
_SYMBOL_RE = re.compile(r'^[A-Z0-9]{1,20}$')


def _load_interest_rates() -> dict:
    """Read data/interest_rates/fd_rates.csv → {"rates": [...]}.

    Each row: {date, rate (float), metric, source}. Returns sorted by date.
    Fails soft to an empty list if the file is missing or unreadable.
    """
    import csv as _csv
    path = DATA_DIR / "interest_rates" / "fd_rates.csv"
    if not path.exists():
        return {"rates": []}
    try:
        with open(path, newline="") as f:
            rows = list(_csv.DictReader(f))
        parsed = []
        for r in rows:
            try:
                parsed.append({
                    "date": r.get("date", ""),
                    "rate": float(r.get("rate", "") or 0),
                    "metric": r.get("metric", ""),
                    "source": r.get("source", ""),
                })
            except (ValueError, TypeError):
                continue
        parsed.sort(key=lambda x: x["date"])
        return {"rates": parsed}
    except Exception:
        return {"rates": []}


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


# ── Index CAGR (price-only, no corporate actions) ────────────────────────────
def calculate_index_cagr(start_date: date, initial_investment: float,
                         end_date: date = None, index_slug: str = "nepse") -> dict:
    csv_path = DATA_DIR / "index" / index_slug / "history.csv"
    display_name = INDEX_DISPLAY_NAMES.get(index_slug, index_slug.upper())
    try:
        df = pd.read_csv(csv_path, parse_dates=["date"])
    except FileNotFoundError:
        return {"error": f"{display_name} index history not found"}

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
        return {"error": f"No {display_name} data on or before {effective_end}"}
    end_row    = end_rows.iloc[-1]
    actual_end = end_row["date"].date()
    end_price  = float(end_row["close"])

    years = (actual_end - actual_start).days / DAYS_PER_YEAR
    if years <= 0:
        return {"error": "End date must be after start date"}

    final_value = initial_investment * (end_price / start_price)
    cagr_pct    = ((final_value / initial_investment) ** (1.0 / years) - 1) * 100

    return {
        "symbol":               display_name,
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


def get_company_trading_range(symbol: str) -> dict:
    """Return first and last available trading dates for a company, if present."""
    csv_path = DATA_DIR / "company-wise" / symbol / "prices.csv"
    if not csv_path.exists():
        return {"symbol": symbol, "first_date": None, "last_date": None}
    try:
        df = pd.read_csv(csv_path, usecols=["date"])
        if df.empty:
          return {"symbol": symbol, "first_date": None, "last_date": None}
        dates = sorted(str(d).split(" ")[0] for d in df["date"].dropna().tolist())
        return {"symbol": symbol, "first_date": dates[0], "last_date": dates[-1]}
    except Exception:
        return {"symbol": symbol, "first_date": None, "last_date": None}


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
        elif self.path == "/quit":
            self._send_json({"status": "shutting_down"})
            threading.Thread(target=lambda: (time.sleep(0.2), os._exit(0)), daemon=True).start()
        elif self.path.startswith("/trading_range"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            symbol = qs.get("symbol", [""])[0].strip().upper()
            if symbol and _SYMBOL_RE.match(symbol):
                if symbol in INDEX_ALIASES:
                    slug = INDEX_ALIASES[symbol]
                    csv_path = DATA_DIR / "index" / slug / "history.csv"
                    try:
                        df = pd.read_csv(csv_path, usecols=["date"])
                        dates = sorted(df["date"].dropna().tolist())
                        self._send_json({"symbol": symbol, "first_date": dates[0], "last_date": dates[-1]})
                    except Exception:
                        self._send_json({"symbol": symbol, "first_date": None, "last_date": None})
                else:
                    self._send_json(get_company_trading_range(symbol))
            else:
                self._send_json({"error": "Invalid symbol"})
        elif self.path.startswith("/price"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            symbol = qs.get("symbol", [""])[0].strip().upper()
            date_str = qs.get("date", [""])[0].strip()
            if not symbol or not _SYMBOL_RE.match(symbol):
                self._send_json({"error": "Invalid symbol"})
            elif not date_str:
                self._send_json({"error": "Missing date parameter (YYYY-MM-DD)"})
            else:
                try:
                    lookup_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    self._send_json({"error": "Invalid date format. Use YYYY-MM-DD."})
                    return
                try:
                    if symbol in INDEX_ALIASES:
                        slug = INDEX_ALIASES[symbol]
                        csv_path = DATA_DIR / "index" / slug / "history.csv"
                    else:
                        csv_path = DATA_DIR / "company-wise" / symbol / "prices.csv"
                    df = pd.read_csv(csv_path, parse_dates=["date"]).sort_values("date")
                    before = df[df["date"].dt.date <= lookup_date]
                    if before.empty:
                        self._send_json({"error": f"No price data on or before {date_str} for {symbol}"})
                    else:
                        row = before.iloc[-1]
                        price_col = "close" if "close" in row.index else "ltp"
                        self._send_json({
                            "symbol": symbol,
                            "requested_date": date_str,
                            "actual_date": str(row["date"].date()),
                            "close": round(float(row[price_col]), 2),
                        })
                except FileNotFoundError:
                    self._send_json({"error": f"No price data found for {symbol}"})
                except Exception as ex:
                    self._send_json({"error": str(ex)})
        elif self.path.startswith("/search"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            q = qs.get("q", [""])[0].strip()
            if not q:
                self._send_json({"error": "Missing q parameter"})
            else:
                try:
                    max_results = max(1, min(50, int(qs.get("max_results", ["10"])[0])))
                except (TypeError, ValueError):
                    max_results = 10
                try:
                    offset = max(0, int(qs.get("offset", ["0"])[0]))
                except (TypeError, ValueError):
                    offset = 0
                self._send_json({"results": search_companies(q, max_results=max_results, offset=offset)})
        elif self.path.startswith("/listing_date"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            symbol = qs.get("symbol", [""])[0].strip().upper()
            if symbol == "NEPSE":
                self._send_json({"symbol": "NEPSE", "listing_date": None})
            elif symbol and _SYMBOL_RE.match(symbol):
                # Check overrides first
                if symbol in LISTING_DATE_OVERRIDES:
                    listing_date = LISTING_DATE_OVERRIDES[symbol]
                else:
                    listing_date = _listing_scraper.get(symbol)
                self._send_json({"symbol": symbol, "listing_date": listing_date})
            else:
                self._send_json({"error": "Invalid symbol"})
        elif self.path.startswith("/fundamentals"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            symbol = qs.get("symbol", [""])[0].strip().upper()
            force = qs.get("force", ["0"])[0] in ("1", "true", "yes")
            if not symbol or not _SYMBOL_RE.match(symbol):
                self._send_json({"error": "Invalid symbol"})
            else:
                data = _fundamentals_scraper.get(symbol, force_refresh=force)
                if "listing_date" not in data:
                    if symbol in LISTING_DATE_OVERRIDES:
                        data["listing_date"] = LISTING_DATE_OVERRIDES[symbol]
                    else:
                        try:
                            data["listing_date"] = _listing_scraper.get(symbol)
                        except Exception:
                            data["listing_date"] = None
                merger_info = get_merger_info(symbol)
                if merger_info:
                    data["merger"] = merger_info
                    status = merger_info.get("status", "closed")
                    data["is_merged"] = status == "closed"
                    data["merge_status"] = status
                    data["event_type"] = merger_info.get("event_type")
                    data["merged_date"] = merger_info.get("merged_date")
                    data["merged_to"] = merger_info.get("merged_into") or merger_info.get("merged_to")
                    data["merged_to_name"] = merger_info.get("merged_into_name") or merger_info.get("merged_to_name")
                    data["merged_note"] = merger_info.get("note")
                    data["merged_from"] = merger_info.get("merged_from")
                    data["merged_from_name"] = merger_info.get("merged_from_name")
                    data["surviving_symbol"] = merger_info.get("surviving_symbol")
                    data["surviving_name"] = merger_info.get("surviving_name")
                    final = resolve_final_survivor(symbol)
                    if final:
                        data["final_survivor_symbol"] = final["symbol"]
                        data["final_survivor_name"] = final["name"]
                        data["final_survivor_date"] = final["chain"][-1].get("merged_date")
                        data["merger_chain"] = final["chain"]
                # Attach latest day OHLC from local prices.csv
                try:
                    csv_path = DATA_DIR / "company-wise" / symbol / "prices.csv"
                    if csv_path.exists():
                        df = pd.read_csv(csv_path)
                        if len(df) > 0:
                            row = df.iloc[0]
                            data["latest_day"] = {
                                "date": str(row.get("date", "")),
                                "open": float(row.get("open", 0) or 0),
                                "high": float(row.get("high", 0) or 0),
                                "low": float(row.get("low", 0) or 0),
                                "ltp": float(row.get("ltp", 0) or 0),
                                "qty": float(row.get("qty", 0) or 0),
                                "turnover": float(row.get("turnover", 0) or 0),
                            }
                except Exception:
                    pass
                self._send_json(data)
        elif self.path == "/mergers":
            self._send_json({"version": 1, "entries": _load_merger_meta()})
        elif self.path == "/interest_rates":
            self._send_json(_load_interest_rates())
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

            if symbol in INDEX_ALIASES:
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
                self._send_json(calculate_index_cagr(start_date, investment, end_date, INDEX_ALIASES[symbol]))
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

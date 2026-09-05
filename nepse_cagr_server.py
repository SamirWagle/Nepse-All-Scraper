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

import base64
import errno
import json
import os
import re
import sys
import threading
import time
from html import escape as html_escape
from urllib.parse import quote
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
    FACE_VALUE_OVERRIDES,
    DAYS_PER_YEAR,
    LISTING_DATES,
)

import pandas as pd
from instrument_type import is_equity
from scraper.core.listing_date import ShareHubListingDateScraper
from scraper.core.fundamentals import MerolaganiFundamentalsScraper
_listing_scraper = ShareHubListingDateScraper()
_fundamentals_scraper = MerolaganiFundamentalsScraper()
_merger_meta_cache = None
_ceo_directory_cache = None

# ── Known listing dates (overrides scraper data) ───────────────────────────────
LISTING_DATE_OVERRIDES = {
    "SPIL": "2023-04-03",
    "SBL": "2006-02-24",
    "SRLI": "2023-05-18",
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

def _load_ceo_directory() -> dict:
    global _ceo_directory_cache
    if _ceo_directory_cache is not None:
        return _ceo_directory_cache
    path = Path(__file__).parent / "data" / "ceo_directory.csv"
    directory = {}
    if path.exists():
        import csv
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ticker = (row.get("ticker") or "").strip().upper()
                if ticker:
                    directory[ticker] = row.get("ceo_name", "").strip()
    _ceo_directory_cache = directory
    return _ceo_directory_cache

def get_ceo_name(symbol: str) -> str | None:
    return _load_ceo_directory().get(symbol.upper()) or None

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

    def _add(sym: str, name: str | None) -> None:
        """Register an ordinary share; skip debentures, bonds, funds, promoter shares."""
        label = name or sym
        if not is_equity(label):
            return
        companies.append({"symbol": sym, "name": label})
        seen.add(sym)

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
        _add(sym, name)

    # Backfill any names that exist in company_names.json but not mapping.
    for sym, name in names.items():
        if sym not in seen:
            _add(sym, name)

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

def _load_ceo_mapping() -> dict:
    p = DATA_DIR / "ceo_mapping.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

_CEO_MAPPING: dict = _load_ceo_mapping()

# NEPSE symbols are 1-15 uppercase alphanumeric characters.
# Validated before any filesystem access to prevent path traversal.
_SYMBOL_RE = re.compile(r'^[A-Z0-9]{1,20}$')

SCREENSHOTS_DIR = DATA_DIR / "screenshots"
# Bare filename only — blocks path traversal (../) same as the karma_signal history route.
_SCREENSHOT_FILENAME_RE = re.compile(r'^[\w .()-]+\.(?:png|jpe?g|gif|webp)$', re.IGNORECASE)
_SCREENSHOT_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}


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


BUBBLE_PERIOD_DAYS = {
    "1d": 1, "1w": 7, "1m": 30,
    "1y": 365, "2y": 730, "3y": 1095, "4y": 1460, "5y": 1825,
    "6y": 2190, "7y": 2555, "8y": 2920, "9y": 3285,
    "10y": 3650, "11y": 4015, "12y": 4380,
}


BUBBLE_TOP_N = 75


def get_bubbles_data(period: str) -> list:
    """Total return % (or annualized CAGR/XIRR) + market cap, for the bubble map.

    Price-only % change is misleading whenever bonus shares, cash dividends,
    or rights fell inside the window (see CIT: heavy bonus dilution pushes
    the raw price down over a decade while a holder's actual total return is
    positive). So every window runs the same bonus/dividend/rights-adjusted
    engine the CAGR calculator uses (nepse_cagr.calculate_cagr, XIRR when
    rights are involved):
      - <=1y windows show the *raw* total return over that window (not
        annualized — annualizing a 1-day move is nonsensical).
      - >1y windows show the annualized CAGR/XIRR.
    Only run over the top-N by market cap since the adjusted engine is much
    heavier than a raw price lookup.
    """
    days = BUBBLE_PERIOD_DAYS.get(period, BUBBLE_PERIOD_DAYS["1m"])
    use_annualized = days > 365

    candidates = []
    for c in _load_companies():
        symbol = c["symbol"]
        csv_path = DATA_DIR / "company-wise" / symbol / "prices.csv"
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path, usecols=["date", "ltp"], parse_dates=["date"])
        except Exception:
            continue
        df = df.dropna(subset=["date", "ltp"]).sort_values("date")
        if df.empty:
            continue
        last_date = df.iloc[-1]["date"]
        last_price = float(df.iloc[-1]["ltp"])
        if last_price <= 0:
            continue
        target_date = last_date - pd.Timedelta(days=days)
        past = df[df["date"] <= target_date]
        if past.empty:
            continue
        past_price = float(past.iloc[-1]["ltp"])
        if past_price <= 0:
            continue

        market_cap = None
        fpath = DATA_DIR / "company-wise" / symbol / "fundamentals.json"
        if fpath.exists():
            try:
                market_cap = json.loads(fpath.read_text()).get("market_cap")
            except Exception:
                market_cap = None

        candidates.append({
            "symbol": symbol,
            "name": c["name"],
            "price": round(last_price, 2),
            "pct_change": round((last_price / past_price - 1) * 100, 2),
            "market_cap": market_cap,
            "last_date": last_date,
            "target_date": target_date,
        })

    candidates.sort(key=lambda r: -(r["market_cap"] or 0))
    candidates = candidates[:BUBBLE_TOP_N]

    results = []
    for r in candidates:
        display_pct = r["pct_change"]
        try:
            cagr_result = calculate_cagr(
                symbol=r["symbol"],
                start_date=r["target_date"].date(),
                initial_investment=100_000,
                end_date=r["last_date"].date(),
            )
            if "error" not in cagr_result:
                if use_annualized:
                    display_pct = cagr_result.get("xirr_pct", cagr_result.get("cagr_pct"))
                else:
                    total_invested = cagr_result["total_invested"]
                    display_pct = (cagr_result["todays_value"] / total_invested - 1) * 100
                display_pct = round(display_pct, 2)
        except Exception:
            pass  # fall back to raw price % change for this symbol

        results.append({
            "symbol": r["symbol"],
            "name": r["name"],
            "price": r["price"],
            "pct_change": r["pct_change"],
            "cagr_pct": display_pct,
            "is_cagr": use_annualized,
            "market_cap": r["market_cap"],
            "last_date": str(r["last_date"].date()),
        })
    return results


def build_adjusted_series(symbol: str, df: pd.DataFrame) -> list:
    """Bonus/right/cash-adjusted wealth-index series for a company.

    Returns a list of {date, close} where `close` is the value of a holding
    that started as 1 unit at the first price, accumulating bonus + right
    units and cash dividends over time. Anchored so the first point equals
    the first raw price, then diverges upward as corporate actions accrue —
    making the line visually match the CAGR (total-return) story.

    Cash dividends mirror nepse_cagr.calculate_cagr: declared on units held
    BEFORE that year's bonus, not reinvested (added as a cash component).
    Right-share cost is ignored here (rights add units only); fine for STC
    which has none, and a small approximation otherwise.
    """
    face_value = FACE_VALUE_OVERRIDES.get(symbol.upper(), FACE_VALUE)

    # Build a date-sorted action list: (date, kind, payload)
    actions = []
    for _, row in load_dividends(symbol, DATA_DIR).iterrows():
        d = row.get("book_closure_date")
        if pd.isna(d):
            continue
        actions.append((d.date(), "dividend", row))
    for _, row in load_right_shares(symbol, DATA_DIR).iterrows():
        d = row.get("closing_date")
        if pd.isna(d):
            continue
        actions.append((d.date(), "right", row))
    actions.sort(key=lambda a: a[0])

    units = 1.0
    cum_cash = 0.0
    ai = 0  # pointer into sorted actions

    points = []
    for d, c in zip(df["date"], df[df.attrs["price_col"]]):
        if pd.isna(c):
            continue
        row_date = d.date()
        # Apply all corporate actions on or before this price date.
        while ai < len(actions) and actions[ai][0] <= row_date:
            _, kind, payload = actions[ai]
            if kind == "right":
                units += units * float(payload["ratio_multiplier"])
            else:  # dividend
                cash_pct = float(payload.get("cash_dividend", 0) or 0)
                bonus_pct = float(payload.get("bonus_share", 0) or 0)
                if cash_pct > 0:
                    cum_cash += units * face_value * cash_pct
                if bonus_pct > 0:
                    units += units * bonus_pct
            ai += 1
        value = units * float(c) + cum_cash
        points.append({"date": str(row_date), "close": round(value, 2)})

    return points


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


# ── News digest cache helpers ─────────────────────────────────────────────────
# The news scan runs nightly from cron; these let the HTTP handler tell
# "already scanned tonight" from "the cron never ran".
NEWS_CRON_HOUR = 22  # must match the crontab entry for scripts/nepse_news.py


def _last_news_scan() -> datetime | None:
    """Timestamp of the last completed scan, or None if none ever ran."""
    marker = Path(__file__).parent / "output" / "news_last_scan.json"
    if not marker.exists():
        return None
    try:
        return datetime.fromisoformat(json.loads(marker.read_text())["timestamp"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def _last_scheduled_news_run() -> datetime:
    """The most recent moment the cron should have fired (today's 22:00, or
    yesterday's if it's not 22:00 yet)."""
    now = datetime.now()
    today = now.replace(hour=NEWS_CRON_HOUR, minute=0, second=0, microsecond=0)
    return today if now >= today else today - timedelta(days=1)


def _load_dismissed_news_urls() -> set[str]:
    store = Path(__file__).parent / "output" / "news_dismissed.json"
    if not store.exists():
        return set()
    try:
        return set(json.loads(store.read_text()).get("urls", []))
    except (json.JSONDecodeError, OSError):
        return set()


_NEWS_SECTION_RE = re.compile(
    r'(<details class="sect"[^>]*><summary>.*?<span class="cnt">)(\d+)'
    r'(</span>.*?<tbody>)(.*?)(</tbody>.*?</details>)',
    re.DOTALL,
)
_NEWS_ROW_RE = re.compile(r"<tr>.*?</tr>", re.DOTALL)


def _apply_dismissed_to_report(doc: str, dismissed: set[str]) -> str:
    """Hide dismissed rows at serve time instead of mutating the cached
    report file — so undo works for free (the row is just still in the
    file, only re-hidden while its url stays in the dismissed set) and a
    stale page reload can't resurrect something already marked read."""
    if not dismissed:
        return doc
    escaped = {html_escape(u) for u in dismissed}

    def repl(match: re.Match) -> str:
        pre, _cnt, mid, rows_html, tail = match.groups()
        rows = _NEWS_ROW_RE.findall(rows_html)
        kept = [r for r in rows if not any(f"href='{u}'" in r for u in escaped)]
        return f"{pre}{len(kept)}{mid}{''.join(kept)}{tail}"

    return _NEWS_SECTION_RE.sub(repl, doc)


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

    def _send_html(self, body_str, status=200):
        body = body_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

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
        elif self.path.startswith("/bubbles"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            period = qs.get("period", ["1m"])[0].strip().lower()
            if period not in BUBBLE_PERIOD_DAYS:
                self._send_json({"error": f"Invalid period. Use one of: {', '.join(BUBBLE_PERIOD_DAYS)}"})
            else:
                self._send_json({"period": period, "data": get_bubbles_data(period)})
        elif self.path.startswith("/series"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            symbol = qs.get("symbol", [""])[0].strip().upper()
            adjusted = qs.get("adjusted", ["0"])[0] in ("1", "true", "yes")
            if not symbol or not _SYMBOL_RE.match(symbol):
                self._send_json({"error": "Invalid symbol"})
            else:
                try:
                    is_index = symbol in INDEX_ALIASES
                    if is_index:
                        slug = INDEX_ALIASES[symbol]
                        csv_path = DATA_DIR / "index" / slug / "history.csv"
                    else:
                        csv_path = DATA_DIR / "company-wise" / symbol / "prices.csv"
                    df = pd.read_csv(csv_path, parse_dates=["date"]).sort_values("date")
                    # Clip to known listing date so the overlay doesn't show
                    # a pre-listing entity's price history (e.g. KBL before 2017).
                    if not is_index:
                        listing = LISTING_DATES.get(symbol)
                        if listing is not None:
                            df = df[df["date"].dt.date >= listing]
                    price_col = "close" if "close" in df.columns else "ltp"
                    # Indices have no corporate actions — adjusted == raw.
                    if adjusted and not is_index:
                        df.attrs["price_col"] = price_col
                        points = build_adjusted_series(symbol, df)
                    else:
                        points = [
                            {"date": str(d.date()), "close": round(float(c), 2)}
                            for d, c in zip(df["date"], df[price_col])
                            if pd.notna(c)
                        ]
                    self._send_json({"symbol": symbol, "points": points, "adjusted": adjusted and not is_index})
                except FileNotFoundError:
                    self._send_json({"error": f"No price data found for {symbol}"})
                except Exception as ex:
                    self._send_json({"error": str(ex)})
        elif self.path == "/btc_series":
            try:
                df = pd.read_csv(DATA_DIR / "btc" / "history.csv")
                points = [
                    {"date": str(d), "close": float(c)}
                    for d, c in zip(df["date"], df["close"])
                    if pd.notna(c)
                ]
                self._send_json({"symbol": "BTC-USD", "points": points})
            except FileNotFoundError:
                self._send_json({"error": "No BTC data — run scraper/btc_scraper.py"})
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
                if symbol in LISTING_DATE_OVERRIDES:
                    data["listing_date"] = LISTING_DATE_OVERRIDES[symbol]
                elif "listing_date" not in data:
                    try:
                        data["listing_date"] = _listing_scraper.get(symbol)
                    except Exception:
                        data["listing_date"] = None
                if not data.get("ceo"):
                    data["ceo"] = get_ceo_name(symbol)
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
                # Build absorbed-entities lists for surviving companies (M&A card)
                all_merger_entries = _load_merger_meta()
                absorbed_mergers = []
                absorbed_acquisitions = []
                for k, v in all_merger_entries.items():
                    if not isinstance(v, dict):
                        continue
                    if v.get("status") != "closed":
                        continue
                    target = (v.get("surviving_symbol") or v.get("merged_into") or "").upper()
                    if target != symbol:
                        continue
                    event_type = (v.get("event_type") or "merger").lower()
                    entry = {
                        "entity": v.get("display_name") or k,
                        "symbol": k,
                        "date": v.get("merged_date"),
                        "status": "Completed",
                    }
                    if event_type == "acquisition":
                        absorbed_acquisitions.append(entry)
                    else:
                        absorbed_mergers.append(entry)
                if absorbed_mergers:
                    absorbed_mergers.sort(key=lambda x: x.get("date") or "")
                    data["mergers"] = absorbed_mergers
                if absorbed_acquisitions:
                    absorbed_acquisitions.sort(key=lambda x: x.get("date") or "")
                    data["acquisitions"] = absorbed_acquisitions
                # Shiller P/E (CAPE) — current price / avg(eps, up to 10 years)
                # Reads from eps_history.csv which accumulates yearly EPS per symbol.
                import csv as _csv
                eps_csv = DATA_DIR / "company-wise" / symbol / "eps_history.csv"
                price = data.get("market_price")
                if price and eps_csv.exists():
                    try:
                        with open(eps_csv, newline="") as _f:
                            rows = [
                                (r["fiscal_year"], float(r["eps"]))
                                for r in _csv.DictReader(_f)
                                if r.get("eps") and float(r["eps"]) > 0
                            ]
                        rows.sort(key=lambda x: x[0])
                        recent = [e for _, e in rows[-10:]]
                        if recent:
                            data["shiller_pe"] = round(price / (sum(recent) / len(recent)), 2)
                            data["shiller_pe_years"] = len(recent)
                    except Exception:
                        pass
                # Historical PE band — this company's own PE at each fiscal
                # year-end across its full price/EPS history (see scripts/schiller_pe.py).
                try:
                    import statistics as _statistics
                    from scripts.schiller_pe import historical_pe_series as _hist_pe_series, PE_OUTLIER_CAP as _PE_CAP
                    hist = _hist_pe_series(symbol)
                    hist_pes = [h["pe"] for h in hist if h["pe"] <= _PE_CAP]
                    if hist_pes:
                        data["historical_pe_avg"] = round(_statistics.mean(hist_pes), 2)
                        data["historical_pe_median"] = round(_statistics.median(hist_pes), 2)
                        data["historical_pe_min"] = round(min(hist_pes), 2)
                        data["historical_pe_max"] = round(max(hist_pes), 2)
                        data["historical_pe_years"] = len(hist_pes)
                except Exception:
                    pass
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
                ceo = _CEO_MAPPING.get(symbol)
                if ceo:
                    data["ceo"] = ceo
                self._send_json(data)
        elif self.path.startswith("/verdict"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            symbol = qs.get("symbol", [""])[0].strip().upper()
            if not symbol or not _SYMBOL_RE.match(symbol):
                self._send_json({"error": "Invalid symbol"})
            else:
                verdict_path = DATA_DIR / "company-wise" / symbol / "verdict.json"
                if verdict_path.exists():
                    self._send_json(json.loads(verdict_path.read_text()))
                else:
                    self._send_json({"error": "No verdict on file for this symbol"}, status=404)
        elif self.path == "/mergers":
            self._send_json({"version": 1, "entries": _load_merger_meta()})
        elif self.path == "/interest_rates":
            self._send_json(_load_interest_rates())
        elif self.path == "/screenshots":
            files = []
            if SCREENSHOTS_DIR.is_dir():
                for p in SCREENSHOTS_DIR.iterdir():
                    if p.is_file() and _SCREENSHOT_FILENAME_RE.match(p.name):
                        files.append((p.stat().st_mtime, p.name))
            files.sort(reverse=True)
            self._send_json({"files": [
                {"name": name, "url": f"/screenshots/file/{quote(name)}"}
                for _, name in files
            ]})
        elif self.path.startswith("/screenshots/file/"):
            from urllib.parse import unquote
            filename = unquote(self.path[len("/screenshots/file/"):])
            if not _SCREENSHOT_FILENAME_RE.match(filename):
                self._send_json({"error": "Invalid screenshot filename"}, status=400)
            else:
                fpath = SCREENSHOTS_DIR / filename
                if fpath.is_file():
                    mime = _SCREENSHOT_MIME.get(fpath.suffix.lower(), "application/octet-stream")
                    self._send_bytes(fpath.read_bytes(), mime)
                else:
                    self._send_json({"error": "Screenshot not found"}, status=404)
        elif self.path.startswith("/karma_signal/history/"):
            filename = self.path[len("/karma_signal/history/"):]
            # Only bare filenames matching the archiver's own naming pattern —
            # blocks path traversal (../) and anything outside output/history/.
            if not re.fullmatch(r"[\w.-]+\.html", filename):
                self._send_json({"error": "Invalid history filename"}, status=400)
            else:
                history_path = Path(__file__).parent / "output" / "history" / filename
                if history_path.is_file():
                    self._send_html(history_path.read_text(encoding="utf-8"))
                else:
                    self._send_json({"error": "Snapshot report not found"}, status=404)
        elif self.path == "/karma_signal":
            # ponytail: fixed argv, no user input — nothing to inject.
            import subprocess
            try:
                proc = subprocess.run(
                    [sys.executable, str(Path(__file__).parent / "scripts" / "karma_signal.py"),
                     "scan", "--mode", "both"],
                    capture_output=True, text=True, timeout=600,
                )
                # The scan archives a styled report and repoints latest.html at
                # it; hand that straight to the page instead of the text dump.
                report = Path(__file__).parent / "output" / "latest.html"
                self._send_json({
                    "output": proc.stdout,
                    "html": report.read_text(encoding="utf-8") if report.exists() else None,
                    "error": proc.stderr.strip() or None,
                    "returncode": proc.returncode,
                })
            except subprocess.TimeoutExpired:
                self._send_json({"error": "karma_signal scan timed out after 600s"}, status=504)
            except Exception as ex:
                self._send_json({"error": str(ex)}, status=500)
        elif self.path.startswith("/nepse_news/dismiss") or \
                self.path.startswith("/nepse_news/undismiss"):
            from urllib.parse import urlparse, parse_qs
            undo = self.path.startswith("/nepse_news/undismiss")
            target = parse_qs(urlparse(self.path).query).get("url", [""])[0]
            self._toggle_news_dismissed(target, undo=undo)
        elif self.path.startswith("/nepse_news/delete"):
            # Confirm page only — the deletion itself is a POST, so a browser
            # prefetching this link can't destroy an archive.
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            filename = qs.get("file", [""])[0]
            if not re.fullmatch(r"[\w.-]+\.html", filename):
                self._send_json({"error": "Invalid snapshot filename"}, status=400)
            else:
                safe = html_escape(filename)
                self._send_html(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Delete snapshot</title><style>
body{{background:#121212;color:#e6e6e6;font-family:-apple-system,sans-serif;
padding:40px;max-width:620px;margin:0 auto}}
.warn{{background:#1b1b1b;border:1px solid #a33;border-radius:10px;padding:20px}}
code{{color:#e0a76c}} button{{background:#a33;color:#fff;border:0;border-radius:8px;
padding:10px 18px;font-size:14px;cursor:pointer}}
a{{color:#7fb8ff;margin-left:16px}}</style></head><body>
<div class="warn"><h2>Delete this snapshot permanently?</h2>
<p><code>{safe}</code></p>
<p>This removes the archived report from disk and drops its row from the
snapshot list. It is the only stored copy of that digest &mdash; any
newsletter links it held go with it. This cannot be undone.</p>
<form method="POST" action="/nepse_news/delete">
<input type="hidden" name="file" value="{safe}">
<button type="submit">Delete permanently</button>
<a href="javascript:window.close()">Cancel</a>
</form></div></body></html>""")
        elif self.path.startswith("/nepse_news/history/"):
            filename = self.path[len("/nepse_news/history/"):]
            if not re.fullmatch(r"[\w.-]+\.html", filename):
                self._send_json({"error": "Invalid history filename"}, status=400)
            else:
                history_path = Path(__file__).parent / "output" / "news_history" / filename
                if history_path.is_file():
                    self._send_html(history_path.read_text(encoding="utf-8"))
                else:
                    self._send_json({"error": "Snapshot report not found"}, status=404)
        elif self.path.startswith("/nepse_news"):
            # The scan is heavy (Firecrawl calls + dozens of fetches), so the
            # 22:00 cron owns it and the button normally just reads that
            # result back. A fresh scan runs only when the cron didn't —
            # machine asleep, say — and then only covers the gap since the
            # last one. `?force=1` (the Re-run button) always rescans.
            import subprocess
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            force = qs.get("force", ["0"])[0] == "1"
            report = Path(__file__).parent / "output" / "news_latest.html"
            last_scan = _last_news_scan()

            if not force and last_scan and last_scan >= _last_scheduled_news_run() and report.exists():
                dismissed = _load_dismissed_news_urls()
                html_out = _apply_dismissed_to_report(report.read_text(encoding="utf-8"), dismissed)
                self._send_json({
                    "html": html_out,
                    "cached": True,
                    "last_scan": last_scan.isoformat(),
                })
                return

            # Cover only the gap since the last successful scan so a missed
            # night doesn't silently drop a day of news; fall back to 24h on
            # a first run, and cap at a week so a long absence can't ask for
            # an unbounded lookback.
            hours = 24
            if last_scan:
                gap = (datetime.now() - last_scan).total_seconds() / 3600
                hours = max(24, min(int(gap) + 1, 168))
            try:
                proc = subprocess.run(
                    [sys.executable, str(Path(__file__).parent / "scripts" / "nepse_news.py"),
                     "scan", "--hours", str(hours)],
                    capture_output=True, text=True, timeout=900,
                )
                html_out = None
                if report.exists():
                    dismissed = _load_dismissed_news_urls()
                    html_out = _apply_dismissed_to_report(report.read_text(encoding="utf-8"), dismissed)
                self._send_json({
                    "output": proc.stdout,
                    "html": html_out,
                    "error": proc.stderr.strip() or None,
                    "returncode": proc.returncode,
                    "cached": False,
                    "lookback_hours": hours,
                })
            except subprocess.TimeoutExpired:
                self._send_json({"error": "nepse_news scan timed out after 900s"}, status=504)
            except Exception as ex:
                self._send_json({"error": str(ex)}, status=500)
        else:
            self.send_response(404)
            self.end_headers()

    def _toggle_news_dismissed(self, target: str, *, undo: bool) -> None:
        """Hide a digest item once read, or put it back.

        Reversible by design, which is why this is safe on a GET: the worst a
        stray prefetch can do is hide a headline, and the reply carries the
        link to undo it.
        """
        if not target.startswith(("http://", "https://")):
            self._send_json({"error": "Invalid item URL"}, status=400)
            return
        store = Path(__file__).parent / "output" / "news_dismissed.json"
        urls = []
        if store.exists():
            try:
                urls = json.loads(store.read_text()).get("urls", [])
            except (json.JSONDecodeError, OSError):
                urls = []
        if undo:
            urls = [u for u in urls if u != target]
        elif target not in urls:
            urls.append(target)
        store.write_text(json.dumps({"urls": urls}, indent=2))

        safe = html_escape(target)
        back = "dismiss" if undo else "undismiss"
        label = "Restored" if undo else "Marked as read"
        verb = "hide it again" if undo else "undo"
        self._send_html(f"""<!doctype html><html><head><meta charset="utf-8">
<title>{label}</title><style>
body{{background:#121212;color:#e6e6e6;font-family:-apple-system,sans-serif;
padding:40px;max-width:620px;margin:0 auto}}
.ok{{background:#1b1b1b;border:1px solid #2a2a2a;border-radius:10px;padding:20px}}
a{{color:#7fb8ff}} .u{{color:#8a8a8a;font-size:12px;word-break:break-all}}
.hint{{color:#7a7a7a;font-size:12px}}
</style></head><body><div class="ok">
<h2>{label}</h2>
<p class="u">{safe}</p>
<p>It is now {'visible again' if undo else 'hidden from the digest'}. Hidden items
stay hidden across future scans until restored.</p>
<p><a href="/nepse_news/{back}?url={quote(target, safe='')}">Click to {verb}</a></p>
<p class="hint">You normally never see this page &mdash; the digest hides items
in place. It shows up when the link is opened on its own, so close this tab
(or go back) to return to the digest.</p>
<p><a href="javascript:history.back()">&larr; Back</a>
   <a href="javascript:window.close()" style="margin-left:16px">Close tab</a></p>
</div></body></html>""")

    def _delete_news_snapshot(self, filename: str) -> None:
        """Remove one archived digest and its snapshot row. Irreversible."""
        if not re.fullmatch(r"[\w.-]+\.html", filename):
            self._send_json({"error": "Invalid snapshot filename"}, status=400)
            return
        out_dir = Path(__file__).parent / "output"
        archive = out_dir / "news_history" / filename
        # Resolve and re-check: the regex already blocks traversal, but the
        # containment check is what actually guarantees we delete inside
        # news_history/ and nowhere else.
        try:
            archive = archive.resolve()
            archive.relative_to((out_dir / "news_history").resolve())
        except (ValueError, OSError):
            self._send_json({"error": "Refusing to delete outside news_history"}, status=400)
            return

        removed_file = False
        if archive.is_file():
            archive.unlink()
            removed_file = True

        snap_file = out_dir / "news_snapshots.json"
        removed_rows = 0
        if snap_file.exists():
            try:
                snapshots = json.loads(snap_file.read_text())
                kept = [s for s in snapshots if s.get("file") != filename]
                removed_rows = len(snapshots) - len(kept)
                if removed_rows:
                    snap_file.write_text(json.dumps(kept, indent=2))
            except (json.JSONDecodeError, OSError) as ex:
                self._send_json({"error": f"Snapshot index update failed: {ex}"}, status=500)
                return

        safe = html_escape(filename)
        self._send_html(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Snapshot deleted</title><style>
body{{background:#121212;color:#e6e6e6;font-family:-apple-system,sans-serif;
padding:40px;max-width:620px;margin:0 auto}}
.ok{{background:#1b1b1b;border:1px solid #2a2a2a;border-radius:10px;padding:20px}}
code{{color:#e0a76c}}</style></head><body><div class="ok">
<h2>{'Deleted' if removed_file or removed_rows else 'Nothing to delete'}</h2>
<p><code>{safe}</code></p>
<p>Archive file removed: <strong>{str(removed_file).lower()}</strong><br>
Snapshot rows removed: <strong>{removed_rows}</strong></p>
<p>Reopen the digest and press Snapshots to see the updated list.</p>
<p><a href="javascript:window.close()" style="color:#7fb8ff">Close tab</a></p>
</div></body></html>""")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = 0
        raw = self.rfile.read(length) if length else b""

        # Form-encoded, not JSON — handled before the JSON parse below.
        if self.path == "/nepse_news/delete":
            from urllib.parse import parse_qs
            filename = parse_qs(raw.decode("utf-8")).get("file", [""])[0]
            self._delete_news_snapshot(filename)
            return

        body = json.loads(raw.decode("utf-8")) if raw else {}

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
        elif self.path == "/screenshots/upload":
            raw_name = os.path.basename(body.get("filename", ""))
            data_b64 = body.get("data", "")
            if not raw_name or not _SCREENSHOT_FILENAME_RE.match(raw_name):
                self._send_json({"error": "Filename must end in .png, .jpg, .jpeg, .gif, or .webp"}, status=400)
                return
            try:
                img_bytes = base64.b64decode(data_b64, validate=True)
            except Exception:
                self._send_json({"error": "Invalid base64 image data"}, status=400)
                return

            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            stem, ext = os.path.splitext(raw_name)
            dest = SCREENSHOTS_DIR / raw_name
            n = 1
            while dest.exists():
                dest = SCREENSHOTS_DIR / f"{stem}-{n}{ext}"
                n += 1
            dest.write_bytes(img_bytes)
            self._send_json({"name": dest.name, "url": f"/screenshots/file/{quote(dest.name)}"})
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

"""
build_api.py
============
Converts CSV data into a static JSON "API" served by GitHub Pages.

Output: docs/
  index.html              -- Swagger UI
  openapi.json            -- OpenAPI 3.1 spec
  api/
    companies.json        -- list of all tracked symbols
    latest.json           -- last-day snapshot for every symbol
    prices/{SYMBOL}.json
    dividends/{SYMBOL}.json
    right-shares/{SYMBOL}.json
    floorsheet/index.json -- list of dates + raw-CSV URLs
"""
import csv
import json
import os
from pathlib import Path
from datetime import date as dt_date

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COMPANY_WISE = DATA / "company-wise"
FLOORSHEET = DATA / "floorsheet"
INDICES = DATA / "indices"
DOCS = ROOT / "docs"
API = DOCS / "api"

# Repo info for raw CSV links (override via env in CI).
GH_USER = os.environ.get("GH_USER", "SamirWagle")
GH_REPO = os.environ.get("GH_REPO", "Nepse-All-Scraper")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")
RAW_BASE = f"https://raw.githubusercontent.com/{GH_USER}/{GH_REPO}/{GH_BRANCH}"


def safe_slug(symbol: str) -> str:
    """Match the on-disk dir name (slashes -> dashes)."""
    return symbol.replace("/", "-")


def csv_to_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def build_companies():
    """Return sorted symbol list — unify priority list with on-disk dirs."""
    list_path = DATA / "company_list.json"
    with open(list_path) as f:
        priority = set(json.load(f))
    on_disk = {d.name.replace("-", "/") if d.name.replace("-", "/") in priority else d.name
               for d in COMPANY_WISE.iterdir() if d.is_dir()}
    return sorted(priority | on_disk)


def build_per_symbol(symbols):
    """Convert each company's CSVs to JSON. Returns latest-price snapshot dict."""
    latest = {}
    for sym in symbols:
        slug = safe_slug(sym)
        sym_dir = COMPANY_WISE / slug
        if not sym_dir.exists():
            continue

        prices = csv_to_records(sym_dir / "prices.csv")
        if prices:
            write_json(API / "prices" / f"{slug}.json",
                       {"symbol": sym, "count": len(prices), "data": prices})
            latest[sym] = prices[-1] if prices else None

        divs = csv_to_records(sym_dir / "dividend.csv")
        if divs:
            write_json(API / "dividends" / f"{slug}.json",
                       {"symbol": sym, "count": len(divs), "data": divs})

        rights = csv_to_records(sym_dir / "right-share.csv")
        if rights:
            write_json(API / "right-shares" / f"{slug}.json",
                       {"symbol": sym, "count": len(rights), "data": rights})
    return latest


def build_indices():
    """Convert data/indices/*.csv to JSON. Returns latest snapshot dict."""
    if not INDICES.exists():
        return [], {}

    # Read slug -> human name mapping
    name_by_slug = {}
    meta = INDICES / "_index_names.csv"
    if meta.exists():
        for row in csv_to_records(meta):
            name_by_slug[row["slug"]] = row["name"]

    listing = []
    latest = {}
    for f in sorted(INDICES.glob("*.csv")):
        if f.name.startswith("_"):
            continue
        slug = f.stem
        rows = csv_to_records(f)
        if not rows:
            continue
        name = name_by_slug.get(slug, slug.replace("-", " ").title())
        write_json(API / "indices" / f"{slug}.json",
                   {"slug": slug, "name": name, "count": len(rows), "data": rows})
        listing.append({"slug": slug, "name": name, "rows": len(rows),
                        "first_date": rows[0]["date"], "last_date": rows[-1]["date"]})
        latest[slug] = {"name": name, **rows[-1]}

    write_json(API / "indices" / "list.json", listing)
    write_json(API / "indices" / "latest.json", latest)
    return listing, latest


def build_floorsheet_index():
    """List of available dates + raw-CSV URLs (CSVs not copied — too heavy for Pages)."""
    if not FLOORSHEET.exists():
        return []
    entries = []
    for f in sorted(FLOORSHEET.glob("floorsheet_*.csv")):
        date = f.stem.replace("floorsheet_", "")
        entries.append({
            "date": date,
            "csv_url": f"{RAW_BASE}/data/floorsheet/{f.name}",
            "size_bytes": f.stat().st_size,
        })
    return entries


def build_openapi(symbol_count: int, floorsheet_dates: list[str]):
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "NEPSE All Scraper API",
            "version": "1.0.0",
            "description": (
                f"Free, static JSON API for {symbol_count} NEPSE-listed companies. "
                "Updated every weekday after market close. Backed by flat files on GitHub Pages — "
                "no auth, no rate limits, CDN-cached.\n\n"
                "**Note:** Symbols with `/` (e.g. `GBILD86/87`) use `-` in URLs (`GBILD86-87`) "
                "because filesystems don't allow `/` in folder names."
            ),
            "contact": {"url": f"https://github.com/{GH_USER}/{GH_REPO}"},
            "license": {"name": "Educational use"},
        },
        "servers": [{"url": "./api"}],
        "paths": {
            "/companies.json": {
                "get": {
                    "summary": "List all tracked symbols",
                    "responses": {"200": {
                        "description": "Array of symbol strings",
                        "content": {"application/json": {"schema": {
                            "type": "array", "items": {"type": "string"},
                            "example": ["ADBL", "NABIL", "NICA"]
                        }}}
                    }}
                }
            },
            "/latest.json": {
                "get": {
                    "summary": "Last-day price snapshot for every company",
                    "responses": {"200": {
                        "description": "Map of symbol -> latest OHLC row",
                        "content": {"application/json": {"schema": {"type": "object"}}}
                    }}
                }
            },
            "/prices/{symbol}.json": {
                "get": {
                    "summary": "Full OHLC price history for a symbol",
                    "parameters": [{
                        "name": "symbol", "in": "path", "required": True,
                        "schema": {"type": "string"},
                        "example": "ADBL",
                        "description": "Stock ticker. For symbols with `/` use `-` (e.g. `GBILD86-87`)."
                    }],
                    "responses": {
                        "200": {"description": "OHLC history"},
                        "404": {"description": "Symbol not found or no price data"}
                    }
                }
            },
            "/dividends/{symbol}.json": {
                "get": {
                    "summary": "Dividend history",
                    "parameters": [{
                        "name": "symbol", "in": "path", "required": True,
                        "schema": {"type": "string"}, "example": "ADBL"
                    }],
                    "responses": {"200": {"description": "Dividend records"}}
                }
            },
            "/right-shares/{symbol}.json": {
                "get": {
                    "summary": "Right-share issuance history",
                    "parameters": [{
                        "name": "symbol", "in": "path", "required": True,
                        "schema": {"type": "string"}, "example": "NABIL"
                    }],
                    "responses": {"200": {"description": "Right-share records"}}
                }
            },
            "/indices/list.json": {
                "get": {
                    "summary": "All available NEPSE indices (main + sub-indices)",
                    "description": "List of slugs with first/last dates and row counts. Slugs feed `/indices/{slug}.json`.",
                    "responses": {"200": {"description": "Array of {slug, name, rows, first_date, last_date}"}}
                }
            },
            "/indices/latest.json": {
                "get": {
                    "summary": "Latest-day value for every index (NEPSE, Sensitive, Banking, Hydro, etc.)",
                    "responses": {"200": {"description": "Map slug -> {name, date, current, point_change, percent_change, turnover}"}}
                }
            },
            "/indices/{slug}.json": {
                "get": {
                    "summary": "Daily history for one index",
                    "parameters": [{
                        "name": "slug", "in": "path", "required": True,
                        "schema": {"type": "string"},
                        "example": "nepse",
                        "description": "Index slug. Common values: `nepse`, `sensitive`, `float`, `sensitive-float`, `banking`, `hydropower`, `finance`, `development-bank`, `manufacturing-and-processing`, `microfinance`, `mutual-fund`, `life-insurance`, `non-life-insurance`, `hotels-and-tourism`, `investment`, `trading`, `others`. See `/indices/list.json` for full list."
                    }],
                    "responses": {"200": {"description": "Daily index history"}}
                }
            },
            "/snapshots/today.json": {
                "get": {
                    "summary": "Today's market snapshot — top gainers/losers/turnover/volume in one file",
                    "responses": {"200": {"description": "Snapshot object with all top-N lists"}}
                }
            },
            "/snapshots/top-gainers.json": {
                "get": {
                    "summary": "Top 20 gainers (by percent change) for the latest trading day",
                    "responses": {"200": {"description": "Array of {symbol, ltp, percent_change, qty, turnover, date}"}}
                }
            },
            "/snapshots/top-losers.json": {
                "get": {"summary": "Top 20 losers", "responses": {"200": {"description": "Array of rows"}}}
            },
            "/snapshots/top-turnover.json": {
                "get": {"summary": "Top 20 by daily turnover (NPR)", "responses": {"200": {"description": "Array of rows"}}}
            },
            "/snapshots/top-volume.json": {
                "get": {"summary": "Top 20 by daily share volume", "responses": {"200": {"description": "Array of rows"}}}
            },
            "/status.json": {
                "get": {
                    "summary": "Scrape health & coverage snapshot",
                    "description": "Last scrape date, symbol counts, coverage %. Shields.io-compatible endpoint format.",
                    "responses": {"200": {"description": "Status object"}}
                }
            },
            "/floorsheet/index.json": {
                "get": {
                    "summary": "List of available floorsheet dates with raw-CSV download URLs",
                    "description": (
                        "Floorsheet files are large (~70k rows/day, ~10MB each). "
                        "We expose them as raw CSVs hosted on github.com to keep Pages light. "
                        "Use the `csv_url` from each entry to download."
                    ),
                    "responses": {"200": {
                        "description": "Array of {date, csv_url, size_bytes}",
                        "content": {"application/json": {"example": [{
                            "date": floorsheet_dates[0] if floorsheet_dates else "2026-05-04",
                            "csv_url": f"{RAW_BASE}/data/floorsheet/floorsheet_2026-05-04.csv",
                            "size_bytes": 8_700_000,
                        }]}}
                    }}
                }
            },
        }
    }


SWAGGER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>NEPSE All Scraper — API Docs</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
  <style>body{margin:0}.topbar{display:none}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => SwaggerUIBundle({
      url: "./openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      layout: "BaseLayout",
    });
  </script>
</body>
</html>
"""


def build_snapshots(latest):
    """Top-N snapshots derived from latest-day OHLC. No new scraping needed."""
    def _f(v, default=0.0):
        try: return float(str(v).replace(",", "").replace("%", "").strip())
        except (ValueError, AttributeError): return default

    rows = []
    for sym, r in latest.items():
        if not r: continue
        rows.append({
            "symbol": sym,
            "ltp": _f(r.get("ltp")),
            "percent_change": _f(r.get("percent_change")),
            "qty": _f(r.get("qty")),
            "turnover": _f(r.get("turnover")),
            "date": r.get("date"),
        })

    # Snapshot is "for the latest market date" — keep only rows from that date with qty>0.
    snapshot_date = max((r["date"] for r in rows if r["date"]), default=None)
    traded = [r for r in rows if r["qty"] > 0 and r["date"] == snapshot_date]

    return {
        "date": snapshot_date,
        "top_gainers":      sorted(traded, key=lambda r: -r["percent_change"])[:20],
        "top_losers":       sorted(traded, key=lambda r:  r["percent_change"])[:20],
        "top_turnover":     sorted(traded, key=lambda r: -r["turnover"])[:20],
        "top_volume":       sorted(traded, key=lambda r: -r["qty"])[:20],
        "traded_count":     len(traded),
        "untraded_count":   len(rows) - len(traded),
    }


def build_status(symbols, latest, fs, dividend_count, rights_count):
    """Health snapshot — drives shields.io endpoint badges."""
    today = str(dt_date.today())
    coverage_pct = round(100 * len(latest) / max(len(symbols), 1), 1)
    return {
        "schemaVersion": 1,  # shields.io endpoint contract
        "label": "data",
        "message": f"{len(symbols)} symbols · {today}",
        "color": "blue",
        "scrape_date": today,
        "symbols_total": len(symbols),
        "symbols_with_prices": len(latest),
        "symbols_with_dividends": dividend_count,
        "symbols_with_right_shares": rights_count,
        "floorsheet_days": len(fs),
        "floorsheet_latest": fs[-1]["date"] if fs else None,
        "coverage_pct": coverage_pct,
    }


def main():
    print(f"Building static API to {DOCS}/")
    DOCS.mkdir(parents=True, exist_ok=True)
    API.mkdir(parents=True, exist_ok=True)

    symbols = build_companies()
    print(f"  symbols: {len(symbols)}")
    write_json(API / "companies.json", symbols)

    print("  building per-symbol JSON...")
    latest = build_per_symbol(symbols)
    write_json(API / "latest.json", latest)
    print(f"  latest snapshot: {len(latest)} symbols with prices")

    fs = build_floorsheet_index()
    write_json(API / "floorsheet" / "index.json", fs)
    print(f"  floorsheet dates: {len(fs)}")

    idx_list, idx_latest = build_indices()
    print(f"  indices: {len(idx_list)} indices, latest snapshot: {len(idx_latest)}")

    snapshot = build_snapshots(latest)
    write_json(API / "snapshots" / "today.json", snapshot)
    write_json(API / "snapshots" / "top-gainers.json", snapshot["top_gainers"])
    write_json(API / "snapshots" / "top-losers.json", snapshot["top_losers"])
    write_json(API / "snapshots" / "top-turnover.json", snapshot["top_turnover"])
    write_json(API / "snapshots" / "top-volume.json", snapshot["top_volume"])
    print(f"  snapshots: {snapshot['traded_count']} traded, {snapshot['untraded_count']} untraded ({snapshot['date']})")

    div_count = sum(1 for _ in (API / "dividends").glob("*.json")) if (API / "dividends").exists() else 0
    rights_count = sum(1 for _ in (API / "right-shares").glob("*.json")) if (API / "right-shares").exists() else 0

    status = build_status(symbols, latest, fs, div_count, rights_count)
    write_json(API / "status.json", status)

    spec = build_openapi(len(symbols), [e["date"] for e in fs])
    write_json(DOCS / "openapi.json", spec)

    (DOCS / "index.html").write_text(SWAGGER_HTML, encoding="utf-8")

    # CNAME / .nojekyll so Pages doesn't run jekyll on numeric folder names.
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Done. {len(symbols)} symbols, {len(latest)} with prices, {len(fs)} floorsheet days.")
    print(f"      dividends: {div_count}, right-shares: {rights_count}")


if __name__ == "__main__":
    main()

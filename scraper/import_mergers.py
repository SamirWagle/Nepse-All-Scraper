#!/usr/bin/env python3
"""
Import merger announcements into data/company_mergers.json.

Supported input formats:
  - JSON: {"entries": {...}} or a flat symbol->entry dict
  - CSV: symbol,status,merged_date,merged_into,...

This tool is intentionally generic so you can keep a single registry file
up to date as you discover more merged/delisted companies.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REGISTRY_PATH = DATA_DIR / "company_mergers.json"


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"version": 1, "entries": {}}
    data = json.loads(REGISTRY_PATH.read_text())
    if "entries" not in data:
        return {"version": 1, "entries": data}
    return data


def normalize_entry(row: dict[str, str]) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    for key, value in row.items():
        if value is None:
            continue
        value = value.strip()
        if not value:
            continue
        entry[key.strip()] = value
    return entry


def import_csv(path: Path, registry: dict[str, Any]) -> dict[str, Any]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = normalize_entry(row)
            symbol = row.pop("symbol", "").upper()
            if not symbol:
                continue
            registry["entries"][symbol] = row
    return registry


def import_json(path: Path, registry: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(path.read_text())
    entries = data.get("entries", data)
    for symbol, entry in entries.items():
        registry["entries"][symbol.upper()] = entry
    return registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Import merger registry data.")
    parser.add_argument("source", help="CSV or JSON file containing merger metadata")
    parser.add_argument("--out", default=str(REGISTRY_PATH), help="Output registry path")
    args = parser.parse_args()

    source = Path(args.source)
    registry = load_registry()

    if source.suffix.lower() == ".csv":
        registry = import_csv(source, registry)
    elif source.suffix.lower() == ".json":
        registry = import_json(source, registry)
    else:
        raise SystemExit("Input must be .csv or .json")

    out_path = Path(args.out)
    out_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False))
    print(f"Saved merger registry to {out_path}")


if __name__ == "__main__":
    main()

"""Flight-movement store: one CSV per month under data/flights/, de-duplicated."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from . import config
from .aerodatabox import FIELDS
from .reference import fill_airport

BOOL_FIELDS = ("is_cargo", "is_international")


def _key(r: dict) -> tuple:
    return (r["date"], r["direction"], r["flight_no"] or r.get("aircraft_reg", ""), r.get("sched_local", "")[:16])


def _path(month: str, base: Path | None = None) -> Path:
    return (base or config.FLIGHTS_DIR) / f"{month}.csv"


def _norm(r: dict) -> dict:
    out = {k: r.get(k, "") for k in FIELDS}
    for b in BOOL_FIELDS:
        v = out[b]
        out[b] = v if isinstance(v, bool) else str(v).strip().lower() in ("true", "1", "yes")
    return fill_airport(out)


def load_month(month: str, base: Path | None = None) -> list[dict]:
    p = _path(month, base)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return [_norm(r) for r in csv.DictReader(f)]


def load_all(base: Path | None = None) -> list[dict]:
    d = base or config.FLIGHTS_DIR
    rows: list[dict] = []
    for p in sorted(d.glob("*.csv")):
        rows.extend(load_month(p.stem, d))
    return rows


def upsert(rows: Iterable[dict], base: Path | None = None) -> int:
    """Insert or update rows; later data (e.g. actual times, final status) replaces earlier."""
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("date"):
            by_month[r["date"][:7]].append(_norm(r))
    changed = 0
    for month, new_rows in by_month.items():
        existing = {_key(r): r for r in load_month(month, base)}
        for r in new_rows:
            k = _key(r)
            if existing.get(k) != r:
                existing[k] = r
                changed += 1
        p = _path(month, base)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for r in sorted(existing.values(), key=lambda x: (x["date"], x["sched_local"], x["direction"])):
                w.writerow(r)
    return changed

"""Aggregations over flight movements and AAI monthly traffic."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Iterable

from . import config
from .reference import DEFAULT_SEATS, seats_for

CANCELLED = {"canceled", "cancelled", "canceleduncertain", "diverted"}


def is_operated(r: dict) -> bool:
    return (r.get("status") or "").replace(" ", "").lower() not in CANCELLED


def _num(v) -> float | None:
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip().replace("T", " ")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            return None


def delay_minutes(r: dict) -> float | None:
    sched = _parse_dt(r.get("sched_local", ""))
    act = _parse_dt(r.get("actual_local", "") or r.get("revised_local", ""))
    if not sched or not act:
        return None
    if (sched.tzinfo is None) != (act.tzinfo is None):
        sched, act = sched.replace(tzinfo=None), act.replace(tzinfo=None)
    return (act - sched).total_seconds() / 60.0


def seats(r: dict) -> int:
    return seats_for(r.get("aircraft_model")) or DEFAULT_SEATS


# ---------------------------------------------------------------- load factor calibration
def calibrate_load_factor(flights: list[dict], monthly: dict[str, dict]) -> dict:
    """Implied load factor = AAI passengers / estimated seats, for months with near-complete flight data."""
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in flights:
        by_month[r["date"][:7]].append(r)
    result = {}
    for m, rows in by_month.items():
        pax = _num(monthly.get(m, {}).get("pax_total"))
        days = len({r["date"] for r in rows})
        if not pax or days < 25:
            continue
        seat_sum = sum(seats(r) for r in rows if is_operated(r) and not r["is_cargo"])
        if seat_sum:
            lf = pax / seat_sum
            if 0.3 <= lf <= 1.05:  # reject implausible values (data gaps)
                result[m] = round(lf, 3)
    return result


def current_load_factor(cal: dict) -> tuple[float, str]:
    if cal:
        recent = [cal[m] for m in sorted(cal)[-3:]]
        return round(mean(recent), 3), f"calibrated from AAI ({', '.join(sorted(cal)[-3:])})"
    return config.DEFAULT_LOAD_FACTOR, "assumed default (no AAI month to calibrate yet)"


# ---------------------------------------------------------------- flight aggregations
def summarize(rows: Iterable[dict], lf: float) -> dict:
    rows = list(rows)
    op = [r for r in rows if is_operated(r)]
    pax_rows = [r for r in op if not r["is_cargo"]]
    delays = [d for d in (delay_minutes(r) for r in op) if d is not None]
    seat_sum = sum(seats(r) for r in pax_rows)
    return {
        "movements": len(op),
        "arrivals": sum(r["direction"] == "arrival" for r in op),
        "departures": sum(r["direction"] == "departure" for r in op),
        "cargo": sum(r["is_cargo"] for r in op),
        "international": sum(r["is_international"] for r in op),
        "domestic": sum(not r["is_international"] for r in op),
        "cancelled": len(rows) - len(op),
        "est_seats": seat_sum,
        "est_pax": round(seat_sum * lf),
        "on_time_pct": round(100 * sum(d <= 15 for d in delays) / len(delays), 1) if delays else None,
        "avg_delay_min": round(mean(delays), 1) if delays else None,
    }


def group_by(rows: list[dict], keyfn) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        g[keyfn(r)].append(r)
    return dict(g)


def iso_week(d: str) -> str:
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def airline_table(rows: list[dict], lf: float) -> list[dict]:
    out = []
    op = [r for r in rows if is_operated(r)]
    total = len(op) or 1
    for airline, rs in group_by(op, lambda r: r["airline"] or "Unknown").items():
        s = summarize(rs, lf)
        out.append({
            "airline": airline,
            "code": rs[0].get("airline_iata") or rs[0].get("airline_icao") or "",
            "flights": s["movements"], "share_pct": round(100 * s["movements"] / total, 1),
            "arrivals": s["arrivals"], "departures": s["departures"],
            "international": s["international"], "cargo": s["cargo"],
            "est_seats": s["est_seats"], "est_pax": s["est_pax"], "on_time_pct": s["on_time_pct"],
            "aircraft": ", ".join(f"{k} ({v})" for k, v in Counter(r["aircraft_model"] or "n/a" for r in rs).most_common(3)),
            "routes": ", ".join(sorted({r["other_city"] or r["other_iata"] for r in rs if r["other_city"] or r["other_iata"]})),
        })
    return sorted(out, key=lambda x: -x["flights"])


def route_table(rows: list[dict], lf: float) -> list[dict]:
    op = [r for r in rows if is_operated(r)]
    days = max(1, len({r["date"] for r in op}))
    out = []
    for key, rs in group_by(op, lambda r: r["other_iata"] or r["other_city"] or "?").items():
        s = summarize(rs, lf)
        out.append({
            "iata": rs[0]["other_iata"], "city": rs[0]["other_city"] or rs[0]["other_name"],
            "country": rs[0]["other_country"], "international": rs[0]["is_international"],
            "flights": s["movements"], "per_day": round(s["movements"] / days, 2),
            "airlines": ", ".join(sorted({r["airline"] for r in rs})), "est_pax": s["est_pax"],
        })
    return sorted(out, key=lambda x: -x["flights"])


def aircraft_table(rows: list[dict]) -> list[dict]:
    op = [r for r in rows if is_operated(r)]
    c = Counter(r["aircraft_model"] or "Not reported" for r in op)
    total = sum(c.values()) or 1
    return [{"aircraft": k, "flights": v, "share_pct": round(100 * v / total, 1),
             "typical_seats": seats_for(k)} for k, v in c.most_common()]


def hourly_profile(rows: list[dict]) -> list[int]:
    hours = [0] * 24
    for r in rows:
        if not is_operated(r):
            continue
        dt = _parse_dt(r.get("sched_local", ""))
        if dt:
            hours[dt.hour] += 1
    return hours


def daily_series(rows: list[dict], lf: float) -> list[dict]:
    out = []
    for d, rs in sorted(group_by(rows, lambda r: r["date"]).items()):
        s = summarize(rs, lf)
        s["date"] = d
        out.append(s)
    return out


def period_rows(rows: list[dict], start: date, end: date) -> list[dict]:
    a, b = start.isoformat(), end.isoformat()
    return [r for r in rows if a <= r["date"] <= b]


def week_bounds(any_day: date) -> tuple[date, date]:
    start = any_day - timedelta(days=any_day.weekday())
    return start, start + timedelta(days=6)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return start, nxt - timedelta(days=1)

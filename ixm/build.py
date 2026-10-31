"""Build the JSON files the dashboard reads (site/data/*.json)."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import aai, analytics as an, config, forecast, store


def _write(name: str, obj) -> None:
    config.SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.SITE_DATA_DIR / name).write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")


def _f(v):
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def read_annual() -> list[dict]:
    if not config.AAI_ANNUAL_CSV.exists():
        return []
    with config.AAI_ANNUAL_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def aai_tables(monthly: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    rows = []
    for m in sorted(monthly):
        r = monthly[m]
        prev = monthly.get(f"{int(m[:4]) - 1}-{m[5:]}", {})
        cur, old = _f(r.get("pax_total")), _f(prev.get("pax_total"))
        rows.append({
            "month": m, **{k: _f(r.get(k)) for k in aai.MONTHLY_FIELDS if k not in ("month", "source")},
            "pax_yoy_pct": round(100 * (cur - old) / old, 1) if cur and old else None,
            "pax_per_day": round(cur / an.month_bounds(int(m[:4]), int(m[5:]))[1].day) if cur else None,
            "source": r.get("source", ""),
        })
    # fiscal-year totals from complete monthly data, merged with the annual seed
    fy = defaultdict(list)
    for r in rows:
        if r["pax_total"]:
            fy[forecast.fiscal_year(r["month"])].append(r)
    annual = {a["fiscal_year"]: {**a, "derived": False} for a in read_annual()}
    for y, rs in fy.items():
        if len(rs) == 12:
            entry = annual.setdefault(y, {"fiscal_year": y})
            entry.setdefault("passengers", str(int(sum(r["pax_total"] for r in rs))))
            if all(r["mov_total"] for r in rs):
                entry.setdefault("movements", str(int(sum(r["mov_total"] for r in rs))))
            if all(r["frt_total"] is not None for r in rs):
                entry.setdefault("freight_tonnes", str(round(sum(r["frt_total"] for r in rs))))
            entry.setdefault("source", "sum of AAI monthly")
    return rows, [annual[k] for k in sorted(annual)]


def publish_reports() -> list[dict]:
    """Copy generated reports into the site and index them (newest first)."""
    import re
    import shutil
    src = config.ROOT / "reports"
    dst = config.SITE_DIR / "reports"
    groups: dict[str, dict] = {}
    if src.exists():
        dst.mkdir(parents=True, exist_ok=True)
        for p in sorted(src.glob("IXM_*_report_*.*")):
            if p.suffix not in (".pptx", ".xlsx"):
                continue
            m = re.match(r"IXM_(weekly|monthly)_report_(.+)$", p.stem)
            if not m:
                continue
            shutil.copy2(p, dst / p.name)
            g = groups.setdefault(p.stem, {"title": f"{m.group(1).title()} report", "kind": m.group(1),
                                           "period": m.group(2), "files": []})
            g["files"].append({"label": "PowerPoint" if p.suffix == ".pptx" else "Excel",
                               "href": f"reports/{p.name}"})
    return sorted(groups.values(), key=lambda g: (g["period"], g["kind"]), reverse=True)


def build(today: date | None = None) -> dict:
    tz = ZoneInfo(config.LOCAL_TZ)
    today = today or datetime.now(tz).date()
    flights = store.load_all()
    monthly = aai.merged_monthly()
    cal = an.calibrate_load_factor(flights, monthly)
    lf, lf_note = an.current_load_factor(cal)

    past = [r for r in flights if r["date"] < today.isoformat()]
    future = [r for r in flights if r["date"] >= today.isoformat()]
    last7 = an.period_rows(past, today - timedelta(days=7), today - timedelta(days=1))
    last30 = an.period_rows(past, today - timedelta(days=30), today - timedelta(days=1))
    mstart, _ = an.month_bounds(today.year, today.month)
    mtd = an.period_rows(past, mstart, today - timedelta(days=1))

    board = sorted([r for r in flights if r["date"] == today.isoformat()],
                   key=lambda r: r["sched_local"])

    monthly_rows, annual_rows = aai_tables(monthly)
    latest_aai = next((r for r in reversed(monthly_rows) if r["pax_total"]), None)

    # next-7-days schedule-based forecast
    next7 = []
    for i in range(7):
        d = today + timedelta(days=i)
        rs = [r for r in future if r["date"] == d.isoformat()]
        if rs:
            s = an.summarize(rs, lf)
            next7.append({"date": d.isoformat(), "flights": s["movements"], "est_pax": s["est_pax"],
                          "international": s["international"], "cargo": s["cargo"]})

    flight_months = []
    for m, rs in sorted(an.group_by(past, lambda r: r["date"][:7]).items()):
        s = an.summarize(rs, lf)
        s.update({"month": m, "days_with_data": len({r["date"] for r in rs})})
        flight_months.append(s)

    weeks = []
    for w, rs in sorted(an.group_by(past, lambda r: an.iso_week(r["date"])).items()):
        s = an.summarize(rs, lf)
        s.update({"week": w, "days_with_data": len({r["date"] for r in rs})})
        weeks.append(s)

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today_local": today.isoformat(),
        "airport": {"iata": config.AIRPORT_IATA, "icao": config.AIRPORT_ICAO, "name": config.AIRPORT_NAME,
                    "lat": config.AIRPORT_LAT, "lon": config.AIRPORT_LON},
        "load_factor": {"value": lf, "note": lf_note, "calibration": cal},
        "kpi": {"last7": an.summarize(last7, lf), "last30": an.summarize(last30, lf),
                "month_to_date": an.summarize(mtd, lf)},
        "latest_aai_month": latest_aai,
        "coverage": {"flight_days": len({r["date"] for r in flights}),
                     "first_flight_day": min((r["date"] for r in flights), default=None),
                     "last_flight_day": max((r["date"] for r in flights), default=None),
                     "aai_months": sum(1 for r in monthly_rows if r["pax_total"])},
        "board": board,
    }
    _write("summary.json", summary)
    _write("daily.json", an.daily_series(past, lf)[-400:])
    _write("weekly_flights.json", weeks)
    _write("monthly_flights.json", flight_months)
    _write("aai_monthly.json", monthly_rows)
    _write("aai_annual.json", annual_rows)
    _write("airlines.json", {"last30": an.airline_table(last30, lf), "all": an.airline_table(past, lf)})
    _write("routes.json", {"last30": an.route_table(last30, lf), "all": an.route_table(past, lf)})
    _write("aircraft.json", {"last30": an.aircraft_table(last30), "all": an.aircraft_table(past)})
    _write("hourly.json", {"last30": an.hourly_profile(last30)})
    _write("forecast.json", {"monthly": forecast.monthly_forecast(monthly), "next7": next7,
                             "load_factor": lf})
    _write("reports.json", publish_reports())
    if not (config.SITE_DATA_DIR / "live.json").exists():
        _write("live.json", {"status": "not yet collected", "aircraft": []})
    return summary

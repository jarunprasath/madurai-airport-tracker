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


def _consistent(d, i, t) -> bool:
    return None not in (d, i, t) and (not t or abs(d + i - t) <= max(2.0, 0.01 * t))


def clean_monthly(monthly: dict[str, dict]) -> dict[str, dict]:
    """Cross-check every metric group (passengers, movements, cargo) of every month:
    1. prefer the revised copy from next year's report when it is consistent and differs from ours;
    2. a value identical to the same month last year (a column slip in the PDF) is treated as a misread;
    3. groups where domestic + international != total, or impossible cargo, are blanked."""
    out = {}
    for m, src in monthly.items():
        r = dict(src)
        prev = monthly.get(f"{int(m[:4]) - 1}-{m[5:]}", {})
        notes = []
        for g in ("pax", "mov", "frt"):
            keys = [f"{g}_dom", f"{g}_intl", f"{g}_total"]
            cur = [_f(r.get(k)) for k in keys]
            rev = [_f(r.get(f"{k}_rev")) for k in keys]
            last = [_f(prev.get(k)) for k in keys]
            # the same report's own "last year" column for this row (stored on last year's month as *_rev)
            last_same_pdf = [_f(prev.get(f"{k}_rev")) for k in keys]
            if _consistent(*rev) and cur != rev and any(
                    c is None or (v and abs(c - v) > max(2.0, 0.02 * v)) for c, v in zip(cur, rev)):
                for k, v in zip(keys, rev):
                    r[k] = v
                cur = rev
                notes.append(f"{g}: revised figures used")
            slip = any(c is not None and c > 10 and c in (l, l2) and not (rev[n] is not None and rev[n] == c)
                       for n, (c, l, l2) in enumerate(zip(cur, last, last_same_pdf)))
            bad = (slip or not _consistent(*cur) if None not in cur else False) or (
                g == "frt" and any(v is not None and v > aai.FREIGHT_MAX_T for v in cur))
            if bad:
                for k in keys:
                    r[k] = ""
                notes.append(f"{g}: failed cross-check, left blank")
        r["checks"] = "; ".join(notes)
        out[m] = r
    return out


def aai_tables(monthly: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    if not any("checks" in r for r in monthly.values()):
        monthly = clean_monthly(monthly)
    rows = []
    for m in sorted(monthly):
        r = monthly[m]
        prev = monthly.get(f"{int(m[:4]) - 1}-{m[5:]}", {})
        cur, old = _f(r.get("pax_total")), _f(prev.get("pax_total"))
        rows.append({
            "month": m, **{k: _f(r.get(k)) for k in aai.VALUE_FIELDS},
            "pax_yoy_pct": round(100 * (cur - old) / old, 1) if cur and old else None,
            "pax_per_day": round(cur / an.month_bounds(int(m[:4]), int(m[5:]))[1].day) if cur else None,
            "source": r.get("source", ""), "checks": r.get("checks", ""),
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
        for p in sorted(list(src.glob("IXM_*_report_*.*")) + list(src.glob("IXM_10_year_review.*"))):
            if p.suffix not in (".pptx", ".xlsx"):
                continue
            m = re.match(r"IXM_(weekly|monthly|yearly)_report_(.+)$", p.stem)
            if p.stem == "IXM_10_year_review":
                kind, title, period = "review", "10-year review & recommendations", "FY 2016-17 onwards"
            elif m:
                kind, title, period = m.group(1), f"{m.group(1).title()} report", m.group(2)
            else:
                continue
            shutil.copy2(p, dst / p.name)
            g = groups.setdefault(p.stem, {"title": title, "kind": kind, "period": period, "files": []})
            g["files"].append({"label": "PowerPoint" if p.suffix == ".pptx" else "Excel",
                               "href": f"reports/{p.name}"})
    return sorted(groups.values(), key=lambda g: (g["kind"] == "review", g["period"], g["kind"]), reverse=True)


def build(today: date | None = None) -> dict:
    tz = ZoneInfo(config.LOCAL_TZ)
    today = today or datetime.now(tz).date()
    flights = store.load_all()
    monthly = clean_monthly(aai.merged_monthly())
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
        "kpi": {"last7": {**an.summarize(last7, lf), "days": len({r["date"] for r in last7})},
                "last30": {**an.summarize(last30, lf), "days": len({r["date"] for r in last30})},
                "month_to_date": {**an.summarize(mtd, lf), "days": len({r["date"] for r in mtd})}},
        "latest_aai_month": latest_aai,
        "coverage": {"flight_days": len({r["date"] for r in flights}),
                     "first_flight_day": min((r["date"] for r in flights), default=None),
                     "last_flight_day": max((r["date"] for r in flights), default=None),
                     "aai_months": sum(1 for r in monthly_rows if r["pax_total"])},
        "board": board,
        "flights_status": json.loads((config.DATA_DIR / "flights_status.json").read_text(encoding="utf-8"))
        if (config.DATA_DIR / "flights_status.json").exists() else None,
    }
    _write("summary.json", summary)
    _write("daily.json", an.daily_series(past, lf))
    _write("weekly_flights.json", weeks)
    _write("monthly_flights.json", flight_months)
    _write("aai_monthly.json", monthly_rows)
    _write("aai_annual.json", annual_rows)
    def span(rows, label):
        ds = sorted({r["date"] for r in rows})
        return {"label": label, "from": ds[0] if ds else None, "to": ds[-1] if ds else None, "days": len(ds)}
    periods = {"last30": span(last30, "Last 30 days"), "all": span(past, "All collected data")}
    _write("airlines.json", {"last30": an.airline_table(last30, lf), "all": an.airline_table(past, lf), "periods": periods})
    _write("routes.json", {"last30": an.route_table(last30, lf), "all": an.route_table(past, lf), "periods": periods})
    _write("aircraft.json", {"last30": an.aircraft_table(last30), "all": an.aircraft_table(past), "periods": periods})
    _write("hourly.json", {"last30": an.hourly_profile(last30), "periods": periods})
    _write("forecast.json", {"monthly": forecast.monthly_forecast(monthly), "next7": next7,
                             "load_factor": lf})
    _write("reports.json", publish_reports())
    if not (config.SITE_DATA_DIR / "live.json").exists():
        _write("live.json", {"status": "not yet collected", "aircraft": []})
    return summary

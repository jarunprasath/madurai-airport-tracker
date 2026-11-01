"""On-demand weekly / monthly reports: computes the report data, writes the Excel
workbook (native charts) and a JSON payload the PowerPoint builder (report_pptx.js) reads."""
from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import aai, analytics as an, config, forecast, store
from .build import aai_tables

REPORTS_DIR = config.ROOT / "reports"
INK, ACCENT, MUTED = "17324D", "C8553D", "6B7785"


def _pct(cur, prev):
    if cur is None or not prev:
        return None
    return round(100 * (cur - prev) / prev, 1)


def _period(kind: str, ref: date) -> tuple[date, date, date, date, str]:
    if kind == "weekly":
        s, e = an.week_bounds(ref)
        ps, pe = s - timedelta(days=7), e - timedelta(days=7)
        y, w, _ = s.isocalendar()
        label = f"Week {w}, {y} ({s:%d %b} - {e:%d %b %Y})"
    elif kind == "monthly":
        s, e = an.month_bounds(ref.year, ref.month)
        ps, pe = an.month_bounds(ref.year - (ref.month == 1), (ref.month - 2) % 12 + 1)
        label = f"{s:%B %Y}"
    elif kind == "yearly":
        fy = ref.year if ref.month >= 4 else ref.year - 1        # Indian financial year, April-March
        s, e = date(fy, 4, 1), date(fy + 1, 3, 31)
        ps, pe = date(fy - 1, 4, 1), date(fy, 3, 31)
        label = f"FY {fy}-{(fy + 1) % 100:02d} (Apr {fy} - Mar {fy + 1})"
    else:
        raise ValueError("kind must be 'weekly', 'monthly' or 'yearly'")
    return s, e, ps, pe, label


def fy_aggregate(monthly_rows: list[dict], s: date, e: date, name: str,
                 only_months: set[str] | None = None) -> dict | None:
    """Sum AAI monthly rows inside [s, e]. A metric is summed only when every month has it.
    `only_months` (calendar month numbers "MM") restricts the sum for like-for-like comparisons."""
    a, b = f"{s.year}-{s.month:02d}", f"{e.year}-{e.month:02d}"
    rows = [r for r in monthly_rows if a <= r["month"] <= b and r.get("pax_total")
            and (only_months is None or r["month"][5:] in only_months)]
    if not rows:
        return None
    n_expected = (e.year - s.year) * 12 + e.month - s.month + 1
    out = {"month": name, "months": len(rows), "months_expected": n_expected,
           "missing": sorted({f"{y}-{m:02d}" for y in range(s.year, e.year + 1) for m in range(1, 13)
                              if a <= f"{y}-{m:02d}" <= b} - {r["month"] for r in rows})}
    for k in ("pax_dom", "pax_intl", "pax_total", "mov_dom", "mov_intl", "mov_total", "frt_dom", "frt_intl", "frt_total"):
        vals = [r.get(k) for r in rows]
        out[k] = round(sum(vals), 1) if all(v is not None for v in vals) else None
    return out


def build_report_data(kind: str, ref: date) -> dict:
    s, e, ps, pe, label = _period(kind, ref)
    flights = store.load_all()
    from .build import clean_monthly
    monthly = clean_monthly(aai.merged_monthly())
    lf, lf_note = an.current_load_factor(an.calibrate_load_factor(flights, monthly))

    cur_rows, prev_rows = an.period_rows(flights, s, e), an.period_rows(flights, ps, pe)
    first_day = min((r["date"] for r in flights), default=None)
    last_day = max((r["date"] for r in flights), default=None)
    if cur_rows:
        no_flight_reason = ""
    elif not first_day:
        no_flight_reason = ("No flight-schedule data has been collected yet. "
                            "Check that the AERODATABOX_KEY secret is set and the 'Collect flights' workflow has run.")
    elif e.isoformat() < first_day:
        no_flight_reason = (f"Flight-by-flight collection started on {date.fromisoformat(first_day):%d %b %Y}, "
                            f"after this period, so daily flights, airlines and routes are not available. "
                            + ("For past periods use the monthly report, which is based on AAI's official figures."
                               if kind == "weekly" else "Official AAI monthly figures are shown instead."))
    else:
        no_flight_reason = "No flights were recorded in this period (the data source may have had an outage)."
    cur, prev = an.summarize(cur_rows, lf), an.summarize(prev_rows, lf)
    days_cur = len({r["date"] for r in cur_rows})
    days_expected = (e - s).days + 1

    monthly_rows, annual_rows = aai_tables(monthly)
    end_month = f"{e.year}-{e.month:02d}"
    aai_hist = [r for r in monthly_rows if r["month"] <= end_month and r["pax_total"]][-24:]
    aai_this = next((r for r in monthly_rows if r["month"] == end_month and r["pax_total"]), None)
    fy_months = []
    if kind == "yearly":
        fy_name = label.split(" (")[0]
        aai_this = fy_aggregate(monthly_rows, s, e, fy_name)
        fy_months = [r for r in monthly_rows if f"{s.year}-{s.month:02d}" <= r["month"] <= end_month]
        aai_hist = [r for r in monthly_rows if r["month"] <= end_month and r["pax_total"]][-36:]
    fc = forecast.monthly_forecast({k: v for k, v in monthly.items() if k <= end_month})

    airlines = an.airline_table(cur_rows, lf)
    routes = an.route_table(cur_rows, lf)
    aircraft = an.aircraft_table(cur_rows)
    hourly = an.hourly_profile(cur_rows)
    daily = an.daily_series(cur_rows, lf)

    insights = []
    if cur["movements"]:
        ch = _pct(cur["movements"], prev["movements"])
        insights.append(f"{cur['movements']} flight movements ({cur['arrivals']} arrivals, {cur['departures']} departures)"
                        + (f", {ch:+.1f}% vs previous {kind[:-2]}" if ch is not None else "") + ".")
        if airlines:
            a = airlines[0]
            insights.append(f"{a['airline']} operated {a['share_pct']}% of movements - the largest carrier.")
        if routes:
            r = routes[0]
            insights.append(f"Busiest route: {r['city'] or r['iata']} with {r['flights']} movements (~{r['per_day']}/day).")
        intl_share = round(100 * cur["international"] / cur["movements"], 1)
        insights.append(f"International movements: {cur['international']} ({intl_share}% of total).")
        if any(hourly):
            peak = max(range(24), key=lambda h: hourly[h])
            insights.append(f"Peak hour: {peak:02d}:00-{peak:02d}:59 local with {hourly[peak]} scheduled movements.")
        if cur["cancelled"]:
            insights.append(f"{cur['cancelled']} flights were cancelled or diverted.")
        if cur["on_time_pct"] is not None:
            insights.append(f"On-time performance (within 15 min): {cur['on_time_pct']}%.")
        if cur["cargo"]:
            insights.append(f"{cur['cargo']} dedicated cargo flight movements recorded.")
    else:
        insights.append(no_flight_reason)
    aai_prev_year = None
    if aai_this:
        if kind == "yearly":
            # like-for-like: compare only the calendar months present in BOTH years
            cur_mm = {r["month"][5:] for r in monthly_rows if f"{s.year}-04" <= r["month"] <= f"{e.year}-03" and r.get("pax_total")}
            prev_mm = {r["month"][5:] for r in monthly_rows if f"{ps.year}-04" <= r["month"] <= f"{pe.year}-03" and r.get("pax_total")}
            common = cur_mm & prev_mm
            aai_prev_year = fy_aggregate(monthly_rows, ps, pe, f"FY {ps.year}-{(ps.year + 1) % 100:02d}", common)
            cur_lfl = fy_aggregate(monthly_rows, s, e, "lfl", common)
            if aai_prev_year and cur_lfl:
                aai_this["lfl_months"] = len(common)
                for k in ("pax_total", "pax_dom", "pax_intl", "mov_total", "frt_total"):
                    aai_this[f"{k}_lfl"] = cur_lfl.get(k)
                aai_this["pax_yoy_pct"] = _pct(cur_lfl["pax_total"], aai_prev_year["pax_total"])
            if aai_this["missing"]:
                insights.append(f"AAI data covers {aai_this['months']} of {aai_this['months_expected']} months "
                                f"(missing: {', '.join(aai_this['missing'])}); totals below are for available months.")
        else:
            py = f"{int(end_month[:4]) - 1}-{end_month[5:]}"
            aai_prev_year = next((r for r in monthly_rows if r["month"] == py and r["pax_total"]), None)
        y = aai_this.get("pax_yoy_pct")
        insights.append(f"AAI official passengers for {aai_this['month']}: {int(aai_this['pax_total']):,}"
                        + (f" ({y:+.1f}% year on year)." if y is not None else "."))
        if kind == "yearly" and fy_months:
            best = max((r for r in fy_months if r.get("pax_total")), key=lambda r: r["pax_total"])
            worst = min((r for r in fy_months if r.get("pax_total")), key=lambda r: r["pax_total"])
            insights.append(f"Busiest month {best['month']} ({int(best['pax_total']):,}); quietest {worst['month']} ({int(worst['pax_total']):,}).")
        if aai_this.get("pax_dom") is not None and aai_this.get("pax_intl") is not None:
            share = 100 * aai_this["pax_intl"] / aai_this["pax_total"]
            line = f"Domestic {int(aai_this['pax_dom']):,} and international {int(aai_this['pax_intl']):,} ({share:.1f}% of total)"
            if aai_prev_year and aai_prev_year.get("pax_intl"):
                line += (f"; international {_pct(aai_this['pax_intl'], aai_prev_year['pax_intl']):+.1f}% and domestic "
                         f"{_pct(aai_this['pax_dom'], aai_prev_year['pax_dom']):+.1f}% vs a year ago")
            insights.append(line + ".")
        if aai_this.get("mov_total"):
            line = f"Aircraft movements: {int(aai_this['mov_total']):,} (about {aai_this['pax_total'] / aai_this['mov_total']:.0f} passengers per movement)"
            if aai_prev_year and aai_prev_year.get("mov_total"):
                line += f", {_pct(aai_this['mov_total'], aai_prev_year['mov_total']):+.1f}% vs a year ago"
            insights.append(line + ".")
        if aai_this.get("frt_total") is not None:
            line = f"Cargo handled: {aai_this['frt_total']:,.0f} tonnes"
            if aai_prev_year and aai_prev_year.get("frt_total"):
                line += f" ({_pct(aai_this['frt_total'], aai_prev_year['frt_total']):+.1f}% year on year)"
            insights.append(line + ".")
    # months missing inside the plotted AAI history
    gaps = []
    if aai_hist:
        y0, m0 = map(int, aai_hist[0]["month"].split("-"))
        have = {r["month"] for r in aai_hist}
        while f"{y0}-{m0:02d}" <= aai_hist[-1]["month"]:
            if f"{y0}-{m0:02d}" not in have:
                gaps.append(f"{y0}-{m0:02d}")
            m0 += 1
            if m0 == 13:
                y0, m0 = y0 + 1, 1
    if lf >= 0.85 and "calibrated" in lf_note:
        insights.append(f"Implied seat load factor is about {round(lf * 100)}% - flights run close to full, "
                        "which supports a case for added capacity or new frequencies.")
    if fc.get("available"):
        nxt = fc["points"][:3]
        insights.append("Forecast (AAI basis) next 3 months: " +
                        ", ".join(f"{p['month']} ~{p['forecast']:,}" for p in nxt) + " passengers.")

    caveats = [
        "Flight movements come from AeroDataBox schedule/status data; coverage may miss some flights.",
        f"Passenger counts per flight are ESTIMATES: typical seats x load factor {lf} ({lf_note}).",
        "Official passenger, movement and freight totals come from AAI monthly Traffic News and lag 4-8 weeks.",
        "Forecasts are statistical estimates, not official projections.",
    ]
    if days_cur < days_expected:
        caveats.insert(0, f"Flight data covers {days_cur} of {days_expected} days in this period.")
    if gaps:
        caveats.append(f"AAI months not yet collected (skipped in the trend chart): {', '.join(gaps)}.")

    return {
        "kind": kind, "label": label, "start": s.isoformat(), "end": e.isoformat(),
        "prev_start": ps.isoformat(), "prev_end": pe.isoformat(),
        "airport": {"name": config.AIRPORT_NAME, "iata": config.AIRPORT_IATA, "icao": config.AIRPORT_ICAO},
        "load_factor": lf, "load_factor_note": lf_note,
        "kpi": cur, "kpi_prev": prev,
        "kpi_change": {k: _pct(cur[k], prev[k]) for k in ("movements", "est_pax", "international", "cargo")},
        "days_with_data": days_cur, "days_in_period": days_expected,
        "daily": daily, "airlines": airlines, "routes": routes, "aircraft": aircraft, "hourly": hourly,
        "aai_history": aai_hist, "aai_this_month": aai_this, "aai_prev_year": aai_prev_year,
        "aai_gaps": gaps, "aai_annual": annual_rows, "no_flight_reason": no_flight_reason, "fy_months": fy_months,
        "flight_coverage": {"first": first_day, "last": last_day},
        "forecast": fc, "insights": insights, "caveats": caveats,
        "flights": sorted(cur_rows, key=lambda r: (r["date"], r["sched_local"])),
        "sources": ["AAI Traffic News - aai.aero", "AeroDataBox (via RapidAPI)", "OpenSky Network"],
    }


# ---------------------------------------------------------------- Excel
def _sheet(wb: Workbook, title: str, header: list[str], rows: list[list]):
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=INK)
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for r in rows:
        ws.append(r)
    for i, h in enumerate(header, 1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r)]) + 2
        ws.column_dimensions[get_column_letter(i)].width = min(max(width, 9), 48)
    ws.freeze_panes = "A2"
    return ws


def _bar(ws, title, cats_col, val_cols, n, anchor, ytitle="", stacked=False, horizontal=False):
    if n == 0:
        return
    ch = BarChart()
    ch.type = "bar" if horizontal else "col"
    ch.title, ch.y_axis.title = title, ytitle
    if stacked:
        ch.grouping, ch.overlap = "stacked", 100
    for c in val_cols:
        ch.add_data(Reference(ws, min_col=c, min_row=1, max_row=n + 1), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=cats_col, min_row=2, max_row=n + 1))
    ch.height, ch.width = 8, 16
    ws.add_chart(ch, anchor)


def write_excel(d: dict, path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"{d['airport']['name']} ({d['airport']['iata']}) - {d['kind'].title()} report"
    ws["A1"].font = Font(bold=True, size=16, color=INK)
    ws["A2"] = d["label"]
    ws["A2"].font = Font(size=12, color=MUTED)
    k, kp, kc = d["kpi"], d["kpi_prev"], d["kpi_change"]
    rows = [
        ("Flight movements", k["movements"], kp["movements"], kc["movements"]),
        ("Arrivals", k["arrivals"], kp["arrivals"], _pct(k["arrivals"], kp["arrivals"])),
        ("Departures", k["departures"], kp["departures"], _pct(k["departures"], kp["departures"])),
        ("International movements", k["international"], kp["international"], kc["international"]),
        ("Cargo flight movements", k["cargo"], kp["cargo"], kc["cargo"]),
        ("Cancelled / diverted", k["cancelled"], kp["cancelled"], _pct(k["cancelled"], kp["cancelled"])),
        ("Estimated seats", k["est_seats"], kp["est_seats"], _pct(k["est_seats"], kp["est_seats"])),
        ("Estimated passengers", k["est_pax"], kp["est_pax"], kc["est_pax"]),
        ("On-time % (<=15 min)", k["on_time_pct"], kp["on_time_pct"], None),
    ]
    ws.append([])
    ws.append(["Metric", "This period", "Previous period", "Change %"])
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=INK)
    for r in rows:
        ws.append(list(r))
    if d["aai_this_month"]:
        a = d["aai_this_month"]
        ws.append([])
        ws.append(["AAI official", "Passengers", "Aircraft movements", "Freight (t)"])
        ws.append([a["month"], a["pax_total"], a["mov_total"], a["frt_total"]])
    ws.append([])
    ws.append(["Key insights"])
    ws.cell(ws.max_row, 1).font = Font(bold=True, color=INK)
    for s in d["insights"]:
        ws.append([s])
    ws.append([])
    ws.append(["Notes & caveats"])
    ws.cell(ws.max_row, 1).font = Font(bold=True, color=INK)
    for s in d["caveats"]:
        ws.append([s])
    ws.append(["Sources: " + "; ".join(d["sources"])])
    ws.column_dimensions["A"].width = 34
    for col in "BCD":
        ws.column_dimensions[col].width = 18

    if d.get("fy_months"):
        fm = d["fy_months"]
        wsy = _sheet(wb, "Months in FY", ["Month", "Passengers", "Domestic", "International", "YoY %", "Movements", "Cargo (t)"],
                     [[x["month"], x["pax_total"], x["pax_dom"], x["pax_intl"], x["pax_yoy_pct"], x["mov_total"], x["frt_total"]] for x in fm])
        _bar(wsy, "Monthly passengers in the financial year", 1, [3, 4], len(fm), "I2", "Passengers", stacked=True)
    daily = d["daily"]
    wsd = _sheet(wb, "Daily", ["Date", "Movements", "Arrivals", "Departures", "International", "Cargo",
                               "Cancelled", "Est. passengers", "On-time %"],
                 [[x["date"], x["movements"], x["arrivals"], x["departures"], x["international"], x["cargo"],
                   x["cancelled"], x["est_pax"], x["on_time_pct"]] for x in daily])
    _bar(wsd, "Daily arrivals and departures", 1, [3, 4], len(daily), "K2", "Movements", stacked=True)

    al = d["airlines"]
    wsa = _sheet(wb, "Airlines", ["Airline", "Code", "Flights", "Share %", "Arrivals", "Departures",
                                  "International", "Cargo", "Est. seats", "Est. passengers", "On-time %",
                                  "Aircraft (top 3)", "Routes"],
                 [[x["airline"], x["code"], x["flights"], x["share_pct"], x["arrivals"], x["departures"],
                   x["international"], x["cargo"], x["est_seats"], x["est_pax"], x["on_time_pct"], x["aircraft"],
                   x["routes"]] for x in al])
    if al:
        pie = PieChart()
        pie.title = "Share of movements by airline"
        pie.add_data(Reference(wsa, min_col=3, min_row=1, max_row=len(al) + 1), titles_from_data=True)
        pie.set_categories(Reference(wsa, min_col=1, min_row=2, max_row=len(al) + 1))
        pie.height, pie.width = 8, 12
        wsa.add_chart(pie, "O2")

    rt = d["routes"]
    wsr = _sheet(wb, "Routes", ["IATA", "City", "Country", "International", "Flights", "Per day", "Airlines",
                                "Est. passengers"],
                 [[x["iata"], x["city"], x["country"], "Yes" if x["international"] else "No", x["flights"],
                   x["per_day"], x["airlines"], x["est_pax"]] for x in rt])
    _bar(wsr, "Movements by route", 2, [5], min(len(rt), 15), "J2", horizontal=True)

    ac = d["aircraft"]
    wst = _sheet(wb, "Aircraft types", ["Aircraft", "Flights", "Share %", "Typical seats (assumed)"],
                 [[x["aircraft"], x["flights"], x["share_pct"], x["typical_seats"]] for x in ac])
    _bar(wst, "Movements by aircraft type", 1, [2], min(len(ac), 12), "F2", horizontal=True)

    wsh = _sheet(wb, "Hourly", ["Hour (local)", "Scheduled movements"],
                 [[f"{h:02d}:00", v] for h, v in enumerate(d["hourly"])])
    _bar(wsh, "Movements by hour of day", 1, [2], 24, "D2")

    hist = d["aai_history"]
    wsm = _sheet(wb, "AAI monthly", ["Month", "Passengers total", "Domestic", "International", "YoY %",
                                     "Aircraft movements", "Freight total (t)", "Source"],
                 [[x["month"], x["pax_total"], x["pax_dom"], x["pax_intl"], x["pax_yoy_pct"], x["mov_total"],
                   x["frt_total"], x["source"]] for x in hist])
    if hist:
        ln = LineChart()
        ln.title, ln.y_axis.title = "AAI official monthly passengers", "Passengers"
        ln.add_data(Reference(wsm, min_col=2, min_row=1, max_row=len(hist) + 1), titles_from_data=True)
        ln.set_categories(Reference(wsm, min_col=1, min_row=2, max_row=len(hist) + 1))
        ln.height, ln.width = 8, 18
        wsm.add_chart(ln, "J2")

    fc = d["forecast"]
    if fc.get("available"):
        wsf = _sheet(wb, "Forecast", ["Month", "Forecast passengers", "Low (80%)", "High (80%)",
                                      "Seasonal index", "Season / festivals"],
                     [[p["month"], p["forecast"], p["low"], p["high"], p["seasonal_index"], "; ".join(p["season"])]
                      for p in fc["points"]])
        ln = LineChart()
        ln.title = "12-month passenger forecast"
        for c in (2, 3, 4):
            ln.add_data(Reference(wsf, min_col=c, min_row=1, max_row=len(fc["points"]) + 1), titles_from_data=True)
        ln.set_categories(Reference(wsf, min_col=1, min_row=2, max_row=len(fc["points"]) + 1))
        ln.height, ln.width = 8, 18
        wsf.add_chart(ln, "H2")
        wsf.append([])
        wsf.append([f"Method: {fc['method']}. Trained on {fc['trained_on']}. "
                    f"Backtest MAPE: {fc['backtest_mape_pct']}%."])
    else:
        wsf = wb.create_sheet("Forecast")
        wsf["A1"] = "Forecast not available: " + fc.get("reason", "")

    fl = d["flights"]
    _sheet(wb, "Flights", ["Date", "Direction", "Flight", "Airline", "Status", "Cargo", "International",
                           "Aircraft", "Registration", "From/To", "City", "Scheduled", "Revised", "Actual"],
           [[x["date"], x["direction"], x["flight_no"], x["airline"], x["status"], x["is_cargo"],
             x["is_international"], x["aircraft_model"], x["aircraft_reg"], x["other_iata"], x["other_city"],
             x["sched_local"], x["revised_local"], x["actual_local"]] for x in fl])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def generate(kind: str, ref: date, out_dir: Path | None = None, pptx: bool = True) -> dict[str, Path]:
    d = build_report_data(kind, ref)
    out = out_dir or REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    if kind == "weekly":
        tag = f"{d['start'][:4]}-W{date.fromisoformat(d['start']).isocalendar()[1]:02d}"
    elif kind == "yearly":
        tag = f"FY{d['start'][:4]}-{int(d['start'][2:4]) + 1:02d}"
    else:
        tag = d["start"][:7]
    stem = f"IXM_{kind}_report_{tag}"
    paths = {"xlsx": write_excel(d, out / f"{stem}.xlsx")}
    jpath = out / f"{stem}.json"
    jpath.write_text(json.dumps(d, default=str, indent=1), encoding="utf-8")
    paths["json"] = jpath
    if pptx:
        ppath = out / f"{stem}.pptx"
        script = config.ROOT / "report_pptx.js"
        subprocess.run(["node", str(script), str(jpath), str(ppath)], check=True)
        paths["pptx"] = ppath
    return paths

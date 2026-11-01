"""10-year strategic review of Madurai Airport (FY 2016-17 to FY 2026-27 YTD).

Every number is computed from the tracker's verified data:
  * AAI monthly Traffic News (data/aai_monthly.csv, cleaned & cross-checked by build.clean_monthly)
  * AeroDataBox flight records (data/flights/*.csv)
plus a small set of published external figures (PEERS, INDIA, CONTEXT) whose sources are listed
with them. Run:  python -m ixm decade  -> reports/IXM_10_year_review.{json,xlsx,pptx}
"""
from __future__ import annotations

import json
import math
import subprocess
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from . import aai, analytics as an, config, forecast, store
from .build import aai_tables, clean_monthly

# ------------------------------------------------------------------ external published figures
# Annual passengers by financial year, AAI figures as tabulated on Wikipedia
# "List of busiest airports in India" (retrieved 1 Nov 2026). Verify against AAI annual reports before quoting.
WIKI_SRC = "AAI annual passenger figures via Wikipedia 'List of busiest airports in India' (retrieved 1 Nov 2026)"
INDIA = {"2015-16": 223615522, "2016-17": 264969723, "2017-18": 308753400, "2018-19": 344699733,
         "2019-20": 341050651, "2020-21": 115379783, "2021-22": 188891441, "2022-23": 327279136,
         "2023-24": 376426164, "2024-25": 412086111, "2025-26": 420087802}
PEERS = {  # FY 2018-19 (pre-COVID peak year) and FY 2025-26, passengers; rank FY 2025-26
    "Madurai (IXM)": {"2018-19": 1520016, "2024-25": 1399046, "2025-26": 1388062, "rank_1819": 32, "rank_2526": 40},
    "Tiruchirappalli (TRZ)": {"2018-19": 1578831, "2024-25": 1956851, "2025-26": 2221024, "rank_1819": 31, "rank_2526": 31},
    "Coimbatore (CJB)": {"2018-19": 3000882, "2024-25": 3253190, "2025-26": 3420745, "rank_1819": 19, "rank_2526": 23},
    "Thiruvananthapuram (TRV)": {"2018-19": 4434459, "2024-25": 4891009, "2025-26": 4694206, "rank_1819": 14, "rank_2526": 16},
    "Kozhikode (CCJ)": {"2018-19": 3360847, "2024-25": 3695944, "2025-26": 3855618, "rank_1819": 17, "rank_2526": 21},
    "Mangaluru (IXE)": {"2018-19": 2240664, "2024-25": 2343032, "2025-26": 2548088, "rank_1819": 27, "rank_2526": 30},
}
CONTEXT = [  # (fact, source)
    ("Integrated terminal of 17,560 m² rated for about 2.9 million passengers a year",
     "Swarajya, 22 Aug 2025 (citing Ministry of Civil Aviation)"),
    ("Runway 2,285 m with Cat-I ILS and 7 parking bays; extension to 3,810 m planned for wide-body (Code E) aircraft",
     "Wikipedia 'Madurai Airport'; Swarajya, 22 Aug 2025"),
    ("543.41 of 653.35 acres for the expansion handed over to AAI; no completion timeline given",
     "Swarajya, 22 Aug 2025 (Minister's reply in Parliament)"),
    ("24-hour operations started on 1 October 2024", "Mysuru Infra Hub, 5 Oct 2024 (single source - verify)"),
    ("Union Cabinet approved international airport status on 10 March 2026",
     "Wikipedia 'Madurai Airport' citing ANI / The Hindu, 10 Mar 2026"),
    ("Direct Dubai and Abu Dhabi flights suspended from end-February 2026 due to the Gulf conflict; resumption from 14 Aug 2026",
     "DT Next, 26 Jun 2026"),
    ("Madurai is not part of bilateral air service agreements, which has made foreign carriers reluctant",
     "Wikipedia 'Madurai Airport'"),
]

FY_LABEL = lambda s: f"{s}-{(s + 1) % 100:02d}"


def _cagr(a: float, b: float, years: float) -> float | None:
    return None if not a or not b or years <= 0 else (b / a) ** (1 / years) - 1


def _fy_of(month: str) -> int:
    y, m = map(int, month.split("-"))
    return y if m >= 4 else y - 1


def compute() -> dict:
    monthly = clean_monthly(aai.merged_monthly())
    rows, _annual = aai_tables(monthly)
    rows = [r for r in rows if r["pax_total"]]
    by_month = {r["month"]: r for r in rows}

    # ---------------- financial-year table from AAI monthly data
    fy = defaultdict(list)
    for r in rows:
        fy[_fy_of(r["month"])].append(r)
    fy_table = []
    for s in sorted(fy):
        rs = fy[s]
        def tot(k, rs=rs):
            vals = [x[k] for x in rs if x[k] is not None]
            return sum(vals) if vals else None
        n = len(rs)
        months_present = {x["month"] for x in rs}
        expected = [f"{s}-{m:02d}" for m in range(4, 13)] + [f"{s + 1}-{m:02d}" for m in range(1, 4)]
        fy_table.append({
            "fy": FY_LABEL(s), "months": n, "missing": [m for m in expected if m not in months_present and m <= rows[-1]["month"]],
            "pax_total": tot("pax_total"), "pax_dom": tot("pax_dom"), "pax_intl": tot("pax_intl"),
            "mov_total": tot("mov_total"), "mov_months": sum(1 for x in rs if x["mov_total"]),
            "frt_total": tot("frt_total"), "frt_months": sum(1 for x in rs if x["frt_total"] is not None),
        })
    for f in fy_table:
        f["intl_share"] = round(100 * f["pax_intl"] / f["pax_total"], 1) if f["pax_intl"] is not None else None
        f["pax_per_mov"] = round(f["pax_total"] / f["mov_total"]) if f["mov_total"] and f["mov_months"] == f["months"] else None
        pub = PEERS["Madurai (IXM)"].get(f["fy"]) or None
        f["published_total"] = {"2017-18": 1442807, "2018-19": 1520016, "2019-20": 1422337, "2020-21": 565539,
                                "2021-22": 679781, "2022-23": 1138005, "2023-24": 1285976, "2024-25": 1399046,
                                "2025-26": 1388062, "2016-17": 978919}.get(f["fy"], pub)
        f["matches_published"] = (f["months"] == 12 and f["published_total"] is not None
                                  and abs(f["pax_total"] - f["published_total"]) < 1)

    verified = [f["fy"] for f in fy_table if f["matches_published"]]

    # ---------------- headline comparisons
    peak = PEERS["Madurai (IXM)"]["2018-19"]
    latest_pub = PEERS["Madurai (IXM)"]["2025-26"]
    peers = []
    for name, p in PEERS.items():
        peers.append({"airport": name, "fy1819": p["2018-19"], "fy2425": p["2024-25"], "fy2526": p["2025-26"],
                      "index_vs_1819": round(100 * p["2025-26"] / p["2018-19"], 1),
                      "cagr_1819_2526": round(100 * _cagr(p["2018-19"], p["2025-26"], 7), 2),
                      "growth_2526": round(100 * (p["2025-26"] / p["2024-25"] - 1), 1),
                      "rank_1819": p["rank_1819"], "rank_2526": p["rank_2526"]})
    india = {"fy1819": INDIA["2018-19"], "fy2526": INDIA["2025-26"],
             "index_vs_1819": round(100 * INDIA["2025-26"] / INDIA["2018-19"], 1),
             "cagr_1819_2526": round(100 * _cagr(INDIA["2018-19"], INDIA["2025-26"], 7), 2),
             "growth_2526": round(100 * (INDIA["2025-26"] / INDIA["2024-25"] - 1), 1)}
    gap_vs_india = round(peak * INDIA["2025-26"] / INDIA["2018-19"] - latest_pub)   # passengers "missing" vs national trend

    # ---------------- seasonality & forecast
    fc = forecast.monthly_forecast(monthly)
    season = [{"month": i, "name": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][i - 1],
               "index": fc["seasonal_index"].get(str(i)) if fc.get("available") else None,
               "tags": forecast.SEASON_TAGS.get(i, [])} for i in range(1, 13)]

    # ---------------- international & Gulf suspension
    intl_2026 = []
    for m in range(1, 10):
        cur, prev = by_month.get(f"2026-{m:02d}"), by_month.get(f"2025-{m:02d}")
        if cur and prev and cur["pax_intl"] is not None and prev["pax_intl"]:
            intl_2026.append({"month": f"2026-{m:02d}", "intl_2026": cur["pax_intl"], "intl_2025": prev["pax_intl"],
                              "change_pct": round(100 * (cur["pax_intl"] / prev["pax_intl"] - 1), 1),
                              "dom_2026": cur["pax_dom"], "dom_2025": prev["pax_dom"],
                              "dom_change_pct": round(100 * (cur["pax_dom"] / prev["pax_dom"] - 1), 1)})
    susp = [x for x in intl_2026 if "2026-03" <= x["month"] <= "2026-07"]
    intl_lost = round(sum(x["intl_2025"] - x["intl_2026"] for x in susp))

    # ---------------- cargo
    cargo_fy = [{"fy": f["fy"], "tonnes": round(f["frt_total"]) if f["frt_total"] is not None else None,
                 "months": f["frt_months"]} for f in fy_table]

    # ---------------- flight-level (AeroDataBox)
    flights = store.load_all()
    op = [r for r in flights if an.is_operated(r)]
    month_days = defaultdict(set)
    for r in flights:
        month_days[r["date"][:7]].add(r["date"])
    full_months = sorted(m for m, d in month_days.items() if len(d) >= 28)
    validation = []
    for m in full_months:
        rs = [r for r in op if r["date"][:7] == m]
        aai_m = by_month.get(m, {}).get("mov_total")
        validation.append({"month": m, "days": len(month_days[m]), "aerodatabox_movements": len(rs),
                           "aai_movements": aai_m,
                           "coverage_pct": round(100 * len(rs) / aai_m, 1) if aai_m else None})
    ref_month = full_months[-1] if full_months else None
    network = {}
    for m in full_months:
        rs = [r for r in op if r["date"][:7] == m]
        nd = len(month_days[m])
        routes = defaultdict(list)
        for r in rs:
            routes[r["other_iata"] or r["other_city"]].append(r)
        network[m] = {
            "days": nd, "movements": len(rs), "per_day": round(len(rs) / nd, 1),
            "routes": sorted([{"iata": k, "city": v[0]["other_city"], "international": v[0]["is_international"],
                               "weekly_departures": round(sum(x["direction"] == "departure" for x in v) / nd * 7, 1),
                               "airlines": sorted({x["airline"] for x in v}),
                               "atr_share_pct": round(100 * sum("ATR" in (x["aircraft_model"] or "") for x in v) / len(v))}
                              for k, v in routes.items() if len(v) >= 4], key=lambda x: -x["weekly_departures"]),
            "airlines": [{"airline": a, "share_pct": round(100 * n / len(rs), 1), "flights": n}
                         for a, n in Counter(r["airline"] for r in rs).most_common()],
            "aircraft": [{"aircraft": a, "share_pct": round(100 * n / len(rs), 1)}
                         for a, n in Counter(r["aircraft_model"] or "n/a" for r in rs).most_common(6)],
            "hourly": an.hourly_profile(rs),
            "night_movements": sum(an.hourly_profile(rs)[h] for h in list(range(22, 24)) + list(range(0, 6))),
            "intl_share_pct": round(100 * sum(r["is_international"] for r in rs) / len(rs), 1),
            "hhi": round(sum((n / len(rs) * 100) ** 2 for n in Counter(r["airline"] for r in rs).values())),
        }

    # ---------------- scenarios (what-if, not forecasts)
    base = latest_pub
    scen_defs = [
        ("Status quo", round(100 * _cagr(peak, latest_pub, 7), 2), "Madurai's own trend FY18-19 to FY25-26"),
        ("Match India", india["cagr_1819_2526"], "All-India airport growth FY18-19 to FY25-26"),
        ("Match Trichy", next(p["cagr_1819_2526"] for p in peers if p["airport"].startswith("Tiruchi")),
         "Tiruchirappalli growth FY18-19 to FY25-26"),
    ]
    scenarios = []
    for name, g, basis in scen_defs:
        path = [{"fy": FY_LABEL(2025 + i), "passengers": round(base * (1 + g / 100) ** i)} for i in range(0, 6)]
        scenarios.append({"name": name, "cagr_pct": g, "basis": basis, "path": path,
                          "fy2030_31": path[-1]["passengers"], "terminal_use_pct": round(100 * path[-1]["passengers"] / 2_900_000)})

    return {
        "generated": date.today().isoformat(),
        "aai_range": [rows[0]["month"], rows[-1]["month"]], "aai_months": len(rows),
        "aai_missing": [m for m in (f"{y}-{mm:02d}" for y in range(int(rows[0]["month"][:4]), 2027) for mm in range(1, 13))
                        if rows[0]["month"] <= m <= rows[-1]["month"] and m not in by_month],
        "checks_applied": [{"month": m, "note": r.get("checks")} for m, r in sorted(monthly.items()) if r.get("checks")],
        "fy_table": fy_table, "verified_fy": verified, "monthly": rows,
        "peers": peers, "india": india, "gap_vs_india": gap_vs_india,
        "season": season, "forecast": fc,
        "intl_2026": intl_2026, "intl_lost_mar_jul_2026": intl_lost,
        "cargo_fy": cargo_fy,
        "flight_validation": validation, "network": network, "ref_month": ref_month,
        "flight_days": len({r["date"] for r in flights}),
        "scenarios": scenarios, "context": CONTEXT, "wiki_src": WIKI_SRC,
    }


# ------------------------------------------------------------------ Excel
def write_excel(d: dict, path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    INK = "17324D"
    wb = Workbook()

    def sheet(title, header, data, widths=None):
        ws = wb.create_sheet(title)
        ws.append(header)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor=INK)
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for r in data:
            ws.append(r)
        for i, h in enumerate(header, 1):
            w = max([len(str(h))] + [len(str(r[i - 1])) for r in data[:300] if i - 1 < len(r) and r[i - 1] is not None])
            ws.column_dimensions[get_column_letter(i)].width = min(max(w + 2, 9), 60) if not widths else widths[i - 1]
        ws.freeze_panes = "A2"
        return ws

    def chart(ws, kind, title, cats_col, cols, n, anchor, stacked=False, ytitle=""):
        if n <= 0:
            return
        ch = BarChart() if kind == "bar" else LineChart()
        if kind == "bar" and stacked:
            ch.grouping, ch.overlap = "stacked", 100
        ch.title, ch.y_axis.title = title, ytitle
        for c in cols:
            ch.add_data(Reference(ws, min_col=c, min_row=1, max_row=n + 1), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=cats_col, min_row=2, max_row=n + 1))
        ch.height, ch.width = 9, 18
        ws.add_chart(ch, anchor)

    ws = wb.active
    ws.title = "Read me"
    lines = [
        ("Madurai Airport (IXM) – 10-year traffic review", True),
        (f"AAI monthly data {d['aai_range'][0]} to {d['aai_range'][1]} ({d['aai_months']} months); "
         f"flight-level data from AeroDataBox ({d['flight_days']} days). Generated {d['generated']}.", False),
        ("", False),
        ("Verification", True),
        (f"Financial years whose 12 monthly AAI figures sum exactly to the published AAI annual total: {', '.join(d['verified_fy'])}.", False),
        ("AeroDataBox flight counts vs AAI aircraft movements: " + "; ".join(
            f"{v['month']}: {v['aerodatabox_movements']} vs {v['aai_movements']} ({v['coverage_pct']}%)"
            for v in d["flight_validation"] if v["aai_movements"]), False),
        (f"AAI months not published / not found: {', '.join(d['aai_missing']) or 'none'} "
         "(interpolated only inside the forecast model).", False),
        ("Monthly values corrected or blanked by automated cross-checks: " +
         "; ".join(f"{c['month']} ({c['note']})" for c in d["checks_applied"]), False),
        ("", False),
        ("Important", True),
        ("Passengers, movements and cargo are AAI official figures. Peer-airport and all-India totals are AAI figures as "
         "tabulated on Wikipedia (see Sources) – verify before quoting.", False),
        ("Scenarios are what-if paths using observed growth rates, not forecasts. The 12-month forecast is a statistical model.", False),
        ("Flight-level analysis covers the months with complete AeroDataBox data only (see Flight_validation).", False),
    ]
    for t, bold in lines:
        ws.append([t])
        ws.cell(ws.max_row, 1).font = Font(bold=bold, size=14 if t.startswith("Madurai") else 11, color=INK if bold else "000000")
        ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True)
    ws.column_dimensions["A"].width = 130

    fyt = d["fy_table"]
    w = sheet("FY_summary", ["Financial year", "Months", "Passengers", "Domestic", "International", "Intl share %",
                             "Aircraft movements", "Passengers per movement", "Cargo (t)", "Published AAI total",
                             "Matches published", "Missing months"],
              [[f["fy"], f["months"], f["pax_total"], f["pax_dom"], f["pax_intl"], f["intl_share"], f["mov_total"],
                f["pax_per_mov"], round(f["frt_total"]) if f["frt_total"] is not None else None, f["published_total"],
                "Yes" if f["matches_published"] else ("partial year" if f["months"] < 12 else "No"),
                ", ".join(f["missing"])] for f in fyt])
    chart(w, "bar", "Passengers by financial year (AAI)", 1, [4, 5], len(fyt), "N2", stacked=True)

    m = d["monthly"]
    w = sheet("Monthly_AAI", ["Month", "Passengers", "Domestic", "International", "YoY %", "Movements", "Cargo dom (t)",
                              "Cargo intl (t)", "Cargo total (t)", "Source", "Cross-check note"],
              [[r["month"], r["pax_total"], r["pax_dom"], r["pax_intl"], r["pax_yoy_pct"], r["mov_total"], r["frt_dom"],
                r["frt_intl"], r["frt_total"], r["source"], r.get("checks", "")] for r in m])
    chart(w, "line", "Monthly passengers (AAI)", 1, [2], len(m), "M2")

    pe = d["peers"]
    w = sheet("Peers", ["Airport", "FY18-19 passengers", "FY24-25", "FY25-26", "Index FY25-26 (FY18-19=100)",
                        "CAGR FY18-19→25-26 %", "Growth FY25-26 %", "Rank FY18-19", "Rank FY25-26"],
              [[p["airport"], p["fy1819"], p["fy2425"], p["fy2526"], p["index_vs_1819"], p["cagr_1819_2526"],
                p["growth_2526"], p["rank_1819"], p["rank_2526"]] for p in pe] +
              [["All India", d["india"]["fy1819"], None, d["india"]["fy2526"], d["india"]["index_vs_1819"],
                d["india"]["cagr_1819_2526"], d["india"]["growth_2526"], None, None]])
    chart(w, "bar", "Recovery index FY25-26 vs FY18-19 (=100)", 1, [5], len(pe) + 1, "K2")

    se = d["season"]
    w = sheet("Seasonality", ["Month", "Seasonal index (1.00 = average month)", "Typical travel peaks"],
              [[s["name"], s["index"], "; ".join(s["tags"])] for s in se])
    chart(w, "bar", "Seasonal index by month", 1, [2], 12, "E2")

    ii = d["intl_2026"]
    w = sheet("International_2026", ["Month", "Intl 2026", "Intl 2025", "Intl change %", "Domestic 2026", "Domestic 2025",
                                     "Domestic change %"],
              [[x["month"], x["intl_2026"], x["intl_2025"], x["change_pct"], x["dom_2026"], x["dom_2025"],
                x["dom_change_pct"]] for x in ii])
    chart(w, "bar", "International passengers 2026 vs 2025", 1, [2, 3], len(ii), "I2")

    cg = d["cargo_fy"]
    w = sheet("Cargo", ["Financial year", "Cargo (tonnes)", "Months with data"], [[c["fy"], c["tonnes"], c["months"]] for c in cg])
    chart(w, "bar", "Cargo tonnes by financial year (AAI)", 1, [2], len(cg), "E2")

    sheet("Flight_validation", ["Month", "Days collected", "AeroDataBox movements", "AAI movements", "Coverage %"],
          [[v["month"], v["days"], v["aerodatabox_movements"], v["aai_movements"], v["coverage_pct"]] for v in d["flight_validation"]])
    rows = []
    for mth, n in d["network"].items():
        for r in n["routes"]:
            rows.append([mth, r["city"], r["iata"], "International" if r["international"] else "Domestic",
                         r["weekly_departures"], ", ".join(r["airlines"]), r["atr_share_pct"]])
    sheet("Network_routes", ["Month", "Destination", "IATA", "Type", "Weekly departures", "Airlines", "ATR 72 share %"], rows)
    rows = [[mth, a["airline"], a["flights"], a["share_pct"]] for mth, n in d["network"].items() for a in n["airlines"]]
    sheet("Airlines", ["Month", "Airline", "Flights", "Share %"], rows)
    rows = [[mth, a["aircraft"], a["share_pct"]] for mth, n in d["network"].items() for a in n["aircraft"]]
    sheet("Fleet", ["Month", "Aircraft", "Share of movements %"], rows)
    if d["ref_month"]:
        h = d["network"][d["ref_month"]]["hourly"]
        w = sheet("Hourly", ["Hour (local)", f"Movements in {d['ref_month']}"], [[f"{i:02d}:00", v] for i, v in enumerate(h)])
        chart(w, "bar", f"Movements by hour – {d['ref_month']}", 1, [2], 24, "D2")

    fc = d["forecast"]
    if fc.get("available"):
        w = sheet("Forecast_12m", ["Month", "Forecast passengers", "Low (80%)", "High (80%)", "Seasonal index", "Season"],
                  [[p["month"], p["forecast"], p["low"], p["high"], p["seasonal_index"], "; ".join(p["season"])] for p in fc["points"]])
        chart(w, "line", "12-month passenger forecast", 1, [2, 3, 4], len(fc["points"]), "H2")
    sc = d["scenarios"]
    hdr = ["Financial year"] + [f"{s['name']} ({s['cagr_pct']:+.2f}%/yr)" for s in sc]
    w = sheet("Scenarios_2031", hdr, [[sc[0]["path"][i]["fy"]] + [s["path"][i]["passengers"] for s in sc] for i in range(6)])
    chart(w, "line", "What-if passenger paths to FY 2030-31", 1, list(range(2, 2 + len(sc))), 6, "F2")
    sheet("Recommendations", ["#", "Ask", "Evidence", "Addressed to", "Priority"], [list(x) for x in d.get("recommendations", [])])
    sheet("Context_sources", ["Fact", "Source"], [list(x) for x in d["context"]] +
          [["Peer and all-India annual totals", d["wiki_src"]],
           ["Monthly passengers, movements, cargo", "AAI monthly Traffic News annexures II-IV (aai.aero)"],
           ["Flight schedules, airlines, aircraft, times", "AeroDataBox via RapidAPI"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def generate(out_dir: Path | None = None, recommendations: list | None = None) -> dict[str, Path]:
    d = compute()
    d["recommendations"] = recommendations or RECOMMENDATIONS(d)
    out = out_dir or (config.ROOT / "reports")
    out.mkdir(parents=True, exist_ok=True)
    stem = "IXM_10_year_review"
    j = out / f"{stem}.json"
    j.write_text(json.dumps(d, default=str, indent=1), encoding="utf-8")
    paths = {"json": j, "xlsx": write_excel(d, out / f"{stem}.xlsx")}
    p = out / f"{stem}.pptx"
    subprocess.run(["node", str(config.ROOT / "decade_pptx.js"), str(j), str(p)], check=True)
    paths["pptx"] = p
    return paths


def _normal_month(d: dict) -> str | None:
    """Latest complete flight month with the Gulf routes operating (i.e. not during the 2026 suspension)."""
    for m in sorted(d["network"], reverse=True):
        if any(r["iata"] in ("DXB", "AUH") for r in d["network"][m]["routes"]):
            return m
    return d["ref_month"]


def RECOMMENDATIONS(d: dict) -> list[tuple]:
    """Asks, each tied to evidence computed above."""
    latest = d["network"].get(d["ref_month"], {}) if d["ref_month"] else {}
    nm = _normal_month(d)
    normal = d["network"].get(nm, {}) if nm else {}
    def route(n, iata):
        return next((r for r in n.get("routes", []) if r["iata"] == iata), {})
    maa, blr = route(normal, "MAA"), route(normal, "BLR")
    maa2, blr2 = route(latest, "MAA"), route(latest, "BLR")
    pre = next((f for f in d["fy_table"] if f["fy"] == "2018-19"), {})
    ind = next(p for p in d["peers"] if p["airport"].startswith("Madurai"))
    igo_n = next((a["share_pct"] for a in normal.get("airlines", []) if a["airline"] == "IndiGo"), None)
    igo_l = next((a["share_pct"] for a in latest.get("airlines", []) if a["airline"] == "IndiGo"), None)
    fy = {f["fy"]: f for f in d["fy_table"]}
    c25, c26 = fy.get("2024-25", {}), fy.get("2025-26", {})
    return [
        (1, "Restore Gulf services in full and add Sharjah, Muscat, Kuwait and Doha",
         f"International passengers fell by about {d['intl_lost_mar_jul_2026']:,} in Mar–Jul 2026 vs the same months of 2025 "
         f"during the Gulf suspension; international share was {pre.get('intl_share')}% in FY18-19",
         "Airlines (IndiGo, Air India Express, SpiceJet), MoCA", "High"),
        (2, "Use the new international status: seek point-of-call rights for foreign carriers (Gulf, Sri Lanka, Malaysia, Singapore)",
         "International status approved Mar 2026; Madurai was outside bilateral agreements, which kept foreign airlines away",
         "MoCA, Ministry of External Affairs, State Government", "High"),
        (3, "Upgauge Chennai and Bengaluru from ATR 72 turboprops to A320-family jets",
         "Share of flights on 78-seat ATR 72s – " + "; ".join(
             f"{m}: Chennai {route(n, 'MAA').get('atr_share_pct')}% ({route(n, 'MAA').get('weekly_departures')} dep/wk), "
             f"Bengaluru {route(n, 'BLR').get('atr_share_pct')}% ({route(n, 'BLR').get('weekly_departures')} dep/wk)"
             for m, n in sorted(d["network"].items())),
         "IndiGo, Air India", "High"),
        (4, "Use the 24-hour licence: night slots for international and long domestic flights",
         f"{sum(n['night_movements'] for n in d['network'].values())} scheduled movements between 22:00 and 06:00 across "
         f"{len(d['network'])} complete months of flight data ({', '.join(sorted(d['network']))}), although 24-hour operations began in Oct 2024",
         "AAI Madurai, airlines", "Medium"),
        (5, "Attract a second large domestic airline to reduce dependence on one carrier",
         "IndiGo share of movements – " + "; ".join(
             f"{m}: {next((a['share_pct'] for a in n['airlines'] if a['airline'] == 'IndiGo'), 0)}%" for m, n in sorted(d["network"].items())),
         "Air India group, Akasa Air, State Government (incentives)", "Medium"),
        (6, "New direct domestic routes to Kolkata, Pune, Ahmedabad, Goa and Kochi (demand to be confirmed with airline O&D data)",
         f"{len(normal.get('routes', []))} regular destinations in {nm}; Madurai fell from rank "
         f"{ind['rank_1819']} to {ind['rank_2526']} among Indian airports between FY18-19 and FY25-26",
         "Airlines, State Government (viability-gap / UDAN-type support)", "Medium"),
        (7, "Complete the remaining land handover and fix a timeline for the 3,810 m runway",
         "109.94 of 653.35 acres pending (Aug 2025); wide-body capability needed for long-haul and heavy cargo",
         "State Government, AAI", "Medium"),
        (8, "Grow air cargo: export facilitation for perishables and regional produce",
         f"Cargo {c26.get('frt_total', 0):,.0f} t in 11 months of FY25-26 vs {c25.get('frt_total', 0):,.0f} t in all of FY24-25, "
         "while passengers fell", "AAI Cargo Logistics, Customs, State export agencies", "Medium"),
        (9, "Publish route-level origin–destination data so routes can be planned on evidence",
         "Only monthly airport totals are public; route-level demand is unknown", "DGCA, AAI", "Low"),
    ]

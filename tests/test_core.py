import json
from datetime import date

import pytest

from ixm import aai, aerodatabox, analytics as an, forecast, opensky, reference, store
from ixm.build import build
from ixm.report import build_report_data, generate, write_excel

from .conftest import FIXTURES, synthetic_flights, synthetic_monthly


# ---------------------------------------------------------------- AeroDataBox
def test_parse_fids_fields():
    rows = aerodatabox.parse_fids(json.loads((FIXTURES / "aerodatabox_sample.json").read_text()))
    assert len(rows) == 4
    dep = next(r for r in rows if r["flight_no"] == "6E7012")
    assert dep["direction"] == "departure" and dep["other_iata"] == "MAA" and not dep["is_international"]
    assert dep["sched_local"].startswith("2026-10-30 06:15") and dep["actual_local"].startswith("2026-10-30 06:35")
    sin = next(r for r in rows if r["flight_no"] == "IX685")
    assert sin["is_international"] and sin["other_country"] == "SG" and sin["direction"] == "arrival"
    cargo = next(r for r in rows if r["flight_no"] == "BZ501")
    assert cargo["is_cargo"] and cargo["date"] == "2026-10-31"   # local date at Madurai


def test_windows_cover_day():
    w = aerodatabox.windows_for_day(date(2026, 10, 30))
    assert w == [("2026-10-30T00:00", "2026-10-30T11:59"), ("2026-10-30T12:00", "2026-10-30T23:59")]


def test_fetch_without_key_is_noop(monkeypatch):
    monkeypatch.delenv("AERODATABOX_KEY", raising=False)
    assert aerodatabox.fetch_day(date(2026, 10, 30)) == []


# ---------------------------------------------------------------- reference / analytics
def test_seats_and_callsigns():
    assert reference.seats_for("Airbus A320neo") == 186
    assert reference.seats_for("ATR 72-600") == 78
    assert reference.seats_for("Boeing 737 MAX 8") == 189
    assert reference.seats_for("") is None
    assert reference.airline_from_callsign("IGO7012") == "IndiGo"
    assert reference.looks_cargo("Blue Dart Aviation")


def test_summarize_and_delay():
    rows = aerodatabox.parse_fids(json.loads((FIXTURES / "aerodatabox_sample.json").read_text()))
    s = an.summarize(rows, 0.8)
    assert s["movements"] == 3 and s["cancelled"] == 1 and s["cargo"] == 1
    assert an.delay_minutes(next(r for r in rows if r["flight_no"] == "6E7012")) == 20
    # passenger estimate excludes cargo: ATR72 78 + 737 MAX 189 seats
    assert s["est_seats"] == 78 + 189 and s["est_pax"] == round(267 * 0.8)


def test_store_upsert_dedup(tmp_root):
    rows = synthetic_flights(date(2026, 10, 1), 3)
    assert store.upsert(rows) == len(rows)
    assert store.upsert(rows) == 0                       # idempotent
    changed = dict(rows[0], status="Delayed")
    assert store.upsert([changed]) == 1
    assert len(store.load_all()) == len(rows)
    assert isinstance(store.load_all()[0]["is_cargo"], bool)


def test_calibration(tmp_root):
    flights = synthetic_flights(date(2026, 9, 1), 30)
    seats = sum(an.seats(r) for r in flights if an.is_operated(r) and not r["is_cargo"])
    cal = an.calibrate_load_factor(flights, {"2026-09": {"pax_total": str(round(seats * 0.82))}})
    assert cal["2026-09"] == pytest.approx(0.82, abs=0.002)
    lf, note = an.current_load_factor(cal)
    assert lf == pytest.approx(0.82, abs=0.002) and "calibrated" in note


# ---------------------------------------------------------------- AAI parsing
def _make_pdf(path, sections):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=A4)
    for heading, rows in sections:
        y = 800
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, heading)
        c.setFont("Helvetica", 9)
        c.drawString(40, y - 20, "SL AIRPORT  OCTOBER 2026  OCTOBER 2025  % CHANGE  2026-27  2025-26  % CHANGE")
        y -= 40
        for row in rows:
            x = 40
            for cell in row:
                c.drawString(x, y, cell)
                x += 70
            y -= 14
        c.showPage()
    c.save()


def test_parse_real_pdf_layout(tmp_path):
    p = tmp_path / "Oct2k26Annex3.pdf"
    _make_pdf(p, [
        ("ANNEXURE-III A INTERNATIONAL PASSENGERS", [["32", "TRICHY", "150,000", "140,000", "7.1", "900000", "850000", "5.9"],
                                                     ["33", "MADURAI", "28559", "23397", "22.1", "252121", "226342", "11.4"]]),
        ("ANNEXURE-III B DOMESTIC PASSENGERS", [["40", "MADURAI", "95,000", "90,000", "5.6", "660000", "640000", "3.1"]]),
        ("ANNEXURE-III C TOTAL PASSENGERS", [["38", "MADURAI", "123559", "113397", "9.0", "912121", "866342", "5.3"]]),
    ])
    res = aai.parse_annex_rows(aai.pdf_rows(p.read_bytes()), 3)
    assert res.sections["international"].month == 28559
    assert res.sections["international"].ytd_prev_year == 226342
    assert res.sections["domestic"].month == 95000
    assert res.sections["total"].month == 123559
    assert res.warnings == []


def test_parse_split_rows_and_mismatch_warning():
    rows = ["ANNEXURE-IIIA. INTERNATIONAL PASSENGERS",
            "32 · 28559 · 23397 · 252121 · 226342", "MADURAI · 22.1 · 11.4",
            "ANNEXURE-IIIB DOMESTIC PASSENGERS", "41 MADURAI 90000 85000 5.9 600000 580000 3.4",
            "ANNEXURE-IIIC TOTAL PASSENGERS", "37 MADURAI 200000 108397 9.0 852121 806342 5.7"]
    res = aai.parse_annex_rows(rows, 3)
    assert res.sections["international"].month == 28559
    assert any("!= total" in w for w in res.warnings)


def test_derives_missing_total_and_freight_decimals():
    rows = ["ANNEXURE-IV A INTERNATIONAL FREIGHT (TONNES)", "12 MADURAI 120.5 98.2 22.7 700.1 650.0 7.7",
            "ANNEXURE-IV B DOMESTIC FREIGHT (TONNES)", "20 MADURAI 180.0 170.0 5.9 1200.0 1100.0 9.1"]
    res = aai.parse_annex_rows(rows, 4)
    assert res.sections["international"].month == pytest.approx(120.5)
    assert res.sections["total"].month == pytest.approx(300.5)


def test_discover_links_and_candidates():
    html = ('<a href="/sites/default/files/traffic-news/Sep2k26Annex3.pdf">x</a>'
            '<a href="https://www.aai.aero/sites/default/files/traffic-news/Aug2K26annex2_0.pdf">y</a>'
            '<a href="/sites/default/files/traffic-news/TRDEC12.pdf">z</a>')
    links = aai.discover_links(html)
    assert links[(2026, 9, 3)].endswith("Sep2k26Annex3.pdf")
    assert (2026, 8, 2) in links and len(links) == 2
    names = aai.candidate_names(2026, 3, 3)
    assert "Mar2k26Annex3.pdf" in names and "Mar2k26Annex3_0.pdf" in names and "mar2K26annex3.pdf" in names


def test_apply_annex_fills_prev_year_and_manual_override(tmp_root):
    res = aai.parse_annex_rows(["ANNEXURE-III C TOTAL PASSENGERS", "38 MADURAI 123559 113397 9.0 912121 866342 5.3"], 3)
    table = {}
    aai.apply_annex(table, 2026, 10, 3, res, "u")
    assert table["2026-10"]["pax_total"] == "123559" and table["2025-10"]["pax_total"] == "113397"
    aai.write_monthly(tmp_root / "data" / "aai_monthly.csv", table)
    (tmp_root / "data" / "aai_monthly_manual.csv").write_text(
        "month,pax_total,source\n2026-10,124000,manual fix\n", encoding="utf-8")
    merged = aai.merged_monthly()
    assert merged["2026-10"]["pax_total"] == "124000" and merged["2025-10"]["pax_total"] == "113397"


class FakeFetcher(aai.Fetcher):
    def __init__(self, pdf):
        self.pdf = pdf
        self.index = {}

    def load_index(self, pages=3):
        pass

    def fetch(self, year, month, annex):
        return (self.pdf, "fake://x") if annex == 3 else (None, "")


def test_collect_end_to_end(tmp_root, tmp_path):
    p = tmp_path / "x.pdf"
    _make_pdf(p, [("ANNEXURE-III C TOTAL PASSENGERS", [["38", "MADURAI", "123559", "113397", "9.0", "912121", "866342", "5.3"]])])
    summary = aai.collect(date(2026, 9, 1), date(2026, 10, 1), fetcher=FakeFetcher(p.read_bytes()))
    assert summary["months_ok"] == 2
    assert (tmp_root / "data" / "aai_fetch_log.csv").exists()


# ---------------------------------------------------------------- forecast
def test_forecast_needs_history():
    fc = forecast.monthly_forecast({"2026-01": {"pax_total": "100"}})
    assert not fc["available"] and "24" in fc["reason"]


def test_forecast_recovers_seasonality():
    fc = forecast.monthly_forecast(synthetic_monthly())
    assert fc["available"] and len(fc["points"]) == 12
    assert fc["points"][0]["month"] == "2026-10"
    pts = {p["month"]: p for p in fc["points"]}
    assert pts["2027-05"]["forecast"] > pts["2027-07"]["forecast"]        # summer peak > July lull
    assert fc["backtest_mape_pct"] is not None and fc["backtest_mape_pct"] < 5
    assert all(p["low"] <= p["forecast"] <= p["high"] for p in fc["points"])
    assert forecast.fiscal_year("2026-03") == "2025-26" and forecast.fiscal_year("2026-04") == "2026-27"


# ---------------------------------------------------------------- OpenSky
def test_parse_states_phase_and_distance():
    payload = {"states": [
        ["800c1a", "IGO7012 ", "India", 0, 0, 78.10, 9.90, 900.0, False, 70.0, 300.0, -4.0, None, 950.0, None, False, 0],
        ["800c1b", "AXB685", "India", 0, 0, 78.60, 10.30, 10000.0, False, 230.0, 90.0, 0.0, None, 10100.0, None, False, 0],
        ["800c1c", None, "India", 0, 0, None, None, None, True, 0, 0, 0, None, None, None, False, 0]]}
    ac = opensky.parse_states(payload)
    assert len(ac) == 2 and ac[0]["callsign"] == "IGO7012" and ac[0]["phase"] == "approaching"
    assert ac[0]["airline"] == "IndiGo" and ac[0]["distance_km"] < ac[1]["distance_km"]
    assert ac[1]["phase"] == "overflying"


# ---------------------------------------------------------------- build & reports
def _seed(tmp_root):
    store.upsert(synthetic_flights(date(2026, 9, 1), 61))
    aai.write_monthly(tmp_root / "data" / "aai_monthly.csv", synthetic_monthly())


def test_build_outputs(tmp_root):
    _seed(tmp_root)
    s = build(date(2026, 10, 31))
    files = {p.name for p in (tmp_root / "site" / "data").glob("*.json")}
    assert {"summary.json", "daily.json", "airlines.json", "routes.json", "forecast.json", "aai_monthly.json",
            "aai_annual.json", "live.json", "weekly_flights.json", "monthly_flights.json"} <= files
    assert s["kpi"]["last7"]["movements"] > 0 and s["board"]
    fc = json.loads((tmp_root / "site" / "data" / "forecast.json").read_text())
    assert fc["monthly"]["available"] and len(fc["next7"]) == 1   # only 31 Oct has schedule data
    air = json.loads((tmp_root / "site" / "data" / "airlines.json").read_text())
    assert air["last30"][0]["airline"] == "IndiGo"


def test_build_empty_repo(tmp_root):
    s = build(date(2026, 10, 31))
    assert s["kpi"]["last7"]["movements"] == 0 and s["latest_aai_month"] is None


@pytest.mark.parametrize("kind,ref", [("weekly", date(2026, 10, 21)), ("monthly", date(2026, 9, 15))])
def test_report_data_and_excel(tmp_root, kind, ref):
    _seed(tmp_root)
    d = build_report_data(kind, ref)
    assert d["kpi"]["movements"] > 0 and d["airlines"] and d["insights"]
    if kind == "monthly":
        assert d["aai_this_month"]["month"] == "2026-09" and d["days_with_data"] == 30
    from openpyxl import load_workbook
    path = write_excel(d, tmp_root / f"{kind}.xlsx")
    wb = load_workbook(path)
    assert {"Summary", "Daily", "Airlines", "Routes", "Aircraft types", "Hourly", "AAI monthly",
            "Forecast", "Flights"} <= set(wb.sheetnames)
    assert len(wb["Daily"]._charts) == 1 and len(wb["Airlines"]._charts) == 1


def test_report_empty_period(tmp_root):
    d = build_report_data("weekly", date(2026, 10, 21))
    assert d["kpi"]["movements"] == 0 and "No flight-schedule data" in d["insights"][0]
    write_excel(d, tmp_root / "empty.xlsx")


@pytest.mark.parametrize("seeded", [True, False])
def test_generate_pptx(tmp_root, seeded):
    import shutil
    if not shutil.which("node"):
        pytest.skip("node not installed")
    if seeded:
        _seed(tmp_root)
    from ixm import config
    import os
    os.symlink(config.ROOT.__class__(__file__).resolve().parent.parent / "report_pptx.js", tmp_root / "report_pptx.js")
    paths = generate("monthly", date(2026, 9, 1), tmp_root / "reports")
    from pptx import Presentation
    prs = Presentation(paths["pptx"])
    assert len(prs.slides) == 10

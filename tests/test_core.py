import json
from datetime import date, timedelta

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
    assert names[0] == "Mar2k26Annex3.pdf" and "Mar2k26Annex3_0.pdf" in names and "mar2k26annex3.pdf" in names
    assert len(names) <= 10 and "April2k26Annex3.pdf" in aai.candidate_names(2026, 4, 3) and "Mar2k26Annex_3.pdf" in names and aai.candidate_names(2008, 9, 3)[4] == "sep2k8annex3.pdf"


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
        self.requests = 0

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


def test_fill_airport_from_name(tmp_root):
    row = {"date": "2026-10-31", "direction": "arrival", "flight_no": "SG24", "airline": "SpiceJet",
           "other_name": "Dubai", "other_iata": "", "other_country": "", "is_international": False,
           "is_cargo": False, "sched_local": "2026-10-31 11:10+05:30"}
    store.upsert([row])
    r = store.load_all()[0]
    assert r["is_international"] and r["other_iata"] == "DXB" and r["other_country"] == "AE"
    assert reference.fill_airport({"other_name": "Chennai", "other_iata": "", "other_country": ""})["other_country"] == "IN"


class DownFetcher(aai.Fetcher):
    """Simulates aai.aero timing out on every request."""
    def __init__(self):
        super().__init__(delay=0)

    def load_index(self, pages=3):
        pass

    def _request(self, url, **kw):
        import requests
        self.errors_in_row += 1
        if self.errors_in_row >= self.MAX_CONSECUTIVE_ERRORS:
            raise aai.SiteUnreachable("simulated outage")
        return None


def test_collect_stops_fast_when_site_down(tmp_root):
    s = aai.collect(date(2018, 4, 1), date(2026, 9, 1), fetcher=DownFetcher())
    assert "simulated outage" in s["stopped"] and s["months_ok"] == 0
    assert (tmp_root / "data" / "aai_fetch_log.csv").read_text().count("stopped") == 1


def test_collect_newest_first_saves_each_month_and_resumes(tmp_root, tmp_path):
    p = tmp_path / "x.pdf"
    _make_pdf(p, [("ANNEXURE-III C TOTAL PASSENGERS", [["38", "MADURAI", "123559", "113397", "9.0", "912121", "866342", "5.3"]])])
    fx = FakeFetcher(p.read_bytes())
    s1 = aai.collect(date(2026, 1, 1), date(2026, 9, 1), fetcher=fx, max_months=3)
    assert s1["months_ok"] == 3 and "run again" in s1["stopped"]
    saved = aai.read_monthly(tmp_root / "data" / "aai_monthly.csv")
    assert {"2026-09", "2026-08", "2026-07"} <= set(saved)          # newest months first
    s2 = aai.collect(date(2026, 1, 1), date(2026, 9, 1), fetcher=fx)
    assert s2["months_skipped"] >= 3 and s2["months_ok"] + s2["months_skipped"] == 9 and not s2["stopped"]


def test_freight_serial_not_taken_as_tonnes():
    rows = ["ANNEXURE-IV A INTERNATIONAL FREIGHT (IN TONNES)", "8 MADURAI 98.60 83.20 18.5 700.10 650.00 7.7",
            "ANNEXURE-IV B DOMESTIC FREIGHT (IN TONNES)", "11 MADURAI 311.00 290.10 - 3000.50 2800.20 7.1",
            "ANNEXURE-IV C TOTAL FREIGHT (IN TONNES)", "8 मदुरै MADURAI 409.60 373.30 9.7 3700.60 3450.20 7.3"]
    res = aai.parse_annex_rows(rows, 4)
    assert res.sections["international"].month == pytest.approx(98.6)
    assert res.sections["domestic"].month == pytest.approx(311.0)
    assert res.sections["domestic"].ytd == pytest.approx(3000.5)
    assert res.sections["total"].month == pytest.approx(409.6)
    assert res.warnings == []


def test_discover_full_month_and_underscore_names():
    html = ('<a href="/sites/default/files/traffic-news/April2k26Annex3.pdf">a</a>'
            '<a href="/sites/default/files/traffic-news/Sep2k26Annex_4.pdf">b</a>')
    links = aai.discover_links(html)
    assert (2026, 4, 3) in links and (2026, 9, 4) in links


class CrashFetcher(FakeFetcher):
    def fetch(self, year, month, annex):
        if (year, month) == (2026, 8):
            raise ValueError("boom")
        return super().fetch(year, month, annex)


def test_collect_continues_after_unexpected_error(tmp_root, tmp_path):
    p = tmp_path / "x.pdf"
    _make_pdf(p, [("ANNEXURE-III C TOTAL PASSENGERS", [["38", "MADURAI", "123559", "113397", "9.0", "912121", "866342", "5.3"]])])
    s = aai.collect(date(2026, 6, 1), date(2026, 9, 1), fetcher=CrashFetcher(p.read_bytes()))
    assert s["errors"] == 1 and s["months_ok"] == 3
    assert "error: ValueError" in (tmp_root / "data" / "aai_fetch_log.csv").read_text()


def test_april_derived_from_may_ytd_and_not_overwritten():
    may = aai.parse_annex_rows(["ANNEXURE-III C TOTAL PASSENGERS", "38 MADURAI 120000 110000 9.1 245000 228000 7.5"], 3)
    bad_april = aai.parse_annex_rows(["ANNEXURE-III C TOTAL PASSENGERS", "38 MADURAI 194670 105000 85.4 194670 105000 85.4"], 3)
    table = {}
    aai.apply_annex(table, 2019, 5, 3, may, "u")
    assert table["2019-04"]["pax_total"] == "125000" and table["2018-04"]["pax_total"] == "118000"
    aai.apply_annex(table, 2019, 4, 3, bad_april, "u")          # later direct April read must not overwrite
    assert table["2019-04"]["pax_total"] == "125000" and table["2019-04"]["source"] == aai.APRIL_DERIVED


def test_impossible_cargo_ignored_and_inconsistent_rows_cleaned():
    res = aai.parse_annex_rows(["ANNEXURE-IV C TOTAL FREIGHT", "8 MADURAI 107112 98000 9.3 300000 280000 7.1"], 4)
    table = {}
    aai.apply_annex(table, 2017, 7, 4, res, "u")
    assert not table.get("2017-07", {}).get("frt_total")
    from ixm.build import clean_monthly
    c = clean_monthly({"2018-04": {"month": "2018-04", "frt_dom": "370", "frt_intl": "31", "frt_total": "370",
                                   "pax_dom": "100", "pax_intl": "20", "pax_total": "120"}})
    assert c["2018-04"]["frt_total"] == "" and c["2018-04"]["pax_total"] == "120"


def test_forecast_bridges_short_gap():
    m = synthetic_monthly()
    del m["2025-11"]
    fc = forecast.monthly_forecast(m)
    assert fc["available"] and fc["interpolated_months"] == ["2025-11"]
    assert fc["trained_on"].startswith("2017")
    m2 = synthetic_monthly()
    for k in ("2025-06", "2025-07", "2025-08", "2025-09"):
        del m2[k]                                   # 4-month gap: too long to bridge
    fc2 = forecast.monthly_forecast(m2)
    assert not fc2["available"] and "12" in fc2["reason"]      # only Oct 2025 onwards is usable


def test_cross_check_prefers_revised_and_blanks_column_slip():
    from ixm.build import clean_monthly
    data = {
        "2024-12": {"month": "2024-12", "frt_dom": "166", "frt_intl": "534", "frt_total": "700"},
        # current read slipped last year's intl/total into this year's columns
        "2025-12": {"month": "2025-12", "frt_dom": "232", "frt_intl": "534", "frt_total": "766",
                    "pax_dom": "96000", "pax_intl": "20000", "pax_total": "116000"},
        # first read wrong, revised copy from next year's report is consistent and differs
        "2019-04": {"month": "2019-04", "pax_dom": "182841", "pax_intl": "11829", "pax_total": "194670",
                    "pax_dom_rev": "92000", "pax_intl_rev": "22000", "pax_total_rev": "114000"},
    }
    c = clean_monthly(data)
    assert c["2025-12"]["frt_total"] == "" and "frt" in c["2025-12"]["checks"]
    assert c["2025-12"]["pax_total"] == "116000"
    assert c["2019-04"]["pax_total"] == 114000 and "revised" in c["2019-04"]["checks"]


def test_column_slip_detected_against_same_report_prev_year_column():
    from ixm.build import clean_monthly
    data = {"2024-12": {"month": "2024-12", "frt_dom": "166", "frt_intl": "129", "frt_total": "296",
                        "frt_dom_rev": "166", "frt_intl_rev": "534", "frt_total_rev": "766"},
            "2025-12": {"month": "2025-12", "frt_dom": "232", "frt_intl": "534", "frt_total": "766"}}
    c = clean_monthly(data)
    assert c["2025-12"]["frt_total"] == "" and c["2024-12"]["frt_total"] == "296"


def test_fetch_days_skips_bad_days_saves_progress_and_stops_on_quota(monkeypatch):
    calls, saved = [], []

    def fake(d, key=None, session=None):
        calls.append(d)
        if d.day == 2:
            raise ValueError("HTTP 400: date out of range")
        if d.day == 4:
            raise aerodatabox.QuotaExceeded("Too many requests")
        return [{"date": d.isoformat()}]

    monkeypatch.setattr(aerodatabox, "fetch_day", fake)
    days = [date(2026, 1, i) for i in range(1, 7)]
    res = aerodatabox.fetch_days(days, key="k", on_day=lambda d, rows: saved.append(d))
    assert res["ok"] == 2 and [d for d, _ in res["failed"]] == ["2026-01-02"]
    assert "quota" in res["stopped"] and len(calls) == 4          # stopped at day 4, days 5-6 untouched
    assert saved == [date(2026, 1, 1), date(2026, 1, 3)]          # progress saved day by day


def test_cli_caps_back_mode(monkeypatch, tmp_root, capsys):
    from ixm import __main__ as cli
    seen = {}
    monkeypatch.setattr(aerodatabox, "fetch_days", lambda days, on_day=None: seen.setdefault("days", days) and
                        {"rows": [], "ok": 0, "failed": [], "stopped": ""})
    cli.main(["flights", "--back", "2000", "--ahead", "0"])
    out = capsys.readouterr().out
    assert len(seen["days"]) == 31 and "limited to 31 days" in out
    assert max(seen["days"]) == cli._today()                         # newest days kept first


def test_cli_back_mode_progresses_past_collected_days(monkeypatch, tmp_root):
    from ixm import __main__ as cli
    today = cli._today()
    store.upsert([{"date": (today - timedelta(days=i)).isoformat(), "direction": "arrival", "flight_no": f"X{i}",
                   "sched_local": "", "is_cargo": False, "is_international": False} for i in range(2, 40)])
    seen = {}
    monkeypatch.setattr(aerodatabox, "fetch_days", lambda days, on_day=None: seen.setdefault("days", days) and
                        {"rows": [], "ok": 0, "failed": [], "stopped": ""})
    cli.main(["flights", "--back", "100", "--ahead", "0"])
    got = sorted(seen["days"])
    assert today in got and today - timedelta(days=1) in got            # recent days always refreshed
    assert today - timedelta(days=10) not in got                          # already collected: skipped
    assert min(got) <= today - timedelta(days=40)                         # moves into older history


def test_cli_skips_dates_beyond_history_without_calls(monkeypatch, tmp_root, capsys):
    from ixm import __main__ as cli
    seen = {}
    monkeypatch.setattr(aerodatabox, "fetch_days", lambda days, on_day=None: seen.setdefault("days", list(days)) is not None and
                        {"rows": [], "ok": 0, "failed": [], "stopped": ""})
    cli.main(["flights", "--from", "2021-05-01", "--to", "2021-05-20"])
    assert "keeps only 365 days" in capsys.readouterr().out and seen["days"] == []


def test_yearly_report_like_for_like(tmp_root):
    m = synthetic_monthly()
    del m["2025-11"]
    aai.write_monthly(tmp_root / "data" / "aai_monthly.csv", m)
    d = build_report_data("yearly", date(2025, 6, 1))
    a, p = d["aai_this_month"], d["aai_prev_year"]
    assert a["month"] == "FY 2025-26" and a["months"] == 11 and a["missing"] == ["2025-11"]
    assert a["lfl_months"] == 11 and p["months"] == 11                      # Nov excluded from both years
    assert len(d["fy_months"]) == 11 and d["start"] == "2025-04-01" and d["end"] == "2026-03-31"
    path = write_excel(d, tmp_root / "y.xlsx")
    from openpyxl import load_workbook
    assert "Months in FY" in load_workbook(path).sheetnames


def test_decade_review_computes_and_publishes(tmp_root):
    from ixm import decade
    from ixm.build import publish_reports
    store.upsert(synthetic_flights(date(2026, 6, 1), 30))
    aai.write_monthly(tmp_root / "data" / "aai_monthly.csv", synthetic_monthly())
    d = decade.compute()
    recs = decade.RECOMMENDATIONS(d)
    assert d["aai_months"] > 100 and d["forecast"]["available"] and len(recs) == 9
    assert d["network"] and d["scenarios"][1]["name"] == "Match India"
    p = decade.write_excel({**d, "recommendations": recs}, tmp_root / "reports" / "IXM_10_year_review.xlsx")
    from openpyxl import load_workbook
    assert {"FY_summary", "Peers", "Recommendations", "Scenarios_2031"} <= set(load_workbook(p).sheetnames)
    (tmp_root / "reports" / "IXM_yearly_report_FY2025-26.xlsx").write_bytes(b"x")
    kinds = {g["kind"] for g in publish_reports()}
    assert {"review", "yearly"} <= kinds

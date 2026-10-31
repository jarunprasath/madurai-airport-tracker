import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from ixm import config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    """Point every data/site path at a throw-away directory."""
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "FLIGHTS_DIR", tmp_path / "data" / "flights")
    monkeypatch.setattr(config, "SITE_DIR", tmp_path / "site")
    monkeypatch.setattr(config, "SITE_DATA_DIR", tmp_path / "site" / "data")
    monkeypatch.setattr(config, "AAI_MONTHLY_CSV", tmp_path / "data" / "aai_monthly.csv")
    monkeypatch.setattr(config, "AAI_MANUAL_CSV", tmp_path / "data" / "aai_monthly_manual.csv")
    monkeypatch.setattr(config, "AAI_ANNUAL_CSV", tmp_path / "data" / "aai_annual.csv")
    monkeypatch.setattr(config, "AAI_LOG_CSV", tmp_path / "data" / "aai_fetch_log.csv")
    (tmp_path / "data" / "flights").mkdir(parents=True)
    return tmp_path


# Synthetic test data only - NOT real Madurai figures.
ROUTES = [("IndiGo", "6E", "MAA", "Chennai", "IN", "A320neo"), ("IndiGo", "6E", "BLR", "Bengaluru", "IN", "ATR 72"),
          ("IndiGo", "6E", "BOM", "Mumbai", "IN", "A321neo"), ("SpiceJet", "SG", "DXB", "Dubai", "AE", "Boeing 737-800"),
          ("Air India Express", "IX", "SIN", "Singapore", "SG", "Boeing 737 MAX 8"),
          ("SriLankan Airlines", "UL", "CMB", "Colombo", "LK", "Airbus A320")]


def synthetic_flights(start: date, days: int, seed: int = 1) -> list[dict]:
    rnd = random.Random(seed)
    rows = []
    for i in range(days):
        d = start + timedelta(days=i)
        for j, (al, code, iata, city, cc, ac) in enumerate(ROUTES):
            for direction, hour in (("arrival", 6 + j * 2), ("departure", 7 + j * 2)):
                status = "Canceled" if rnd.random() < 0.03 else ("Arrived" if direction == "arrival" else "Departed")
                delay = rnd.choice([0, 5, 10, 20, 40])
                rows.append({
                    "date": d.isoformat(), "direction": direction, "flight_no": f"{code}{100 + j * 2 + (direction == 'departure')}",
                    "airline": al, "airline_iata": code, "airline_icao": "", "status": status, "is_cargo": False,
                    "is_international": cc != "IN", "aircraft_model": ac, "aircraft_reg": "",
                    "other_iata": iata, "other_icao": "", "other_name": city, "other_city": city, "other_country": cc,
                    "sched_local": f"{d.isoformat()} {hour:02d}:00+05:30",
                    "revised_local": "", "actual_local": f"{d.isoformat()} {hour:02d}:{delay:02d}+05:30",
                    "source": "test"})
        if i % 3 == 0:
            rows.append({**rows[-1], "flight_no": "BZ501", "airline": "Blue Dart Aviation", "is_cargo": True,
                         "direction": "arrival", "aircraft_model": "Boeing 737-300", "is_international": False,
                         "other_iata": "MAA", "other_city": "Chennai", "other_country": "IN",
                         "sched_local": f"{d.isoformat()} 01:30+05:30"})
    return rows


def synthetic_monthly(start_year=2017, end=(2026, 9)) -> dict:
    seas = {1: 1.10, 2: 0.95, 3: 0.97, 4: 1.02, 5: 1.12, 6: 1.00, 7: 0.90, 8: 0.92, 9: 0.93, 10: 1.00, 11: 1.03, 12: 1.08}
    out = {}
    y, m, i = start_year, 4, 0
    while (y, m) <= end:
        key = f"{y}-{m:02d}"
        base = 90000 * (1.004 ** i)
        if "2020-04" <= key <= "2021-12":
            base *= 0.3
        out[key] = {"month": key, "pax_total": str(round(base * seas[m])), "pax_intl": str(round(base * seas[m] * 0.15)),
                    "pax_dom": str(round(base * seas[m] * 0.85)), "mov_total": str(round(base * seas[m] / 115)),
                    "frt_total": "290.5", "source": "synthetic"}
        m += 1
        i += 1
        if m == 13:
            y, m = y + 1, 1
    return out

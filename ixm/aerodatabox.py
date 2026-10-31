"""AeroDataBox FIDS (arrivals/departures) collector for Madurai.

Endpoint (via RapidAPI):
  GET https://aerodatabox.p.rapidapi.com/flights/airports/icao/VOMD/{fromLocal}/{toLocal}
Docs: https://www.aerodatabox.com  /  RapidAPI listing "AeroDataBox".
The time window per call is limited (12 hours at the time of writing — verify in the
current docs), so a full day is fetched as two half-day windows.

The API key is read from the AERODATABOX_KEY environment variable (a GitHub Actions
secret). Without it the collector does nothing and says so.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import requests

from . import config
from .reference import looks_cargo

HOST = os.environ.get("AERODATABOX_HOST", "aerodatabox.p.rapidapi.com")
BASE = f"https://{HOST}"

FIELDS = [
    "date", "direction", "flight_no", "airline", "airline_iata", "airline_icao", "status",
    "is_cargo", "is_international", "aircraft_model", "aircraft_reg", "other_iata", "other_icao",
    "other_name", "other_city", "other_country", "sched_local", "revised_local", "actual_local",
    "source",
]


def _time(node: dict | None, key: str) -> str:
    """Return local time string from either the nested {local, utc} form or older flat keys."""
    if not node:
        return ""
    v = node.get(key)
    if isinstance(v, dict):
        return v.get("local") or v.get("utc") or ""
    if isinstance(v, str):
        return v
    flat = node.get(f"{key}Local")
    return flat or ""


def parse_fids(payload: dict[str, Any], direction_hint: str | None = None) -> list[dict[str, Any]]:
    """Flatten an AeroDataBox FIDS response into flight rows (one per movement at IXM)."""
    rows: list[dict[str, Any]] = []
    for key, direction in (("arrivals", "arrival"), ("departures", "departure")):
        for f in payload.get(key, []) or []:
            here = f.get("arrival" if direction == "arrival" else "departure") or {}
            other = f.get("departure" if direction == "arrival" else "arrival") or {}
            other_ap = other.get("airport") or {}
            airline = f.get("airline") or {}
            aircraft = f.get("aircraft") or {}
            sched = _time(here, "scheduledTime")
            revised = _time(here, "revisedTime")
            actual = _time(here, "runwayTime") or _time(here, "actualTime")
            day = (sched or revised or actual)[:10]
            country = (other_ap.get("countryCode") or "").upper()
            rows.append({
                "date": day,
                "direction": direction,
                "flight_no": (f.get("number") or "").replace(" ", ""),
                "airline": airline.get("name") or "Unknown",
                "airline_iata": airline.get("iata") or "",
                "airline_icao": airline.get("icao") or "",
                "status": f.get("status") or "",
                "is_cargo": bool(looks_cargo(airline.get("name"), f.get("isCargo"))),
                "is_international": bool(country and country != "IN"),
                "aircraft_model": aircraft.get("model") or "",
                "aircraft_reg": aircraft.get("reg") or "",
                "other_iata": other_ap.get("iata") or "",
                "other_icao": other_ap.get("icao") or "",
                "other_name": other_ap.get("name") or "",
                "other_city": other_ap.get("municipalityName") or other_ap.get("shortName") or "",
                "other_country": country,
                "sched_local": sched,
                "revised_local": revised,
                "actual_local": actual,
                "source": "AeroDataBox",
            })
    return rows


def windows_for_day(d: date) -> list[tuple[str, str]]:
    s = datetime(d.year, d.month, d.day)
    fmt = "%Y-%m-%dT%H:%M"
    return [
        (s.strftime(fmt), (s + timedelta(hours=11, minutes=59)).strftime(fmt)),
        ((s + timedelta(hours=12)).strftime(fmt), (s + timedelta(hours=23, minutes=59)).strftime(fmt)),
    ]


def fetch_day(d: date, key: str | None = None, session: requests.Session | None = None) -> list[dict]:
    key = key or os.environ.get("AERODATABOX_KEY")
    if not key:
        print("AERODATABOX_KEY not set - skipping AeroDataBox collection.")
        return []
    s = session or requests.Session()
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": HOST, "User-Agent": config.USER_AGENT}
    params = {
        "withLeg": "true", "direction": "Both", "withCancelled": "true",
        "withCodeshared": "false", "withCargo": "true", "withPrivate": "false",
    }
    rows: list[dict] = []
    for frm, to in windows_for_day(d):
        url = f"{BASE}/flights/airports/icao/{config.AIRPORT_ICAO}/{frm}/{to}"
        r = s.get(url, headers=headers, params=params, timeout=40)
        if r.status_code == 204:
            continue
        if r.status_code != 200:
            print(f"AeroDataBox {r.status_code} for {frm}..{to}: {r.text[:200]}")
            r.raise_for_status()
        rows.extend(parse_fids(r.json()))
    # keep only movements whose local date is the requested day
    return [r for r in rows if r["date"] == d.isoformat()]


def fetch_days(days: Iterable[date], key: str | None = None) -> list[dict]:
    out: list[dict] = []
    with requests.Session() as s:
        for d in days:
            out.extend(fetch_day(d, key, s))
    return out

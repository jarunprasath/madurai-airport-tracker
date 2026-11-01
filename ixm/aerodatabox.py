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
from .reference import fill_airport, looks_cargo

HOST = os.environ.get("AERODATABOX_HOST", "aerodatabox.p.rapidapi.com")
# The API refuses dates earlier than this many days ago ("must not be earlier than 365 day(s) ago").
HISTORY_DAYS = int(os.environ.get("AERODATABOX_HISTORY_DAYS", "365"))
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
            fill_airport(rows[-1])
    return rows


def windows_for_day(d: date) -> list[tuple[str, str]]:
    s = datetime(d.year, d.month, d.day)
    fmt = "%Y-%m-%dT%H:%M"
    return [
        (s.strftime(fmt), (s + timedelta(hours=11, minutes=59)).strftime(fmt)),
        ((s + timedelta(hours=12)).strftime(fmt), (s + timedelta(hours=23, minutes=59)).strftime(fmt)),
    ]


class QuotaExceeded(RuntimeError):
    """The API refused because the plan's request quota / rate limit is used up (HTTP 429)."""


class AuthError(RuntimeError):
    """The key is wrong or the subscription is not active (HTTP 401/403)."""


def fetch_day(d: date, key: str | None = None, session: requests.Session | None = None, meter=None) -> list[dict]:
    """Fetch one local day. Raises QuotaExceeded / AuthError (stop the run) or ValueError
    (this day is unavailable, e.g. too far in the past - skip it and continue)."""
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
        try:
            r = s.get(url, headers=headers, params=params, timeout=40)
        except requests.RequestException as e:
            raise ValueError(f"network error: {type(e).__name__}") from e
        if r.status_code == 429:
            if meter:
                meter.hook(exhausted=True)
            raise QuotaExceeded(r.text[:200])
        if r.status_code in (401, 403):
            raise AuthError(f"HTTP {r.status_code}: {r.text[:200]}")
        if meter:
            if r.status_code in (200, 204):
                meter.hook(r)
            else:
                meter.count_call()      # assume refused requests may still be billed (conservative)
        if r.status_code == 204:
            continue
        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}: {r.text[:160]}")
        rows.extend(parse_fids(r.json()))
    # keep only movements whose local date is the requested day
    return [r for r in rows if r["date"] == d.isoformat()]


def fetch_days(days: Iterable[date], key: str | None = None, on_day=None, meter=None) -> dict:
    """Fetch day by day. `on_day(day, rows)` is called after each successful day (used to save
    progress). Days that fail are skipped; quota or auth errors stop the run cleanly."""
    result = {"rows": [], "ok": 0, "failed": [], "stopped": ""}
    with requests.Session() as s:
        for d in days:
            try:
                day_rows = fetch_day(d, key, s, meter)
            except QuotaExceeded as e:
                result["stopped"] = f"API quota/rate limit reached at {d} - run again later to continue ({e})"
                break
            except AuthError as e:
                result["stopped"] = f"API key or subscription problem: {e}"
                break
            except ValueError as e:
                result["failed"].append((d.isoformat(), str(e)))
                continue
            result["ok"] += 1
            result["rows"].extend(day_rows)
            if on_day:
                on_day(d, day_rows)
    return result

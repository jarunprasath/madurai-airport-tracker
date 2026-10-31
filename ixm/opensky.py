"""OpenSky Network live-aircraft snapshot around Madurai.

Uses the public REST endpoint GET https://opensky-network.org/api/states/all with a
bounding box. Anonymous access works with tight rate limits. If OPENSKY_CLIENT_ID and
OPENSKY_CLIENT_SECRET are set, an OAuth2 client-credentials token is requested first
(OpenSky's newer auth scheme - verify the token URL in OpenSky's current API docs).

ADS-B coverage near Madurai depends on volunteer receivers and may be sparse; an empty
result does not mean no aircraft are flying.
"""
from __future__ import annotations

import math
import os
import time
from typing import Any

import requests

from . import config
from .reference import airline_from_callsign

API = "https://opensky-network.org/api/states/all"
TOKEN_URL = os.environ.get(
    "OPENSKY_TOKEN_URL",
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
)

STATE_FIELDS = [
    "icao24", "callsign", "origin_country", "time_position", "last_contact", "longitude",
    "latitude", "baro_altitude", "on_ground", "velocity", "true_track", "vertical_rate",
    "sensors", "geo_altitude", "squawk", "spi", "position_source",
]


def _token() -> str | None:
    cid, secret = os.environ.get("OPENSKY_CLIENT_ID"), os.environ.get("OPENSKY_CLIENT_SECRET")
    if not (cid and secret):
        return None
    r = requests.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": cid,
                                       "client_secret": secret}, timeout=30)
    if r.status_code != 200:
        print(f"OpenSky token request failed ({r.status_code}); falling back to anonymous.")
        return None
    return r.json().get("access_token")


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_states(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in payload.get("states") or []:
        rec = dict(zip(STATE_FIELDS, s))
        if rec.get("latitude") is None or rec.get("longitude") is None:
            continue
        cs = (rec.get("callsign") or "").strip()
        alt = rec.get("baro_altitude") if rec.get("baro_altitude") is not None else rec.get("geo_altitude")
        vr = rec.get("vertical_rate") or 0
        dist = distance_km(config.AIRPORT_LAT, config.AIRPORT_LON, rec["latitude"], rec["longitude"])
        if rec.get("on_ground"):
            phase = "on ground"
        elif alt is not None and alt < 3000 and vr < -1:
            phase = "approaching"
        elif alt is not None and alt < 3000 and vr > 1:
            phase = "departing"
        else:
            phase = "overflying"
        out.append({
            "icao24": rec["icao24"], "callsign": cs, "airline": airline_from_callsign(cs),
            "lat": round(rec["latitude"], 4), "lon": round(rec["longitude"], 4),
            "alt_m": None if alt is None else round(alt), "speed_kmh": None if rec.get("velocity") is None
            else round(rec["velocity"] * 3.6), "track": rec.get("true_track"),
            "vrate": vr, "on_ground": bool(rec.get("on_ground")), "country": rec.get("origin_country"),
            "distance_km": round(dist, 1), "phase": phase,
        })
    out.sort(key=lambda x: x["distance_km"])
    return out


def snapshot() -> dict[str, Any]:
    headers = {"User-Agent": config.USER_AGENT}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        r = requests.get(API, params=config.LIVE_BBOX, headers=headers, timeout=30)
        r.raise_for_status()
        aircraft = parse_states(r.json())
        status = "ok"
    except Exception as e:  # network or rate limit - keep the dashboard working
        print(f"OpenSky snapshot failed: {e}")
        aircraft, status = [], f"error: {type(e).__name__}"
    return {"generated_utc": int(time.time()), "status": status, "source": "OpenSky Network",
            "bbox": config.LIVE_BBOX, "aircraft": aircraft}

"""Static configuration for the Madurai (IXM / VOMD) airport tracker."""
from __future__ import annotations

import os
from pathlib import Path

AIRPORT_IATA = "IXM"
AIRPORT_ICAO = "VOMD"
AIRPORT_NAME = "Madurai International Airport"
# Coordinates as given for the aerodrome reference point (verify against AAI AIP if precision matters)
AIRPORT_LAT = 9.8336
AIRPORT_LON = 78.0894
LOCAL_TZ = "Asia/Kolkata"

# Bounding box for "live" aircraft near Madurai (~60 km around the airport)
LIVE_BBOX = {"lamin": 9.30, "lamax": 10.40, "lomin": 77.50, "lomax": 78.70}

ROOT = Path(os.environ.get("IXM_ROOT", Path(__file__).resolve().parent.parent))
DATA_DIR = ROOT / "data"
FLIGHTS_DIR = DATA_DIR / "flights"
SITE_DIR = ROOT / "site"
SITE_DATA_DIR = SITE_DIR / "data"

AAI_MONTHLY_CSV = DATA_DIR / "aai_monthly.csv"          # auto-collected from AAI Traffic News PDFs
AAI_MANUAL_CSV = DATA_DIR / "aai_monthly_manual.csv"    # hand-entered corrections; win over auto rows
AAI_ANNUAL_CSV = DATA_DIR / "aai_annual.csv"            # fiscal-year totals (seed)
AAI_LOG_CSV = DATA_DIR / "aai_fetch_log.csv"

# Default load factor for estimating passengers from seats when no AAI figure exists yet.
DEFAULT_LOAD_FACTOR = float(os.environ.get("IXM_LOAD_FACTOR", "0.85"))

USER_AGENT = "madurai-airport-tracker/1.0 (+https://github.com/jarunprasath/madurai-airport-tracker)"

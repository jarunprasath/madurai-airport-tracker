"""Reference tables: airline call-sign prefixes and typical seat counts.

Seat counts are TYPICAL single-class configurations used only to ESTIMATE passengers
when no official figure exists. Real configurations vary by airline and tail number.
Edit these tables if you know the exact configuration an airline flies into Madurai.
"""
from __future__ import annotations

import re

# ICAO airline designator -> display name (used to label OpenSky call signs)
AIRLINE_ICAO = {
    "IGO": "IndiGo",
    "SEJ": "SpiceJet",
    "AIC": "Air India",
    "AXB": "Air India Express",
    "IAD": "AirAsia India",
    "ALK": "SriLankan Airlines",
    "FDB": "flydubai",
    "AKJ": "Akasa Air",
    "VTI": "Vistara",
    "BDA": "Blue Dart",
    "QJT": "Quikjet",
    "AXM": "AirAsia",
    "MAS": "Malaysia Airlines",
    "SIA": "Singapore Airlines",
    "TGW": "Scoot",
    "UAE": "Emirates",
    "IAF": "Indian Air Force",
    "ALW": "Alliance Air",
}

CARGO_AIRLINE_HINTS = ("blue dart", "quikjet", "cargo", "freight", "express logistics", "fedex", "dhl", "ups")

# (regex on aircraft model text, typical seats)
_SEAT_RULES: list[tuple[str, int]] = [
    (r"a321", 222),
    (r"a320", 186),
    (r"a319", 144),
    (r"737\s*max|b38m|7m8", 189),
    (r"737-800|738|b738", 189),
    (r"737-700|73g", 149),
    (r"737", 180),
    (r"atr\s*72|at7|at76", 78),
    (r"atr\s*42|at4", 48),
    (r"dash\s*8|dhc-8|q400|dh8d", 78),
    (r"a330|a33", 290),
    (r"787|b78", 250),
    (r"e175|erj.?175|e75", 76),
    (r"e190|erj.?190|e90", 100),
]
DEFAULT_SEATS = 180


def seats_for(model: str | None) -> int | None:
    """Typical seat count for an aircraft model string; None if unknown/blank."""
    if not model:
        return None
    m = model.lower()
    for pattern, seats in _SEAT_RULES:
        if re.search(pattern, m):
            return seats
    return None


def airline_from_callsign(callsign: str | None) -> str:
    if not callsign:
        return "Unknown"
    prefix = callsign.strip()[:3].upper()
    return AIRLINE_ICAO.get(prefix, prefix if prefix.isalpha() else "Unknown")


def looks_cargo(airline: str | None, flag: bool | None = None) -> bool:
    if flag:
        return True
    a = (airline or "").lower()
    return any(h in a for h in CARGO_AIRLINE_HINTS)


# Fallback when a flight record names the other airport but omits its code/country.
# name/city keyword (lower case) -> (IATA, ISO country code)
KNOWN_AIRPORTS = {
    "dubai": ("DXB", "AE"), "abu dhabi": ("AUH", "AE"), "sharjah": ("SHJ", "AE"), "ras al khaimah": ("RKT", "AE"),
    "colombo": ("CMB", "LK"), "jaffna": ("JAF", "LK"), "singapore": ("SIN", "SG"), "kuala lumpur": ("KUL", "MY"),
    "muscat": ("MCT", "OM"), "doha": ("DOH", "QA"), "kuwait": ("KWI", "KW"), "bahrain": ("BAH", "BH"),
    "riyadh": ("RUH", "SA"), "jeddah": ("JED", "SA"), "dammam": ("DMM", "SA"), "bangkok": ("BKK", "TH"),
    "male": ("MLE", "MV"),
    "chennai": ("MAA", "IN"), "bengaluru": ("BLR", "IN"), "bangalore": ("BLR", "IN"), "mumbai": ("BOM", "IN"),
    "delhi": ("DEL", "IN"), "hyderabad": ("HYD", "IN"), "kolkata": ("CCU", "IN"), "pune": ("PNQ", "IN"),
    "ahmedabad": ("AMD", "IN"), "goa": ("GOI", "IN"), "kochi": ("COK", "IN"), "cochin": ("COK", "IN"),
    "thiruvananthapuram": ("TRV", "IN"), "trivandrum": ("TRV", "IN"), "tirupati": ("TIR", "IN"),
}


def fill_airport(row: dict) -> dict:
    """Fill missing other_iata / other_country / is_international from the airport name or city."""
    if row.get("other_country") and row.get("other_iata"):
        return row
    text = f"{row.get('other_name', '')} {row.get('other_city', '')}".lower()
    for key, (iata, cc) in KNOWN_AIRPORTS.items():
        if key in text:
            row["other_iata"] = row.get("other_iata") or iata
            if not row.get("other_country"):
                row["other_country"] = cc
                row["is_international"] = cc != "IN"
            if not row.get("other_city"):
                row["other_city"] = key.title()
            break
    return row

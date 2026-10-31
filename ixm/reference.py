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

"""Monthly AeroDataBox budget: keep enough units for the daily collection, spend only the spare on back-filling.

State lives in data/api_usage.json (committed with the data), so every GitHub Actions run knows what earlier
runs spent in the current quota cycle.

Settings (environment variables / GitHub repository variables; blank = default):
  AERODATABOX_MONTHLY_UNITS   units in the plan per month           (default 400, the free BASIC plan)
  AERODATABOX_UNITS_PER_CALL  units one airport-FIDS call costs       (default 2 - an estimate, verify in the docs)
  AERODATABOX_RESET_DAY       day of month the quota resets (1-28)    (default: learned automatically - see below)
  AERODATABOX_SAFETY_UNITS    extra units never spent on back-filling (default 10)

Learning the reset day: when a call succeeds after the quota had run out, a new cycle has evidently begun,
so the cycle start is set to that day. If RapidAPI sends x-ratelimit-*-remaining headers they are recorded
and, when one of them counts units, it is trusted over the local count. (Header names are not documented
here with certainty - they are stored as received for inspection.)
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

from . import config

PATH = config.DATA_DIR / "api_usage.json"


def _env_int(name: str, default: int | None) -> int | None:
    v = (os.environ.get(name) or "").strip()
    try:
        return int(v) if v else default
    except ValueError:
        return default


def settings() -> dict:
    return {"monthly": _env_int("AERODATABOX_MONTHLY_UNITS", 400),
            "per_call": _env_int("AERODATABOX_UNITS_PER_CALL", 2),
            "reset_day": _env_int("AERODATABOX_RESET_DAY", None),
            "safety": _env_int("AERODATABOX_SAFETY_UNITS", 10)}


def _add_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, 28))


def load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(u: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(u, indent=1, sort_keys=True), encoding="utf-8")


def current(today: date, u: dict | None = None) -> dict:
    """Usage record for the cycle containing `today` (rolled over when a new cycle has started)."""
    s = settings()
    u = dict(u if u is not None else load())
    if s["reset_day"]:
        rd = max(1, min(28, s["reset_day"]))
        start = date(today.year, today.month, rd) if today.day >= rd else _prev_cycle(today, rd)
    else:
        start = date.fromisoformat(u["cycle_start"]) if u.get("cycle_start") else date(today.year, today.month, 1)
        while _add_month(start) <= today:
            start = _add_month(start)
    if u.get("cycle_start") != start.isoformat():
        u = {"cycle_start": start.isoformat(), "calls": 0, "exhausted": False,
             "headers": {}, "history": (u.get("history") or [])[-11:] + ([{k: u.get(k) for k in ("cycle_start", "calls", "exhausted")}] if u.get("cycle_start") else [])}
    u["cycle_end"] = (_add_month(start) - timedelta(days=1)).isoformat()
    return u


def _prev_cycle(today: date, rd: int) -> date:
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return date(y, m, rd)


def remaining_units(u: dict) -> int:
    s = settings()
    for k, v in (u.get("headers") or {}).items():
        if "remaining" in k and "unit" in k:
            try:
                return int(v)
            except ValueError:
                pass
    if u.get("exhausted"):
        return 0
    return s["monthly"] - u.get("calls", 0) * s["per_call"]


def plan(today: date, daily_calls: int, u: dict | None = None, include_today: bool = True) -> dict:
    """How many units the rest of this cycle's daily runs need, and how many back-fill days are affordable.
    include_today=False when today's daily fetch has already been made in this run."""
    s = settings()
    u = current(today, u)
    end = date.fromisoformat(u["cycle_end"])
    days_left = (end - today).days + (1 if include_today else 0)
    reserve = days_left * daily_calls * s["per_call"]
    rem = remaining_units(u)
    spare = rem - reserve - s["safety"]
    per_day = 2 * s["per_call"]
    return {"cycle_start": u["cycle_start"], "cycle_end": u["cycle_end"], "remaining_units": rem,
            "reserve_units": reserve, "spare_units": max(0, spare), "backfill_days": max(0, spare // per_day),
            "units_per_call": s["per_call"], "monthly_units": s["monthly"]}


class Meter:
    """Counts calls during a run and records quota state; pass `meter.hook` to aerodatabox.fetch_days."""

    def __init__(self, today: date):
        self.today = today
        self.u = current(today)

    def hook(self, response=None, exhausted: bool = False) -> None:
        if exhausted:
            self.u["exhausted"] = True
            self.u["exhausted_on"] = self.today.isoformat()
            return
        if response is None:
            return
        if self.u.get("exhausted"):
            # a call succeeded after the quota had run out: a new cycle has started today
            self.u = {"cycle_start": self.today.isoformat(), "calls": 0, "exhausted": False, "headers": {},
                      "history": (self.u.get("history") or [])[-11:] + [{k: self.u.get(k) for k in ("cycle_start", "calls", "exhausted")}],
                      "learned_reset_day": self.today.day}
            self.u["cycle_end"] = (_add_month(self.today) - timedelta(days=1)).isoformat()
        self.u["calls"] = self.u.get("calls", 0) + 1
        hdr = {k.lower(): v for k, v in getattr(response, "headers", {}).items() if k.lower().startswith("x-ratelimit")}
        if hdr:
            self.u["headers"] = hdr

    def count_call(self) -> None:
        """A request that reached the API but did not return a usable response (still costs units)."""
        self.u["calls"] = self.u.get("calls", 0) + 1

    def save(self) -> None:
        save(self.u)

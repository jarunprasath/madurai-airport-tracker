from datetime import date

import pytest

from ixm import quota


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    for k in ("AERODATABOX_MONTHLY_UNITS", "AERODATABOX_UNITS_PER_CALL", "AERODATABOX_RESET_DAY", "AERODATABOX_SAFETY_UNITS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(quota, "PATH", tmp_path / "api_usage.json")


class R:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_reserve_keeps_units_for_daily_runs():
    # 1 Nov, nothing spent: 30 days x 4 calls x 2 units = 240 reserved, 10 safety -> 150 spare -> 37 days
    p = quota.plan(date(2026, 11, 1), 4, {})
    assert p["cycle_end"] == "2026-11-30"
    assert p["reserve_units"] == 240 and p["remaining_units"] == 400
    assert p["backfill_days"] == 37
    # after today's run, today's reserve is no longer needed
    assert quota.plan(date(2026, 11, 1), 4, {}, include_today=False)["reserve_units"] == 232


def test_meter_counts_and_exhaustion_blocks_backfill():
    m = quota.Meter(date(2026, 11, 5))
    for _ in range(10):
        m.hook(R())
    assert m.u["calls"] == 10
    assert quota.remaining_units(m.u) == 380
    m.hook(exhausted=True)
    assert quota.plan(date(2026, 11, 5), 4, m.u)["backfill_days"] == 0


def test_success_after_exhaustion_starts_new_cycle_on_that_day():
    m = quota.Meter(date(2026, 11, 5))
    m.hook(exhausted=True)
    m.save()
    m2 = quota.Meter(date(2026, 11, 6))
    assert m2.u["exhausted"]
    m2.hook(R())
    assert m2.u["cycle_start"] == "2026-11-06" and m2.u["calls"] == 1 and not m2.u["exhausted"]
    assert m2.u["cycle_end"] == "2026-12-05"
    m2.save()
    # the learned cycle carries on in later runs, and rolls over a month later
    assert quota.current(date(2026, 11, 20))["cycle_start"] == "2026-11-06"
    assert quota.current(date(2026, 12, 6))["calls"] == 0


def test_configured_reset_day(monkeypatch):
    monkeypatch.setenv("AERODATABOX_RESET_DAY", "17")
    assert quota.current(date(2026, 11, 3), {})["cycle_start"] == "2026-10-17"
    assert quota.current(date(2026, 11, 17), {})["cycle_start"] == "2026-11-17"
    assert quota.current(date(2027, 1, 2), {})["cycle_start"] == "2026-12-17"


def test_units_header_is_trusted():
    u = {"cycle_start": "2026-11-01", "calls": 5, "headers": {"x-ratelimit-units-remaining": "123"}}
    assert quota.remaining_units(u) == 123

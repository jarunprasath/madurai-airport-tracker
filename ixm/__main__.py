"""Command line: python -m ixm <command>

  live                       snapshot aircraft near Madurai (OpenSky) -> site/data/live.json
  flights [--back N --ahead N]  collect arrivals/departures (AeroDataBox) for recent/upcoming days
  aai [--start YYYY-MM --end YYYY-MM --refetch]  collect AAI monthly passengers/movements/freight
  build                      rebuild dashboard JSON (site/data)
  report --kind weekly|monthly [--date YYYY-MM-DD] [--no-pptx] [--out DIR]
                             generate PowerPoint + Excel report (default: last complete period)
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config


def _today() -> date:
    return datetime.now(ZoneInfo(config.LOCAL_TZ)).date()


def _ym(s: str) -> date:
    y, m = map(int, s.split("-")[:2])
    return date(y, m, 1)


def _flights(args, today: date) -> None:
    from . import aerodatabox, quota, store
    has_key = bool(os.environ.get("AERODATABOX_KEY"))
    meter = quota.Meter(today) if has_key else None
    oldest = today - timedelta(days=aerodatabox.HISTORY_DAYS - 1)
    have = {r["date"] for r in store.load_all()}
    empty = set(meter.u.get("empty_days", [])) if meter else set()
    saved = {"n": 0}
    stopped = ""

    def save(day, rows):
        saved["n"] += store.upsert(rows)
        if not rows and meter:
            meter.u.setdefault("empty_days", []).append(day.isoformat())
        print(f"  {day}: {len(rows)} movements", flush=True)

    def run(days, label):
        nonlocal stopped
        if not days:
            return
        res = aerodatabox.fetch_days(days, on_day=save, meter=meter)
        for d, why in res["failed"]:
            print(f"  {d}: skipped - {why}", flush=True)
        print(f"{label}: {res['ok']} of {len(days)} days fetched, {len(res['rows'])} movements", flush=True)
        if res["stopped"]:
            stopped = res["stopped"]
            print(f"STOPPED: {stopped}")

    daily_calls = 2 * (args.back + args.ahead + 1)
    if args.date_from:
        d0 = date.fromisoformat(args.date_from)
        d1 = date.fromisoformat(args.date_to) if args.date_to else d0
        days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
        too_old = [d for d in days if d < oldest]
        if too_old:
            print(f"flights: skipping {len(too_old)} days before {oldest} - AeroDataBox keeps only "
                  f"{aerodatabox.HISTORY_DAYS} days of history (no API calls spent on them)")
        days = [d for d in days if d >= oldest and (d.isoformat() not in have or d >= today - timedelta(days=1))]
        cap = args.max_days
        if meter and not args.ignore_budget:
            pl = quota.plan(today, 4, meter.u)
            print(f"budget: {pl['remaining_units']} units left this cycle (to {pl['cycle_end']}), "
                  f"{pl['reserve_units']} kept for daily runs -> room for {pl['backfill_days']} back-fill days")
            cap = min(cap, pl["backfill_days"])
        if len(days) > cap:
            print(f"flights: {len(days)} days requested; fetching {cap} now (quota protection), the rest later")
            days = days[:cap]
        run(days, "range")
    else:
        days = [today + timedelta(days=i) for i in range(-args.back, args.ahead + 1)]
        if args.back > 1:       # manual catch-up run: skip collected/too-old days, newest first, within budget
            days = [d for d in days if d >= oldest and (d.isoformat() not in have or d >= today - timedelta(days=1))]
            cap = args.max_days
            if meter and not args.ignore_budget:
                cap = min(cap, quota.plan(today, 4, meter.u)["backfill_days"] + args.ahead + 2)
            if len(days) > cap:
                print(f"flights: {len(days)} days requested; limited to {cap} days (~{2 * cap} API calls) "
                      f"to protect your quota. Next run continues from {days[-cap] - timedelta(days=1)}.")
                days = days[-cap:]
        run(days, "daily")
        if args.backfill and meter and not stopped:
            pl = quota.plan(today, daily_calls, meter.u, include_today=False)
            print(f"budget: {pl['remaining_units']} units left this cycle (to {pl['cycle_end']}), "
                  f"{pl['reserve_units']} kept for the remaining daily runs -> room for {pl['backfill_days']} back-fill days")
            missing = [oldest + timedelta(days=i) for i in range((today - timedelta(days=args.back) - oldest).days)]
            missing = [d for d in missing if d.isoformat() not in have and d.isoformat() not in empty]
            print(f"backfill: {len(missing)} missing days within the {aerodatabox.HISTORY_DAYS}-day window"
                  + (f", oldest {missing[0]}" if missing else ""))
            run(missing[:min(pl["backfill_days"], args.max_days)], "backfill")
    if meter:
        meter.save()
        pl = quota.plan(today, daily_calls, meter.u, include_today=False)
        print(f"usage: {meter.u.get('calls', 0)} calls this cycle (since {meter.u['cycle_start']}), "
              f"about {pl['remaining_units']} units left")
    if has_key:
        status = {"checked_utc": datetime.utcnow().isoformat(timespec="seconds"),
                  "state": "paused" if stopped else "ok",
                  "message": ("Flight collection paused: " + stopped.split(" (")[0]) if stopped else ""}
        (config.DATA_DIR / "flights_status.json").write_text(json.dumps(status, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m ixm", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("live")
    f = sub.add_parser("flights")
    f.add_argument("--back", type=int, default=1, help="days before today (default 1 = yesterday)")
    f.add_argument("--ahead", type=int, default=0, help="days after today (default 0)")
    f.add_argument("--from", dest="date_from", help="first date YYYY-MM-DD for a historical backfill")
    f.add_argument("--to", dest="date_to", help="last date YYYY-MM-DD (default: same as --from)")
    f.add_argument("--max-days", type=int, default=31, help="safety cap on days per run (API quota), applies to every mode")
    f.add_argument("--backfill", action="store_true",
                   help="after the normal fetch, fill missing past days (oldest first) using only the spare monthly budget")
    f.add_argument("--ignore-budget", action="store_true", help="do not limit a --from/--to run to the spare budget")
    sub.add_parser("quota", help="show this month's AeroDataBox budget")
    a = sub.add_parser("aai")
    a.add_argument("--start", help="YYYY-MM (default: 4 months ago)")
    a.add_argument("--end", help="YYYY-MM (default: last month)")
    a.add_argument("--refetch", action="store_true")
    a.add_argument("--max-months", type=int, help="stop after this many new months (resume next run)")
    a.add_argument("--budget-min", type=float, default=40, help="stop after this many minutes (default 40)")
    sub.add_parser("build")
    dz = sub.add_parser("decade", help="10-year strategic review (PPT + Excel)")
    dz.add_argument("--out", type=Path)
    r = sub.add_parser("report")
    r.add_argument("--kind", choices=["weekly", "monthly", "yearly"], required=True)
    r.add_argument("--date", help="any date inside the wanted week/month (default: last complete one)")
    r.add_argument("--no-pptx", action="store_true")
    r.add_argument("--out", type=Path)
    args = p.parse_args(argv)

    today = _today()
    if args.cmd == "live":
        from .opensky import snapshot
        snap = snapshot()
        config.SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        (config.SITE_DATA_DIR / "live.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
        print(f"live: {snap['status']}, {len(snap['aircraft'])} aircraft")
    elif args.cmd == "quota":
        from . import quota
        print(json.dumps(quota.plan(today, 4), indent=1))
    elif args.cmd == "flights":
        _flights(args, today)
    elif args.cmd == "aai":
        from . import aai
        last = date(today.year, today.month, 1) - timedelta(days=1)
        end = _ym(args.end) if args.end else date(last.year, last.month, 1)
        m0 = end.year * 12 + end.month - 1 - 3      # AAI sometimes revises recent months
        start = _ym(args.start) if args.start else date(m0 // 12, m0 % 12 + 1, 1)
        print("aai:", aai.collect(start, end, refetch=args.refetch, max_months=args.max_months,
                                  time_budget_s=args.budget_min * 60))
    elif args.cmd == "build":
        from .build import build
        s = build(today)
        print(f"build: {s['coverage']}")
    elif args.cmd == "decade":
        from .decade import generate as decade_generate
        for kind, path in decade_generate(args.out).items():
            print(f"decade {kind}: {path}")
    elif args.cmd == "report":
        from .report import generate
        if args.date:
            ref = date.fromisoformat(args.date)
        elif args.kind == "weekly":
            ref = today - timedelta(days=today.weekday() + 7)        # last complete Mon-Sun week
        elif args.kind == "yearly":
            ref = date(today.year - 1 if today.month >= 4 else today.year - 2, 4, 1)   # last complete FY
        else:
            ref = date(today.year, today.month, 1) - timedelta(days=1)  # last complete month
        for kind, path in generate(args.kind, ref, args.out, pptx=not args.no_pptx).items():
            print(f"report {kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

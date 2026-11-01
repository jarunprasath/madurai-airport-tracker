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
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config


def _today() -> date:
    return datetime.now(ZoneInfo(config.LOCAL_TZ)).date()


def _ym(s: str) -> date:
    y, m = map(int, s.split("-")[:2])
    return date(y, m, 1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m ixm", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("live")
    f = sub.add_parser("flights")
    f.add_argument("--back", type=int, default=1, help="days before today (default 1 = yesterday)")
    f.add_argument("--ahead", type=int, default=1, help="days after today (default 1 = tomorrow)")
    f.add_argument("--from", dest="date_from", help="first date YYYY-MM-DD for a historical backfill")
    f.add_argument("--to", dest="date_to", help="last date YYYY-MM-DD (default: same as --from)")
    f.add_argument("--max-days", type=int, default=31, help="safety cap on days per run (API quota)")
    a = sub.add_parser("aai")
    a.add_argument("--start", help="YYYY-MM (default: 4 months ago)")
    a.add_argument("--end", help="YYYY-MM (default: last month)")
    a.add_argument("--refetch", action="store_true")
    a.add_argument("--max-months", type=int, help="stop after this many new months (resume next run)")
    a.add_argument("--budget-min", type=float, default=40, help="stop after this many minutes (default 40)")
    sub.add_parser("build")
    r = sub.add_parser("report")
    r.add_argument("--kind", choices=["weekly", "monthly"], required=True)
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
    elif args.cmd == "flights":
        from . import aerodatabox, store
        if args.date_from:
            d0 = date.fromisoformat(args.date_from)
            d1 = date.fromisoformat(args.date_to) if args.date_to else d0
            days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
            if len(days) > args.max_days:
                print(f"flights: {len(days)} days requested; capped to the first {args.max_days} "
                      f"(about {2 * args.max_days} API calls). Run again from {days[args.max_days]} to continue.")
                days = days[:args.max_days]
        else:
            days = [today + timedelta(days=i) for i in range(-args.back, args.ahead + 1)]
        rows = aerodatabox.fetch_days(days)
        per_day = {}
        for r in rows:
            per_day[r["date"]] = per_day.get(r["date"], 0) + 1
        for d in days:
            print(f"  {d}: {per_day.get(d.isoformat(), 0)} movements")
        print(f"flights: fetched {len(rows)} movements over {len(days)} days "
              f"(~{2 * len(days)} API calls), {store.upsert(rows)} new/updated")
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
    elif args.cmd == "report":
        from .report import generate
        if args.date:
            ref = date.fromisoformat(args.date)
        elif args.kind == "weekly":
            ref = today - timedelta(days=today.weekday() + 7)        # last complete Mon-Sun week
        else:
            ref = date(today.year, today.month, 1) - timedelta(days=1)  # last complete month
        for kind, path in generate(args.kind, ref, args.out, pptx=not args.no_pptx).items():
            print(f"report {kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

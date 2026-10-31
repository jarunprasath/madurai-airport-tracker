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
    a = sub.add_parser("aai")
    a.add_argument("--start", help="YYYY-MM (default: 4 months ago)")
    a.add_argument("--end", help="YYYY-MM (default: last month)")
    a.add_argument("--refetch", action="store_true")
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
        days = [today + timedelta(days=i) for i in range(-args.back, args.ahead + 1)]
        rows = aerodatabox.fetch_days(days)
        print(f"flights: fetched {len(rows)} movements, {store.upsert(rows)} new/updated")
    elif args.cmd == "aai":
        from . import aai
        last = date(today.year, today.month, 1) - timedelta(days=1)
        end = _ym(args.end) if args.end else date(last.year, last.month, 1)
        m0 = end.year * 12 + end.month - 1 - 3      # AAI sometimes revises recent months
        start = _ym(args.start) if args.start else date(m0 // 12, m0 % 12 + 1, 1)
        print("aai:", aai.collect(start, end, refetch=args.refetch))
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

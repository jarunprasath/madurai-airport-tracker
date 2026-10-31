"""Passenger forecasting for Madurai.

Two horizons, both transparent and dependency-free:

1. Monthly (next 12 months) from AAI monthly passengers:
   seasonal index (ratio to centred 12-month moving average, COVID months excluded)
   x linear trend fitted on the last 36 deseasonalised months.
   80% band = +/-1.28 x std-dev of one-step-ahead backtest errors over the last 12 months.
   Festival/holiday peaks are captured by the seasonal index learned from history,
   not hand-coded multipliers.

2. Next 7 days from the published schedule:
   scheduled passenger flights x typical seats x calibrated load factor.

These are statistical estimates, not official figures.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, pstdev

COVID_START, COVID_END = "2020-03", "2022-03"   # excluded from model fitting

# Recurring travel peaks around Madurai, by MONTH only (exact dates vary each year -
# check the calendar for the year in question).
SEASON_TAGS = {
    1: ["Pongal (mid-Jan)", "Sabarimala season ends (mid-Jan)", "Winter holidays"],
    4: ["Chithirai festival (Apr/May, date varies)", "Summer holidays begin"],
    5: ["Summer holidays", "Chithirai festival (Apr/May, date varies)"],
    6: ["Schools reopen - return travel"],
    9: ["Navaratri (Sep/Oct, date varies)"],
    10: ["Navaratri / Ayudha Pooja (date varies)", "Deepavali (Oct/Nov, date varies)"],
    11: ["Deepavali (Oct/Nov, date varies)", "Sabarimala season begins (mid-Nov)", "Karthigai Deepam (Nov/Dec)"],
    12: ["Christmas / New Year", "Sabarimala season", "Gulf/SE-Asia diaspora holiday travel"],
}


def _add_months(ym: str, n: int) -> str:
    y, m = map(int, ym.split("-"))
    m0 = (y * 12 + m - 1) + n
    return f"{m0 // 12}-{m0 % 12 + 1:02d}"


def _series(monthly: dict[str, dict], field: str = "pax_total") -> list[tuple[str, float]]:
    out = []
    for m in sorted(monthly):
        try:
            v = float(monthly[m].get(field) or "")
        except ValueError:
            continue
        if v > 0:
            out.append((m, v))
    return out


def _contiguous_tail(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Longest run of consecutive months ending at the latest observation."""
    if not series:
        return []
    tail = [series[-1]]
    for m, v in reversed(series[:-1]):
        if _add_months(m, 1) == tail[0][0]:
            tail.insert(0, (m, v))
        else:
            break
    return tail


def seasonal_indices(series: list[tuple[str, float]]) -> dict[int, float]:
    vals = [v for _, v in series]
    months = [m for m, _ in series]
    ratios: dict[int, list[float]] = defaultdict(list)
    for i in range(6, len(vals) - 6):
        if COVID_START <= months[i] <= COVID_END:
            continue
        window = vals[i - 6:i + 7]
        cma = (sum(window[1:-1]) + 0.5 * (window[0] + window[-1])) / 12.0
        if cma > 0:
            ratios[int(months[i][5:])].append(vals[i] / cma)
    idx = {m: mean(r) for m, r in ratios.items() if r}
    if len(idx) < 12:
        for m in range(1, 13):
            idx.setdefault(m, 1.0)
    norm = mean(idx.values())
    return {m: v / norm for m, v in idx.items()}


def _linfit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def _fit_predict(series: list[tuple[str, float]], idx: dict[int, float], horizon: int) -> list[tuple[str, float]]:
    fit = [(i, m, v) for i, (m, v) in enumerate(series) if not (COVID_START <= m <= COVID_END)][-36:]
    xs = [i for i, _, _ in fit]
    ys = [v / idx[int(m[5:])] for _, m, v in fit]
    slope, icpt = _linfit(xs, ys)
    last_i, last_m = len(series) - 1, series[-1][0]
    out = []
    for h in range(1, horizon + 1):
        m = _add_months(last_m, h)
        out.append((m, max(0.0, (icpt + slope * (last_i + h)) * idx[int(m[5:])])))
    return out


def monthly_forecast(monthly: dict[str, dict], horizon: int = 12) -> dict:
    series = _series(monthly)
    tail = _contiguous_tail(series)
    if len(tail) < 24:
        return {"available": False,
                "reason": f"needs at least 24 consecutive months of AAI data (have {len(tail)})",
                "season_tags": SEASON_TAGS}
    idx = seasonal_indices(tail)
    # backtest: one-step-ahead over the last 12 observed months
    errors, pct_errors = [], []
    for k in range(len(tail) - 12, len(tail)):
        if k < 24:
            continue
        sub = tail[:k]
        pred = _fit_predict(sub, seasonal_indices(sub), 1)[0][1]
        actual = tail[k][1]
        errors.append(actual - pred)
        pct_errors.append(abs(actual - pred) / actual)
    sigma = pstdev(errors) if len(errors) >= 3 else 0.1 * mean(v for _, v in tail[-12:])
    preds = _fit_predict(tail, idx, horizon)
    points = [{"month": m, "forecast": round(v), "low": round(max(0, v - 1.28 * sigma)),
               "high": round(v + 1.28 * sigma), "season": SEASON_TAGS.get(int(m[5:]), []),
               "seasonal_index": round(idx[int(m[5:])], 3)} for m, v in preds]
    return {
        "available": True,
        "method": "seasonal index x linear trend (last 36 non-COVID months); 80% band from backtest",
        "trained_on": f"{tail[0][0]} to {tail[-1][0]}",
        "backtest_mape_pct": round(100 * mean(pct_errors), 1) if pct_errors else None,
        "seasonal_index": {str(m): round(v, 3) for m, v in sorted(idx.items())},
        "points": points,
        "season_tags": SEASON_TAGS,
    }


def fiscal_year(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    start = y if m >= 4 else y - 1
    return f"{start}-{(start + 1) % 100:02d}"

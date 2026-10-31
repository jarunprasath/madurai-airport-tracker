"""Airports Authority of India (AAI) monthly traffic collector for Madurai.

AAI publishes monthly "Traffic News" on https://www.aai.aero/en/business-opportunities/aai-traffic-news
with airport-wise annexures as PDFs, e.g.
  .../sites/default/files/traffic-news/Mar2k26Annex2.pdf   aircraft movements
  .../sites/default/files/traffic-news/Mar2k26Annex3.pdf   passengers
  .../sites/default/files/traffic-news/Mar2k26Annex4.pdf   freight (tonnes)
Each annexure has International / Domestic / Total sections, and each airport row carries:
  month (this year), month (last year), % change, year-to-date (this FY), YTD (last FY), % change.

File names are not perfectly consistent over the years (case, "_0" suffixes), so the
collector first scrapes the index page for links and then tries name variants.

Parsing PDFs is inherently fragile. Every parsed value passes sanity checks
(domestic + international ~= total, month <= YTD) and failures are logged to
data/aai_fetch_log.csv. Rows in data/aai_monthly_manual.csv always override.
"""
from __future__ import annotations

import csv
import io
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

import requests

from . import config

INDEX_URL = "https://www.aai.aero/en/business-opportunities/aai-traffic-news"
FILE_BASE = "https://www.aai.aero/sites/default/files/traffic-news/"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ANNEX_METRIC = {2: "mov", 3: "pax", 4: "frt"}
METRIC_ANNEX = {v: k for k, v in ANNEX_METRIC.items()}
AIRPORT_TOKEN = "MADURAI"

MONTHLY_FIELDS = ["month", "pax_dom", "pax_intl", "pax_total", "mov_dom", "mov_intl", "mov_total",
                  "frt_dom", "frt_intl", "frt_total", "source"]

_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?![\w])")
_FNAME = re.compile(r"([A-Za-z]{3})[A-Za-z]*\s*2\s*[kK]\s*(\d{1,2})\s*[_\-\s]*annex(?:ure)?[_\-\s]*(\d)",
                    re.IGNORECASE)


# ---------------------------------------------------------------- PDF -> rows
def pdf_rows(pdf_bytes: bytes, y_tol: float = 3.0) -> list[str]:
    """Extract visual rows (words sharing a baseline) from every page of a PDF."""
    import pdfplumber

    rows: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            words.sort(key=lambda w: (round(w["top"]), w["x0"]))
            current: list[dict] = []
            for w in words:
                if current and abs(w["top"] - current[0]["top"]) > y_tol:
                    rows.append(" ".join(x["text"] for x in sorted(current, key=lambda x: x["x0"])))
                    current = []
                current.append(w)
            if current:
                rows.append(" ".join(x["text"] for x in sorted(current, key=lambda x: x["x0"])))
    return rows


# ---------------------------------------------------------------- row parsing
@dataclass
class AirportFigures:
    month: float | None = None
    month_prev_year: float | None = None
    ytd: float | None = None
    ytd_prev_year: float | None = None
    raw: str = ""


@dataclass
class AnnexResult:
    sections: dict[str, AirportFigures] = field(default_factory=dict)  # international/domestic/total
    warnings: list[str] = field(default_factory=list)


def _section_of(row: str, last_letter: str | None) -> tuple[str | None, str | None]:
    """Detect a section heading; returns (section_kind, annex_letter)."""
    up = row.upper()
    m = re.search(r"ANNEXURE\s*[-–]?\s*(?:IV|III|II|I)\s*[-–]?\s*([ABC])\b", up)
    letter = m.group(1) if m else None
    if not m and "ANNEXURE" not in up:
        return None, last_letter
    kind = None
    if "INTERNATIONAL" in up:
        kind = "international"
    elif "DOMESTIC" in up:
        kind = "domestic"
    elif "TOTAL" in up or "GRAND" in up:
        kind = "total"
    if kind is None and letter:
        kind = {"A": "international", "B": "domestic", "C": "total"}[letter]
    return kind, letter or last_letter


def _numbers(row: str) -> tuple[list[float], list[float]]:
    ints, decs = [], []
    for tok in _NUM.findall(row):
        t = tok.replace(",", "")
        if "." in t:
            decs.append(float(t))
        else:
            ints.append(float(t))
    return ints, decs


def _figures_from(rows: list[str], i: int, is_freight: bool) -> AirportFigures | None:
    row = rows[i]
    candidates = [row]
    if i > 0:
        candidates.append(rows[i - 1] + " " + row)
    if i + 1 < len(rows):
        candidates.append(row + " " + rows[i + 1])
    for text in candidates:
        ints, _ = _numbers(text)
        if is_freight:
            # freight values are often decimals (tonnes); percent columns are the 3rd and 6th numbers
            nums = [float(t.replace(",", "")) for t in _NUM.findall(text)]
            if len(nums) >= 7 and nums[0] == int(nums[0]) and nums[0] < 400:
                nums = nums[1:]  # drop serial number
            if len(nums) >= 6:
                return AirportFigures(nums[0], nums[1], nums[3], nums[4], text)
            if len(nums) >= 4:
                return AirportFigures(nums[0], nums[1], nums[2], nums[3], text)
            continue
        if len(ints) >= 5 and ints[0] < 400 and ints[0] < ints[1]:
            ints = ints[1:]  # leading serial number
        if len(ints) >= 4:
            return AirportFigures(ints[0], ints[1], ints[2], ints[3], text)
    return None


def parse_annex_rows(rows: list[str], annex: int) -> AnnexResult:
    res = AnnexResult()
    section, letter = None, None
    order = ["international", "domestic", "total"]
    seen = 0
    for i, row in enumerate(rows):
        kind, letter = _section_of(row, letter)
        if kind:
            section = kind
        if AIRPORT_TOKEN in row.upper():
            figs = _figures_from(rows, i, is_freight=(annex == 4))
            if not figs:
                res.warnings.append(f"no numbers near: {row[:80]}")
                continue
            sec = section or (order[seen] if seen < 3 else None)
            seen += 1
            if sec and sec not in res.sections:
                res.sections[sec] = figs
    _validate(res)
    return res


def _validate(res: AnnexResult) -> None:
    s = res.sections
    for name, f in s.items():
        if f.month is not None and f.ytd is not None and f.month > f.ytd * 1.001 and f.ytd > 0:
            res.warnings.append(f"{name}: month {f.month} > YTD {f.ytd}")
    if {"international", "domestic", "total"} <= s.keys():
        i, d, t = s["international"].month, s["domestic"].month, s["total"].month
        if None not in (i, d, t) and t and abs((i + d) - t) > max(2.0, 0.01 * t):
            res.warnings.append(f"international {i} + domestic {d} != total {t}")
    elif {"international", "domestic"} <= s.keys() and "total" not in s:
        i, d = s["international"], s["domestic"]
        s["total"] = AirportFigures(
            (i.month or 0) + (d.month or 0), (i.month_prev_year or 0) + (d.month_prev_year or 0),
            (i.ytd or 0) + (d.ytd or 0), (i.ytd_prev_year or 0) + (d.ytd_prev_year or 0), "derived")
    elif {"total", "domestic"} <= s.keys() and "international" not in s:
        t, d = s["total"], s["domestic"]
        s["international"] = AirportFigures(
            (t.month or 0) - (d.month or 0), (t.month_prev_year or 0) - (d.month_prev_year or 0),
            (t.ytd or 0) - (d.ytd or 0), (t.ytd_prev_year or 0) - (d.ytd_prev_year or 0), "derived")


# ---------------------------------------------------------------- discovery & download
def candidate_names(year: int, month: int, annex: int) -> list[str]:
    mon = MONTHS[month - 1]
    yy = f"{year % 100:02d}" if year % 100 >= 10 else f"{year % 100}"
    yy_variants = {yy, f"{year % 100:02d}"}
    names = []
    for m in (mon, mon.lower(), mon.upper()):
        for k in ("2k", "2K"):
            for y in yy_variants:
                for a in ("Annex", "annex", "ANNEX"):
                    for suf in ("", "_0", "_1", "_2"):
                        names.append(f"{m}{k}{y}{a}{annex}{suf}.pdf")
    return list(dict.fromkeys(names))


def discover_links(html: str) -> dict[tuple[int, int, int], str]:
    """Map (year, month, annex) -> absolute PDF URL from the traffic-news index HTML."""
    out: dict[tuple[int, int, int], str] = {}
    for href in re.findall(r'href="([^"]+\.pdf)"', html, flags=re.IGNORECASE):
        name = href.rsplit("/", 1)[-1]
        m = _FNAME.search(name)
        if not m:
            continue
        mon = m.group(1).title()
        if mon not in MONTHS:
            continue
        year = 2000 + int(m.group(2))
        annex = int(m.group(3))
        if annex not in ANNEX_METRIC:
            continue
        url = href if href.startswith("http") else "https://www.aai.aero" + (href if href.startswith("/") else "/" + href)
        out.setdefault((year, MONTHS.index(mon) + 1, annex), url)
    return out


class Fetcher:
    def __init__(self, session: requests.Session | None = None, delay: float = 1.0):
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = config.USER_AGENT
        self.delay = delay
        self.index: dict[tuple[int, int, int], str] = {}

    def load_index(self, pages: int = 3) -> None:
        for p in range(pages):
            try:
                r = self.s.get(INDEX_URL, params={"page": p} if p else None, timeout=40)
                if r.status_code == 200:
                    self.index.update(discover_links(r.text))
            except requests.RequestException as e:
                print(f"AAI index fetch failed (page {p}): {e}")
            time.sleep(self.delay)

    def _get_pdf(self, url: str) -> bytes | None:
        try:
            r = self.s.get(url, timeout=60)
        except requests.RequestException:
            return None
        time.sleep(self.delay)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            return r.content
        return None

    def fetch(self, year: int, month: int, annex: int) -> tuple[bytes | None, str]:
        url = self.index.get((year, month, annex))
        if url:
            data = self._get_pdf(url)
            if data:
                return data, url
        for name in candidate_names(year, month, annex):
            url = FILE_BASE + name
            data = self._get_pdf(url)
            if data:
                return data, url
        return None, ""


# ---------------------------------------------------------------- monthly table I/O
def read_monthly(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {r["month"]: r for r in csv.DictReader(f) if r.get("month")}


def write_monthly(path: Path, table: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MONTHLY_FIELDS)
        w.writeheader()
        for m in sorted(table):
            w.writerow({k: table[m].get(k, "") for k in MONTHLY_FIELDS})


def merged_monthly() -> dict[str, dict]:
    """Auto-collected rows overridden field-by-field by manual rows."""
    auto = read_monthly(config.AAI_MONTHLY_CSV)
    manual = read_monthly(config.AAI_MANUAL_CSV)
    for m, row in manual.items():
        base = dict(auto.get(m, {"month": m}))
        for k, v in row.items():
            if v not in ("", None):
                base[k] = v
        base["source"] = row.get("source") or "manual"
        auto[m] = base
    return auto


def _fmt(v: float | None) -> str:
    if v is None:
        return ""
    return str(int(round(v))) if float(v).is_integer() or abs(v) >= 100 else f"{v:.1f}"


def apply_annex(table: dict[str, dict], year: int, month: int, annex: int, res: AnnexResult,
                url: str) -> None:
    metric = ANNEX_METRIC[annex]
    key = f"{year}-{month:02d}"
    prev_key = f"{year - 1}-{month:02d}"
    row = table.setdefault(key, {"month": key})
    prev = table.setdefault(prev_key, {"month": prev_key})
    tag = {"international": "intl", "domestic": "dom", "total": "total"}
    for sec, f in res.sections.items():
        row[f"{metric}_{tag[sec]}"] = _fmt(f.month)
        # previous-year column fills last year's month only if we have nothing better
        if not prev.get(f"{metric}_{tag[sec]}") and f.month_prev_year is not None:
            prev[f"{metric}_{tag[sec]}"] = _fmt(f.month_prev_year)
            prev.setdefault("source", "AAI Traffic News (prev-year column)")
    row["source"] = "AAI Traffic News"
    if not prev.get("source"):
        prev["source"] = "AAI Traffic News (prev-year column)"


def months_between(start: date, end: date) -> Iterable[tuple[int, int]]:
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def collect(start: date, end: date, refetch: bool = False, fetcher: Fetcher | None = None) -> dict:
    """Fetch and parse AAI annexures for every month in [start, end]; updates aai_monthly.csv."""
    table = read_monthly(config.AAI_MONTHLY_CSV)
    fx = fetcher or Fetcher()
    fx.load_index()
    log_rows = []
    summary = {"months_ok": 0, "months_missing": 0, "warnings": 0}
    for y, m in months_between(start, end):
        key = f"{y}-{m:02d}"
        existing = table.get(key, {})
        if not refetch and existing.get("source") == "AAI Traffic News" and existing.get("pax_total"):
            continue
        got_any = False
        for annex in (3, 2, 4):
            data, url = fx.fetch(y, m, annex)
            if not data:
                log_rows.append([key, annex, "", "not found"])
                continue
            try:
                res = parse_annex_rows(pdf_rows(data), annex)
            except Exception as e:  # corrupted PDF etc.
                log_rows.append([key, annex, url, f"parse error {e}"])
                continue
            if not res.sections:
                log_rows.append([key, annex, url, "Madurai row not found; " + "; ".join(res.warnings)])
                continue
            apply_annex(table, y, m, annex, res, url)
            got_any = True
            status = "ok" if not res.warnings else "check: " + "; ".join(res.warnings)
            summary["warnings"] += bool(res.warnings)
            log_rows.append([key, annex, url, status])
        summary["months_ok" if got_any else "months_missing"] += 1
    write_monthly(config.AAI_MONTHLY_CSV, table)
    new_log = not config.AAI_LOG_CSV.exists()
    with config.AAI_LOG_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_log:
            w.writerow(["month", "annex", "url", "status"])
        w.writerows(log_rows)
    return summary

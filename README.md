# IXM Pulse — Madurai Airport Tracker

Live flights, daily / weekly / monthly traffic, airline-wise data, cargo and passenger forecasts for
**Madurai International Airport (IXM / VOMD)** — with on-demand **PowerPoint and Excel reports**.

Built to give citizens, businesses and authorities clear, sourced evidence for more flights and better
connectivity from Madurai.

**Dashboard:** https://jarunprasath.github.io/madurai-airport-tracker/ (after Pages is enabled — see Setup)

## What it shows

| Tab | Content | Source |
|---|---|---|
| Live | Map + list of aircraft within ~60 km, refreshed every minute in the browser (snapshot every 30 min as fallback) | OpenSky Network |
| Today | Arrivals / departures board with status, aircraft, cargo flag; next-7-days schedule | AeroDataBox |
| Traffic | KPIs, daily movements, **official monthly passengers (domestic/international)**, annual FY totals, cargo tonnes, monthly table with YoY | AAI Traffic News |
| Airlines | Share of movements, airline-wise flights / passengers / on-time %, aircraft types | AeroDataBox |
| Routes | Movements per destination, flights per day, peak hours | AeroDataBox |
| Forecast | 12-month passenger forecast with 80% band and festival / holiday season tags | Model on AAI history |
| Reports | Download weekly and monthly PowerPoint + Excel reports | Generated |

## Reports (PowerPoint + Excel)

Each report has: key numbers vs previous period, auto-written insights, daily movements, airlines,
routes, fleet mix, peak hours, official AAI trend, forecast, and data notes. The Excel workbook adds
full tables (daily, airlines, routes, aircraft, hourly, AAI monthly, forecast, every flight) with native charts.

- **Automatic:** weekly every Monday, monthly on the 8th.
- **On demand:** GitHub → **Actions → Generate report → Run workflow** → choose `weekly` or `monthly`
  and optionally any date inside the period. Files appear in the dashboard's Reports tab, in `reports/`,
  and as a downloadable workflow artifact.
- **Locally:** `python -m ixm report --kind monthly --date 2026-09-15`

## Setup (one time)

1. **Enable GitHub Pages:** repository **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Flight data key (AeroDataBox):** create a free account on RapidAPI, subscribe to the *AeroDataBox*
   API (free tier), copy your key, then add it at **Settings → Secrets and variables → Actions →
   New repository secret** named `AERODATABOX_KEY`. Check the free-tier monthly quota on RapidAPI:
   the default schedule makes about 12 calls per day (2 runs × 3 days × 2 half-day windows) — reduce
   `--ahead`/`--back` in `.github/workflows/flights.yml` if your quota is smaller.
3. *(Optional)* OpenSky API client: secrets `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET` for higher
   rate limits. Anonymous access works without them.
4. **Backfill AAI history:** **Actions → AAI monthly traffic → Run workflow** with start `2018-04`.
   It works newest month first, saves after every month and stops after ~40 minutes; if the summary says
   "run again to continue", run it again with the same start until it doesn't. It checks first that aai.aero
   answers and stops within a minute if it doesn't. After that it runs automatically three times a month.
   Check the run summary / `data/aai_fetch_log.csv` for months that could not be found or parsed.

## How the numbers are produced — and their limits

- **Official figures** (passengers, aircraft movements, freight) come from AAI's monthly Traffic News
  PDFs (Annexure II/III/IV). They usually appear 4–8 weeks after month end. The PDF parser checks
  domestic + international = total and logs anything suspicious. **Correct any value** by adding a row to
  `data/aai_monthly_manual.csv`; manual values always win.
- **AAI does not publish daily or per-flight passenger counts.** Daily/weekly passengers here are
  **estimates**: typical seats for the aircraft type (`ixm/reference.py`) × a load factor. The load factor
  is calibrated each month as AAI passengers ÷ estimated seats (default 0.85 until a month can be calibrated).
- **Forecast:** seasonal index (learned from past years, COVID months excluded) × linear trend over the
  last 36 months; the 80% band comes from one-step-ahead backtest errors. Festivals (Pongal, Chithirai,
  Deepavali, Sabarimala season, holidays) show up through the seasonal pattern; the tags are by month
  only because exact dates change each year. It is a statistical estimate, not an official projection.
- `data/aai_annual.csv` seeds fiscal-year totals as listed on Wikipedia from AAI data — verify against
  AAI before quoting; monthly AAI data replaces them once complete years are collected.
- Coverage of AeroDataBox and OpenSky near Madurai is not guaranteed. Gaps are shown, not filled.

## Run locally

```bash
pip install -r requirements-dev.txt && npm install
export AERODATABOX_KEY=...           # optional
python -m ixm flights --back 1 --ahead 1
python -m ixm aai --start 2025-04
python -m ixm live
python -m ixm build                  # writes site/data/*.json
python -m http.server -d site 8000   # open http://localhost:8000
python -m ixm report --kind weekly
python -m pytest -q
```

## Project layout

```
ixm/            Python package: collectors (aerodatabox, opensky, aai), store, analytics,
                forecast, build (dashboard JSON), report (Excel + report data)
report_pptx.js  PowerPoint builder (pptxgenjs, native editable charts)
site/           Static dashboard (HTML/CSS/JS, vendored Chart.js + Leaflet)
data/           Collected data (committed by the workflows)
reports/        Generated PowerPoint/Excel reports
.github/        Scheduled collection, report and Pages deployment workflows
```

## Credits and licences

Code: MIT © Arun Prasath J. Data © their respective providers (AAI, AeroDataBox, OpenSky Network);
map © OpenStreetMap contributors. Vendored libraries: Chart.js (MIT), Leaflet (BSD-2-Clause) — licences in `site/vendor/`.

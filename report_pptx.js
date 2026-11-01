// Builds the weekly/monthly PowerPoint from the JSON written by ixm/report.py.
// Usage: node report_pptx.js report.json out.pptx
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const [, , inPath, outPath] = process.argv;
if (!inPath || !outPath) {
  console.error("usage: node report_pptx.js report.json out.pptx");
  process.exit(2);
}
const d = JSON.parse(fs.readFileSync(inPath, "utf8"));

// Palette: temple maroon (dominant), marigold accent, teal support, slate ink
const MAROON = "7A1E2C", GOLD = "D99A2B", TEAL = "2A7F80", INK = "2B2D42", MUTED = "6B7280",
  LIGHT = "F4F1EE", WHITE = "FFFFFF", GRID = "E5E1DC";
const SERIES = [MAROON, GOLD, TEAL, "8D6A9F", "5B8C5A", "B5651D", "4A6FA5", "9C9C9C"];
const FONT_H = "Cambria", FONT_B = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.title = `${d.airport.name} - ${d.kind} report - ${d.label}`;
pres.author = "Madurai Airport Tracker";
pres.theme = { headFontFace: FONT_H, bodyFontFace: FONT_B };

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: WHITE },
  objects: [
    { text: { text: `${d.airport.name} (${d.airport.iata}) · ${d.label}`,
      options: { x: 0.5, y: 5.2, w: 7.5, h: 0.3, fontSize: 9, color: MUTED, fontFace: FONT_B } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9, h: 0.7,
      fontSize: 26, bold: true, color: INK, fontFace: FONT_H, valign: "middle" }, text: "" } },
  ],
  slideNumber: { x: 9.0, y: 5.2, w: 0.5, h: 0.3, fontSize: 9, color: MUTED, fontFace: FONT_B },
});

const fmt = (v) => (v === null || v === undefined ? "–" : Math.round(v).toLocaleString("en-IN"));
const chg = (v) => (v === null || v === undefined ? "no comparison" : `${v > 0 ? "▲" : v < 0 ? "▼" : "■"} ${Math.abs(v)}% vs previous`);
const axis = () => ({
  catAxisLabelColor: MUTED, valAxisLabelColor: MUTED, catAxisLabelFontFace: FONT_B,
  valAxisLabelFontFace: FONT_B, catAxisLabelFontSize: 10, valAxisLabelFontSize: 10,
  valGridLine: { color: GRID, size: 0.5 }, catGridLine: { style: "none" },
  titleColor: INK, titleFontFace: FONT_B, titleFontSize: 12, dataLabelColor: INK,
  dataLabelFontSize: 9, dataLabelFontFace: FONT_B, valAxisMinVal: 0,
});

function contentSlide(title) {
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText(title, { placeholder: "title" });
  return s;
}

function emptyNote(s, msg, x = 0.5, y = 1.3, w = 9, h = 3.5) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: LIGHT }, line: { color: LIGHT },
    rectRadius: 0.1, objectName: "empty-state" });
  s.addText(msg, { x: x + 0.4, y, w: w - 0.8, h, fontSize: 16, color: MUTED, fontFace: FONT_B,
    align: "center", valign: "middle", isTextBox: true });
}

function commentary(s, lines, x = 6.9, y = 1.3, w = 2.6, h = 3.6) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: LIGHT }, line: { color: LIGHT },
    rectRadius: 0.08, objectName: "commentary-card" });
  s.addText(lines.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < lines.length - 1 } })),
    { x: x + 0.15, y: y + 0.15, w: w - 0.3, h: h - 0.3, fontSize: 12, color: INK, fontFace: FONT_B,
      valign: "top", paraSpaceAfter: 6, isTextBox: true });
}

const hasFlights = d.kpi.movements > 0;
const k = d.kpi, kc = d.kpi_change;

// 1. Title
{
  const s = pres.addSlide();
  s.background = { color: MAROON };
  s.addShape(pres.shapes.OVAL, { x: 7.2, y: -1.2, w: 4.2, h: 4.2, fill: { color: GOLD, transparency: 80 },
    line: { color: GOLD, transparency: 80 }, objectName: "motif-circle" });
  s.addText("MADURAI AIRPORT · IXM / VOMD", { x: 0.6, y: 1.0, w: 8, h: 0.4, fontSize: 14, color: GOLD,
    bold: true, charSpacing: 3, fontFace: FONT_B, isTextBox: true });
  s.addText(`${d.kind === "weekly" ? "Weekly" : "Monthly"} traffic report`, { x: 0.6, y: 1.5, w: 8.5, h: 1.0,
    fontSize: 40, bold: true, color: WHITE, fontFace: FONT_H, isTextBox: true });
  s.addText(d.label, { x: 0.6, y: 2.5, w: 8.5, h: 0.5, fontSize: 20, color: WHITE, fontFace: FONT_B, isTextBox: true });
  s.addText("Flights · passengers · airlines · routes · cargo · forecast", { x: 0.6, y: 3.6, w: 8.5, h: 0.4,
    fontSize: 13, color: "E9C9CE", italic: true, fontFace: FONT_B, isTextBox: true });
  s.addText(`Generated ${new Date().toISOString().slice(0, 10)} · data: AAI, AeroDataBox, OpenSky`,
    { x: 0.6, y: 4.8, w: 8.5, h: 0.3, fontSize: 10, color: "E9C9CE", fontFace: FONT_B, isTextBox: true });
}

// 2. Key numbers
{
  const s = contentSlide("Key numbers at a glance");
  const A = d.aai_this_month, P = d.aai_prev_year || {};
  const yoy = (c, p) => (c === null || c === undefined || !p ? "no comparison" :
    `${c > p ? "▲" : c < p ? "▼" : "■"} ${Math.abs(Math.round(1000 * (c - p) / p) / 10)}% vs a year ago`);
  // No flight-schedule data for the period: show the official AAI month instead of zeros
  const cards = (!hasFlights && A) ? [
    ["Passengers (AAI)", fmt(A.pax_total), yoy(A.pax_total, P.pax_total)],
    ["International passengers", fmt(A.pax_intl), yoy(A.pax_intl, P.pax_intl)],
    ["Aircraft movements", fmt(A.mov_total), yoy(A.mov_total, P.mov_total)],
    ["Cargo (tonnes)", fmt(A.frt_total), yoy(A.frt_total, P.frt_total)],
  ] : [
    ["Flight movements", fmt(k.movements), chg(kc.movements)],
    ["Est. passengers", fmt(k.est_pax), chg(kc.est_pax)],
    ["International movements", fmt(k.international), chg(kc.international)],
    ["Cargo flight movements", fmt(k.cargo), chg(kc.cargo)],
  ];
  cards.forEach(([label, value, sub], i) => {
    const x = 0.5 + i * 2.3;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.3, w: 2.1, h: 2.0, fill: { color: LIGHT },
      line: { color: LIGHT }, rectRadius: 0.1, objectName: `kpi-card-${i}` });
    s.addText(value, { x, y: 1.45, w: 2.1, h: 0.9, fontSize: 36, bold: true, color: i === 0 ? MAROON : INK,
      align: "center", fontFace: FONT_H, isTextBox: true });
    s.addText(label, { x: x + 0.1, y: 2.35, w: 1.9, h: 0.4, fontSize: 12, color: INK, align: "center",
      fontFace: FONT_B, isTextBox: true });
    s.addText(sub, { x: x + 0.1, y: 2.75, w: 1.9, h: 0.35, fontSize: 10, color: MUTED, align: "center",
      fontFace: FONT_B, isTextBox: true });
  });
  const a = d.aai_this_month;
  const line2 = (!hasFlights && a)
    ? `Official AAI figures for ${a.month} (domestic ${fmt(a.pax_dom)} passengers). Flight-by-flight data was not collected for this period.`
    : a
    ? `AAI official for ${a.month}: ${fmt(a.pax_total)} passengers · ${fmt(a.mov_total)} aircraft movements · ${a.frt_total ?? "–"} t freight`
    : "AAI official monthly figures for this period are not published yet (they usually lag 4–8 weeks).";
  s.addText(line2, { x: 0.5, y: 3.6, w: 9, h: 0.5, fontSize: 13, color: INK, fontFace: FONT_B, isTextBox: true });
  s.addText(`Passengers per flight are estimated: typical seats × load factor ${d.load_factor} (${d.load_factor_note}). ` +
    `Data covers ${d.days_with_data} of ${d.days_in_period} days.`,
  { x: 0.5, y: 4.2, w: 9, h: 0.6, fontSize: 10, color: MUTED, fontFace: FONT_B, isTextBox: true });
}

// 3. Insights
{
  const s = contentSlide("What the data says");
  const lines = d.insights.slice(0, 8);
  s.addText(lines.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < lines.length - 1 } })),
    { x: 0.5, y: 1.2, w: hasFlights ? 5.8 : 9, h: 3.8, fontSize: 14, color: INK, fontFace: FONT_B,
      valign: "top", paraSpaceAfter: 8, isTextBox: true });
  if (hasFlights) {
    s.addChart(pres.charts.DOUGHNUT, [{ name: "Movements", labels: ["Domestic", "International"],
      values: [k.domestic, k.international] }], {
      x: 6.5, y: 1.2, w: 3.0, h: 3.6, holeSize: 60, chartColors: [MAROON, GOLD], showLegend: true,
      legendPos: "b", legendFontSize: 10, legendColor: INK, legendFontFace: FONT_B, showPercent: true,
      showValue: false, dataLabelColor: WHITE, dataLabelFontSize: 11, showTitle: true,
      title: "Domestic vs international", titleColor: INK, titleFontSize: 12, titleFontFace: FONT_B,
    });
  }
}

// 4. Daily movements
{
  const s = contentSlide(d.kind === "weekly" ? "Daily flight movements this week" : `Daily flight movements – ${d.label}`);
  if (hasFlights) {
    const labels = d.daily.map((x) => x.date.slice(8));
    s.addChart(pres.charts.BAR, [
      { name: "Arrivals", labels, values: d.daily.map((x) => x.arrivals) },
      { name: "Departures", labels, values: d.daily.map((x) => x.departures) },
    ], { x: 0.5, y: 1.2, w: 6.2, h: 3.8, barDir: "col", barGrouping: "stacked", chartColors: [MAROON, GOLD],
      showLegend: true, legendPos: "b", legendFontSize: 10, legendColor: INK, showTitle: false,
      showValue: d.daily.length <= 10, dataLabelPosition: "ctr", ...axis(), dataLabelColor: WHITE });
    const busiest = d.daily.reduce((a, b) => (b.movements > a.movements ? b : a));
    const avg = (k.movements / d.daily.length).toFixed(1);
    commentary(s, [
      `${avg} movements per day on average`,
      `Busiest day: ${busiest.date} (${busiest.movements})`,
      `${k.cancelled} cancelled or diverted`,
      k.on_time_pct !== null ? `On-time (≤15 min): ${k.on_time_pct}%` : "On-time data not available",
    ]);
  } else emptyNote(s, "No flight-schedule data collected for this period yet.\nAdd the AERODATABOX_KEY secret to start collecting.");
}

// 5. Airlines
{
  const s = contentSlide("Airlines serving Madurai");
  if (d.airlines.length) {
    const top = d.airlines.slice(0, 8);
    s.addChart(pres.charts.BAR, [{ name: "Movements", labels: top.map((a) => a.airline), values: top.map((a) => a.flights) }],
      { x: 0.5, y: 1.2, w: 4.6, h: 3.8, barDir: "bar", chartColors: [MAROON], showLegend: false,
        showValue: true, dataLabelPosition: "outEnd", catAxisOrientation: "maxMin", ...axis() });
    const rows = [["Airline", "Flights", "Share", "Est. pax"].map((t) => ({ text: t,
      options: { bold: true, color: WHITE, fill: { color: INK } } }))];
    top.slice(0, 7).forEach((a) => rows.push([a.airline, fmt(a.flights), `${a.share_pct}%`, fmt(a.est_pax)]));
    s.addTable(rows, { x: 5.3, y: 1.25, w: 4.2, colW: [1.8, 0.7, 0.75, 0.95], fontSize: 11, fontFace: FONT_B,
      color: INK, border: { type: "solid", pt: 0.5, color: GRID }, rowH: 0.34 });
  } else emptyNote(s, "No airline data for this period yet.");
}

// 6. Routes
{
  const s = contentSlide("Routes and connectivity");
  if (d.routes.length) {
    const top = d.routes.slice(0, 10);
    s.addChart(pres.charts.BAR, [{ name: "Movements", labels: top.map((r) => `${r.city || r.iata}${r.international ? " ✈" : ""}`),
      values: top.map((r) => r.flights) }], { x: 0.5, y: 1.2, w: 6.2, h: 3.8, barDir: "bar",
      chartColors: [TEAL], showLegend: false, showValue: true, dataLabelPosition: "outEnd",
      catAxisOrientation: "maxMin", ...axis() });
    const intl = d.routes.filter((r) => r.international);
    commentary(s, [
      `${d.routes.length} destinations connected`,
      `${intl.length} international: ${intl.map((r) => r.city || r.iata).join(", ") || "none"}`,
      `Top route: ${top[0].city || top[0].iata} (~${top[0].per_day}/day)`,
      "✈ marks international routes",
    ]);
  } else emptyNote(s, "No route data for this period yet.");
}

// 7. Aircraft types & peak hours
{
  const s = contentSlide("Fleet mix and peak hours");
  if (hasFlights) {
    const ac = d.aircraft.slice(0, 6);
    s.addChart(pres.charts.BAR, [{ name: "Movements", labels: ac.map((a) => a.aircraft), values: ac.map((a) => a.flights) }],
      { x: 0.5, y: 1.2, w: 4.4, h: 3.8, barDir: "bar", chartColors: [GOLD], showLegend: false, showValue: true,
        dataLabelPosition: "outEnd", catAxisOrientation: "maxMin", showTitle: true, title: "Aircraft types", ...axis() });
    s.addChart(pres.charts.BAR, [{ name: "Movements", labels: d.hourly.map((_, h) => String(h).padStart(2, "0")), values: d.hourly }],
      { x: 5.1, y: 1.2, w: 4.4, h: 3.8, barDir: "col", chartColors: [MAROON], showLegend: false, showValue: false,
        showTitle: true, title: "Scheduled movements by hour (local)", ...axis(), catAxisLabelFontSize: 8 });
  } else emptyNote(s, "No fleet or timing data for this period yet.");
}

// 8. AAI official trend
{
  const s = contentSlide("Official passenger traffic (AAI)");
  const h = d.aai_history;
  if (h.length) {
    const labels = h.map((x) => x.month);
    const series = [{ name: "Total", labels, values: h.map((x) => x.pax_total || 0) }];
    if (h.every((x) => x.pax_intl !== null)) series.push({ name: "International", labels, values: h.map((x) => x.pax_intl || 0) });
    s.addChart(pres.charts.LINE, series, { x: 0.5, y: 1.2, w: 6.2, h: 3.8, chartColors: [MAROON, GOLD],
      lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 5, showLegend: series.length > 1,
      legendPos: "b", legendFontSize: 10, legendColor: INK, ...axis(), catAxisLabelFontSize: 8,
      catAxisLabelRotate: -45 });
    const last = h[h.length - 1];
    const fy = (d.aai_annual || []).slice(-2);
    commentary(s, [
      `Latest month ${last.month}: ${fmt(last.pax_total)} passengers`,
      last.pax_yoy_pct !== null ? `${last.pax_yoy_pct > 0 ? "+" : ""}${last.pax_yoy_pct}% year on year` : "Year-on-year not available",
      ...fy.map((y) => `FY ${y.fiscal_year}: ${fmt(Number(y.passengers))} passengers`),
      "Source: AAI monthly Traffic News",
    ]);
  } else emptyNote(s, "AAI monthly data has not been collected yet.\nRun the 'AAI monthly backfill' workflow once.");
}

// 9. Forecast
{
  const s = contentSlide("Passenger forecast – next 12 months");
  const fc = d.forecast;
  if (fc.available) {
    const labels = fc.points.map((p) => p.month);
    s.addChart(pres.charts.LINE, [
      { name: "Forecast", labels, values: fc.points.map((p) => p.forecast) },
      { name: "Low (80%)", labels, values: fc.points.map((p) => p.low) },
      { name: "High (80%)", labels, values: fc.points.map((p) => p.high) },
    ], { x: 0.5, y: 1.2, w: 6.2, h: 3.8, chartColors: [MAROON, "C9B9A8", "C9B9A8"], lineSize: 2,
      showLegend: true, legendPos: "b", legendFontSize: 10, legendColor: INK, ...axis(), catAxisLabelFontSize: 8,
      catAxisLabelRotate: -45 });
    const peak = fc.points.reduce((a, b) => (b.forecast > a.forecast ? b : a));
    commentary(s, [
      `Peak expected: ${peak.month} (~${fmt(peak.forecast)})` + (peak.season.length ? ` – ${peak.season[0]}` : ""),
      `Next 12 months total: ~${fmt(fc.points.reduce((t, p) => t + p.forecast, 0))}`,
      `Backtest error (MAPE): ${fc.backtest_mape_pct ?? "–"}%`,
      "Seasonal pattern learned from past years (festivals, holidays)",
    ]);
  } else emptyNote(s, `Forecast not available yet: ${fc.reason || "insufficient history"}.`);
}

// 10. Notes & sources
{
  const s = pres.addSlide();
  s.background = { color: INK };
  s.addText("Data notes and sources", { x: 0.5, y: 0.4, w: 9, h: 0.7, fontSize: 26, bold: true, color: WHITE,
    fontFace: FONT_H, isTextBox: true });
  const lines = [...d.caveats, `Sources: ${d.sources.join(" · ")}`];
  s.addText(lines.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < lines.length - 1 } })),
    { x: 0.5, y: 1.3, w: 9, h: 3.6, fontSize: 13, color: "E5E7EB", fontFace: FONT_B, valign: "top",
      paraSpaceAfter: 8, isTextBox: true });
}

pres.writeFile({ fileName: outPath }).then(() => console.log(`wrote ${outPath}`));

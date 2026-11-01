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

function img(s, key, box, alt) {
  if (!d.charts || !d.charts[key] || !fs.existsSync(d.charts[key])) return false;
  s.addImage({ path: d.charts[key], ...box, altText: alt || key });
  return true;
}
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
  s.addText(`${d.kind === "weekly" ? "Weekly" : d.kind === "yearly" ? "Yearly" : "Monthly"} traffic report`, { x: 0.6, y: 1.5, w: 8.5, h: 1.0,
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
  // Yearly reports always lead with AAI's official figures (flight data rarely covers a whole year)
  const useAAI = A && (!hasFlights || d.kind === "yearly");
  // yearly: change is like-for-like over the months present in both years
  const L = (k) => (A && A[`${k}_lfl`] !== undefined ? A[`${k}_lfl`] : A && A[k]);
  const lflNote = A && A.lfl_months && A.lfl_months < 12 ? ` (${A.lfl_months} mo.)` : "";
  const cards = useAAI ? [
    ["Passengers (AAI)", fmt(A.pax_total), yoy(L("pax_total"), P.pax_total) + lflNote],
    ["International passengers", fmt(A.pax_intl), yoy(L("pax_intl"), P.pax_intl) + lflNote],
    ["Aircraft movements", fmt(A.mov_total), yoy(L("mov_total"), P.mov_total) + lflNote],
    ["Cargo (tonnes)", fmt(A.frt_total), yoy(L("frt_total"), P.frt_total) + lflNote],
  ] : [
    ["Flight movements", fmt(k.movements), chg(kc.movements)],
    ["Est. passengers", fmt(k.est_pax), chg(kc.est_pax)],
    ["International movements", fmt(k.international), chg(kc.international)],
    ["Cargo flight movements", fmt(k.cargo), chg(kc.cargo)],
  ];
  if (!hasFlights && !A) {
    emptyNote(s, `${d.no_flight_reason}\nOfficial AAI figures for ${d.end.slice(0, 7)} are not published yet (AAI usually publishes 4–8 weeks after month end).`, 0.5, 1.3, 9, 2.0);
  } else cards.forEach(([label, value, sub], i) => {
    const x = 0.5 + i * 2.3;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.3, w: 2.1, h: 2.0, fill: { color: LIGHT },
      line: { color: LIGHT }, rectRadius: 0.1, objectName: `kpi-card-${i}` });
    s.addText(value, { x, y: 1.45, w: 2.1, h: 0.9, fontSize: value.length > 8 ? 28 : 36, bold: true, color: i === 0 ? MAROON : INK,
      align: "center", fontFace: FONT_H, isTextBox: true });
    s.addText(label, { x: x + 0.1, y: 2.35, w: 1.9, h: 0.4, fontSize: 12, color: INK, align: "center",
      fontFace: FONT_B, isTextBox: true });
    s.addText(sub, { x: x + 0.1, y: 2.75, w: 1.9, h: 0.35, fontSize: 10, color: MUTED, align: "center",
      fontFace: FONT_B, isTextBox: true });
  });
  const a = d.aai_this_month;
  const line2 = (a && d.aai_is_latest_available)
    ? `AAI has not yet published figures for this period; cards show the latest published month, ${a.month} (domestic ${fmt(a.pax_dom)} passengers).` +
      (hasFlights ? "" : ` ${d.no_flight_reason}`)
    : (d.kind === "yearly" && a)
    ? `Official AAI figures for ${a.month}: domestic ${fmt(a.pax_dom)} passengers` + (a.missing && a.missing.length ? ` (${a.months} of ${a.months_expected} months; ${a.missing.join(", ")} not published).` : ".") +
      (hasFlights ? ` Flight-level detail covers ${d.days_with_data} of ${d.days_in_period} days.` : "")
    : (!hasFlights && a)
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
    img(s, "domintl", { x: 6.5, y: 1.2, w: 3.0, h: 3.6 }, "Domestic vs international movements") || s.addChart(pres.charts.DOUGHNUT, [{ name: "Movements", labels: ["Domestic", "International"],
      values: [k.domestic, k.international] }], {
      x: 6.5, y: 1.2, w: 3.0, h: 3.6, holeSize: 60, chartColors: [MAROON, GOLD], showLegend: true,
      legendPos: "b", legendFontSize: 10, legendColor: INK, legendFontFace: FONT_B, showPercent: true,
      showValue: false, dataLabelColor: WHITE, dataLabelFontSize: 11, showTitle: true,
      title: "Domestic vs international", titleColor: INK, titleFontSize: 12, titleFontFace: FONT_B,
    });
  }
}

// 4. Daily movements (yearly reports: month-by-month official passengers instead)
if (d.kind === "yearly" && (d.fy_months || []).length) {
  const s = contentSlide(`Month by month – ${d.label.split(" (")[0]}`);
  const fm = d.fy_months;
  const labels = fm.map((x) => { const [y, m] = x.month.split("-"); return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+m - 1] + " " + y.slice(2); });
  img(s, "fy_months", { x: 0.5, y: 1.2, w: 6.2, h: 3.8 }, "Monthly passengers in the financial year") || s.addChart(pres.charts.BAR, [
    { name: "Domestic", labels, values: fm.map((x) => x.pax_dom || 0) },
    { name: "International", labels, values: fm.map((x) => x.pax_intl || 0) },
  ], { x: 0.5, y: 1.2, w: 6.2, h: 3.8, barDir: "col", barGrouping: "stacked", chartColors: [MAROON, GOLD],
    showLegend: true, legendPos: "b", legendFontSize: 10, legendColor: INK, showValue: false, ...axis() });
  const tot = fm.reduce((t, x) => t + (x.pax_total || 0), 0);
  const best = fm.reduce((a, b) => ((b.pax_total || 0) > (a.pax_total || 0) ? b : a));
  const A = d.aai_this_month || {};
  commentary(s, [
    `${fmt(tot)} passengers in ${fm.length} month${fm.length > 1 ? "s" : ""}`,
    `Average ${fmt(tot / fm.length)} per month`,
    `Busiest: ${best.month} (${fmt(best.pax_total)})`,
    A.pax_intl ? `International share ${(100 * A.pax_intl / A.pax_total).toFixed(1)}%` : "Source: AAI monthly Traffic News",
    ...(A.missing && A.missing.length ? [`Not published by AAI: ${A.missing.join(", ")}`] : []),
  ]);
} else if (hasFlights) {
  const s = contentSlide(d.kind === "weekly" ? "Daily flight movements this week" : `Daily flight movements – ${d.label}`);
  if (hasFlights) {
    const labels = d.daily.map((x) => x.date.slice(8));
    img(s, "daily", { x: 0.5, y: 1.2, w: 6.2, h: 3.8 }, "Daily arrivals and departures") || s.addChart(pres.charts.BAR, [
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
  }
}

// 5. Airlines
if (d.airlines.length) {
  const s = contentSlide("Airlines serving Madurai");
  if (d.airlines.length) {
    const top = d.airlines.slice(0, 8);
    img(s, "airlines", { x: 0.5, y: 1.2, w: 4.6, h: 3.8 }, "Movements by airline") || s.addChart(pres.charts.BAR, [{ name: "Movements", labels: top.map((a) => a.airline), values: top.map((a) => a.flights) }],
      { x: 0.5, y: 1.2, w: 4.6, h: 3.8, barDir: "bar", chartColors: [MAROON], showLegend: false,
        showValue: true, dataLabelPosition: "outEnd", catAxisOrientation: "maxMin", ...axis() });
    const rows = [["Airline", "Flights", "Share", "Est. pax"].map((t) => ({ text: t,
      options: { bold: true, color: WHITE, fill: { color: INK } } }))];
    top.slice(0, 7).forEach((a) => rows.push([a.airline, fmt(a.flights), `${a.share_pct}%`, fmt(a.est_pax)]));
    s.addTable(rows, { x: 5.3, y: 1.25, w: 4.2, colW: [1.8, 0.7, 0.75, 0.95], fontSize: 11, fontFace: FONT_B,
      color: INK, border: { type: "solid", pt: 0.5, color: GRID }, rowH: 0.34 });
  }
}

// 6. Routes
if (d.routes.length) {
  const s = contentSlide("Routes and connectivity");
  if (d.routes.length) {
    const top = d.routes.slice(0, 10);
    img(s, "routes", { x: 0.5, y: 1.2, w: 6.2, h: 3.8 }, "Movements by route") || s.addChart(pres.charts.BAR, [{ name: "Movements", labels: top.map((r) => `${r.city || r.iata}${r.international ? " ✈" : ""}`),
      values: top.map((r) => r.flights) }], { x: 0.5, y: 1.2, w: 6.2, h: 3.8, barDir: "bar",
      chartColors: [TEAL], showLegend: false, showValue: true, dataLabelPosition: "outEnd",
      catAxisOrientation: "maxMin", ...axis() });
    const intl = d.routes.filter((r) => r.international);
    commentary(s, [
      `${d.routes.length} destinations connected`,
      `${intl.length} international: ${intl.map((r) => r.city || r.iata).join(", ") || "none"}`,
      `Top route: ${top[0].city || top[0].iata} (~${top[0].per_day}/day)`,
      "Orange bars marked (intl) are international routes",
    ]);
  }
}

// 7. Aircraft types & peak hours
if (hasFlights) {
  const s = contentSlide("Fleet mix and peak hours");
  if (hasFlights) {
    const ac = d.aircraft.slice(0, 6);
    img(s, "aircraft", { x: 0.5, y: 1.2, w: 4.4, h: 3.8 }, "Movements by aircraft type") || s.addChart(pres.charts.BAR, [{ name: "Movements", labels: ac.map((a) => a.aircraft), values: ac.map((a) => a.flights) }],
      { x: 0.5, y: 1.2, w: 4.4, h: 3.8, barDir: "bar", chartColors: [GOLD], showLegend: false, showValue: true,
        dataLabelPosition: "outEnd", catAxisOrientation: "maxMin", showTitle: true, title: "Aircraft types", ...axis() });
    img(s, "hourly", { x: 5.1, y: 1.2, w: 4.4, h: 3.8 }, "Movements by hour of day") || s.addChart(pres.charts.BAR, [{ name: "Movements", labels: d.hourly.map((_, h) => String(h).padStart(2, "0")), values: d.hourly }],
      { x: 5.1, y: 1.2, w: 4.4, h: 3.8, barDir: "col", chartColors: [MAROON], showLegend: false, showValue: false,
        showTitle: true, title: "Scheduled movements by hour (local)", ...axis(), catAxisLabelFontSize: 8 });
  }
}

// 8. AAI official trend
if ((d.aai_history || []).length) {
  const s = contentSlide("Official passenger traffic (AAI)");
  const h = d.aai_history;
  if (h.length) {
    const labels = h.map((x) => x.month);
    const series = [{ name: "Total", labels, values: h.map((x) => x.pax_total || 0) }];
    if (h.every((x) => x.pax_intl !== null)) series.push({ name: "International", labels, values: h.map((x) => x.pax_intl || 0) });
    img(s, "aai", { x: 0.5, y: 1.2, w: 6.2, h: 3.8 }, "Official monthly passengers (AAI)") || s.addChart(pres.charts.LINE, series, { x: 0.5, y: 1.2, w: 6.2, h: 3.8, chartColors: [MAROON, GOLD],
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
  }
}

// 9. Forecast
if (d.forecast && d.forecast.available) {
  const s = contentSlide("Passenger forecast – next 12 months");
  const fc = d.forecast;
  if (fc.available) {
    const labels = fc.points.map((p) => p.month);
    img(s, "forecast", { x: 0.5, y: 1.2, w: 6.2, h: 3.8 }, "12-month passenger forecast") || s.addChart(pres.charts.LINE, [
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
  }
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

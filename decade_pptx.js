// 10-year strategic review deck for Madurai Airport. Usage: node decade_pptx.js review.json out.pptx
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const [, , inPath, outPath] = process.argv;
const d = JSON.parse(fs.readFileSync(inPath, "utf8"));

const MAROON = "7A1E2C", GOLD = "D99A2B", TEAL = "1F8A86", SAFFRON = "D2622A", INDIGO = "4A5FB0",
  INK = "2B2D42", MUTED = "6B7280", LIGHT = "F4F1EE", WHITE = "FFFFFF", GRID = "E5E1DC", PALE = "C9B9A8";
const FONT_H = "Cambria", FONT_B = "Calibri";
const nf = new Intl.NumberFormat("en-IN");
const fmt = (v) => (v === null || v === undefined ? "–" : nf.format(Math.round(v)));
const lakh = (v) => `${(v / 1e5).toFixed(1)} lakh`;
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const mlab = (ym) => `${MON[+ym.slice(5, 7) - 1]} ${ym.slice(2, 4)}`;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "Madurai Airport – 10-year traffic review and growth agenda";
pres.author = "Arun Prasath J";
pres.theme = { headFontFace: FONT_H, bodyFontFace: FONT_B };
pres.defineSlideMaster({
  title: "CONTENT", background: { color: WHITE },
  objects: [
    { text: { text: "Madurai Airport (IXM) · 10-year review · Arun Prasath J",
      options: { x: 0.5, y: 5.22, w: 6.5, h: 0.28, fontSize: 9, color: MUTED, fontFace: FONT_B } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.28, w: 9, h: 0.7, fontSize: 24, bold: true,
      color: INK, fontFace: FONT_H, valign: "middle" }, text: "" } },
  ],
  slideNumber: { x: 9.0, y: 5.22, w: 0.5, h: 0.28, fontSize: 9, color: MUTED, fontFace: FONT_B },
});
const axis = () => ({ catAxisLabelColor: MUTED, valAxisLabelColor: MUTED, catAxisLabelFontFace: FONT_B, valAxisLabelFontFace: FONT_B,
  catAxisLabelFontSize: 9, valAxisLabelFontSize: 9, valGridLine: { color: GRID, size: 0.5 }, catGridLine: { style: "none" },
  dataLabelColor: INK, dataLabelFontSize: 9, dataLabelFontFace: FONT_B, valAxisMinVal: 0, titleColor: INK, titleFontSize: 11,
  titleFontFace: FONT_B, legendFontSize: 9, legendColor: INK, legendFontFace: FONT_B, valAxisLabelFormatCode: "#,##0" });
function slide(title, source) {
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText(title, { placeholder: "title" });
  if (source) s.addText(`Source: ${source}`, { x: 0.5, y: 4.95, w: 9, h: 0.25, fontSize: 8.5, color: MUTED, italic: true, fontFace: FONT_B, isTextBox: true });
  return s;
}
function card(s, x, y, w, h) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: LIGHT }, line: { color: LIGHT }, rectRadius: 0.08 });
}
function bullets(s, lines, x, y, w, h, size = 12, color = INK) {
  s.addText(lines.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < lines.length - 1 } })),
    { x, y, w, h, fontSize: size, color, fontFace: FONT_B, valign: "top", paraSpaceAfter: 5, isTextBox: true });
}
function side(s, lines, x = 6.85, y = 1.15, w = 2.65, h = 3.7, size = 11.5) {
  card(s, x, y, w, h);
  bullets(s, lines, x + 0.12, y + 0.12, w - 0.24, h - 0.24, size);
}
function stat(s, x, y, w, value, label, sub, color = INK) {
  card(s, x, y, w, 1.55);
  s.addText(value, { x, y: y + 0.12, w, h: 0.65, fontSize: value.length > 9 ? 22 : 28, bold: true, color, align: "center", fontFace: FONT_H, isTextBox: true });
  s.addText(label, { x: x + 0.08, y: y + 0.78, w: w - 0.16, h: 0.35, fontSize: 10.5, color: INK, align: "center", fontFace: FONT_B, isTextBox: true });
  if (sub) s.addText(sub, { x: x + 0.08, y: y + 1.1, w: w - 0.16, h: 0.35, fontSize: 9, color: MUTED, align: "center", fontFace: FONT_B, isTextBox: true });
}

const FY = d.fy_table;
const full = FY.filter((f) => f.months === 12);
const fy = (k) => FY.find((f) => f.fy === k) || {};
const peers = d.peers, ixm = peers.find((p) => p.airport.startsWith("Madurai")), trz = peers.find((p) => p.airport.startsWith("Tiruchi"));
const nmonths = Object.keys(d.network).sort();
const nlast = d.network[d.ref_month] || {};
const scen = d.scenarios;
const AAI = "AAI monthly Traffic News (aai.aero), compiled by the IXM Pulse tracker";
const PEER_SRC = "AAI annual figures as tabulated on Wikipedia 'List of busiest airports in India' (verify before quoting)";
const ADB = "AeroDataBox flight records collected by the IXM Pulse tracker";

// 1 ---------------------------------------------------------------- title
{
  const s = pres.addSlide(); s.background = { color: MAROON };
  s.addShape(pres.shapes.OVAL, { x: 7.0, y: -1.4, w: 4.6, h: 4.6, fill: { color: GOLD, transparency: 80 }, line: { color: GOLD, transparency: 80 } });
  s.addText("MADURAI AIRPORT · IXM / VOMD", { x: 0.6, y: 0.9, w: 8, h: 0.4, fontSize: 13, color: GOLD, bold: true, charSpacing: 3, fontFace: FONT_B, isTextBox: true });
  s.addText("Ten years of traffic – and how Madurai can catch up", { x: 0.6, y: 1.35, w: 8.6, h: 1.4, fontSize: 34, bold: true, color: WHITE, fontFace: FONT_H, isTextBox: true });
  s.addText(`Review of FY 2016-17 to FY 2026-27 (to ${mlab(d.aai_range[1])}) with recommendations for authorities and airlines`,
    { x: 0.6, y: 2.85, w: 8.4, h: 0.6, fontSize: 15, color: WHITE, fontFace: FONT_B, isTextBox: true });
  s.addText(`Prepared by Arun Prasath J · Data: AAI (${d.aai_months} months), AeroDataBox (${d.flight_days} days of flights) · ${d.generated}`,
    { x: 0.6, y: 4.75, w: 8.8, h: 0.35, fontSize: 10.5, color: "E9C9CE", fontFace: FONT_B, isTextBox: true });
}

// 2 ---------------------------------------------------------------- executive summary
{
  const s = slide("Executive summary");
  stat(s, 0.5, 1.1, 2.1, lakh(ixm.fy2526), "passengers in FY 2025-26", `${(ixm.index_vs_1819 - 100).toFixed(1)}% vs FY18-19 peak`, MAROON);
  stat(s, 2.75, 1.1, 2.1, `+${(d.india.index_vs_1819 - 100).toFixed(1)}%`, "all-India growth, same period", "FY18-19 to FY25-26");
  stat(s, 5.0, 1.1, 2.1, `#${ixm.rank_1819} → #${ixm.rank_2526}`, "Madurai's national rank", "by passengers");
  stat(s, 7.25, 1.1, 2.25, `−${fmt(d.intl_lost_mar_jul_2026)}`, "international passengers lost", "Mar–Jul 2026 vs 2025 (Gulf suspension)");
  bullets(s, [
    `Madurai is the only airport in its peer group still below its pre-COVID peak; Trichy grew ${trz.index_vs_1819 - 100 > 0 ? "+" : ""}${(trz.index_vs_1819 - 100).toFixed(1)}% and now carries ${(trz.fy2526 / ixm.fy2526).toFixed(1)}× Madurai's traffic.`,
    `Had Madurai grown like India since FY18-19 it would handle about ${lakh(ixm.fy1819 * d.india.fy2526 / d.india.fy1819)} passengers a year – roughly ${lakh(d.gap_vs_india)} more than today.`,
    `The constraint is airline capacity and connectivity, not the terminal (about ${Math.round(100 * ixm.fy2526 / 2900000)}% of its 2.9 million rated capacity in use).`,
    "Priorities: restore and widen Gulf links, use the new international status to bring in foreign airlines, upgauge Chennai/Bengaluru from turboprops, use night slots, attract a second airline.",
  ], 0.5, 2.85, 9.0, 2.05, 12);
}

// 3 ---------------------------------------------------------------- data & verification
{
  const s = slide("What this analysis is built on – and how it was checked");
  const cols = [
    ["AAI official traffic", [`${d.aai_months} monthly reports, ${mlab(d.aai_range[0])} – ${mlab(d.aai_range[1])}`,
      "Passengers (domestic/international), aircraft movements, cargo tonnes",
      `${d.verified_fy.length} complete financial years (${d.verified_fy[0]} to ${d.verified_fy[d.verified_fy.length - 1]}) add up exactly to AAI's published annual totals`,
      `Not published / not found: ${d.aai_missing.join(", ")}`]],
    ["AeroDataBox flight records", [`${d.flight_days} days of individual flights (airline, route, aircraft, times)`,
      ...d.flight_validation.filter((v) => v.aai_movements).map((v) => `${mlab(v.month)}: ${fmt(v.aerodatabox_movements)} flights vs ${fmt(v.aai_movements)} AAI movements (${v.coverage_pct}%)`),
      "Only months with complete daily data are used for network analysis"]],
    ["Published context", ["Peer airports & all-India totals: AAI figures via Wikipedia", "Infrastructure & policy: Ministry replies, news reports (dated, listed in the Excel)",
      "Scenarios are what-if paths, not forecasts"]],
  ];
  cols.forEach(([h, lines], i) => {
    const x = 0.5 + i * 3.05; card(s, x, 1.1, 2.9, 3.75);
    s.addText(h, { x: x + 0.15, y: 1.2, w: 2.6, h: 0.4, fontSize: 13, bold: true, color: [MAROON, TEAL, INDIGO][i], fontFace: FONT_H, isTextBox: true });
    bullets(s, lines, x + 0.12, 1.62, 2.66, 3.15, 10.5);
  });
}

// 4 ---------------------------------------------------------------- 10 years of passengers
{
  const s = slide("Ten years of passengers: a pre-COVID peak not yet regained", AAI);
  const labels = FY.map((f) => f.fy + (f.months < 12 ? "*" : ""));
  s.addChart(pres.charts.BAR, [
    { name: "Domestic", labels, values: FY.map((f) => f.pax_dom || 0) },
    { name: "International", labels, values: FY.map((f) => f.pax_intl || 0) },
  ], { x: 0.4, y: 1.05, w: 6.3, h: 3.85, barDir: "col", barGrouping: "stacked", chartColors: [MAROON, GOLD], showLegend: true, legendPos: "b", ...axis() });
  const f1819 = fy("2018-19"), f2021 = fy("2020-21"), f2425 = fy("2024-25"), f2526 = fy("2025-26");
  side(s, [
    `Peak: ${fmt(f1819.pax_total)} in FY 2018-19`,
    `COVID low: ${fmt(f2021.pax_total)} in FY 2020-21 (${Math.round(100 * f2021.pax_total / f1819.pax_total)}% of peak)`,
    `Best since: ${fmt(f2425.pax_total)} in FY 2024-25 (${Math.round(100 * f2425.pax_total / f1819.pax_total)}% of peak)`,
    `FY 2025-26: ${fmt(ixm.fy2526)} (published total; −0.8%)`,
    "* partial year: FY16-17 (Oct 2016 missing), FY25-26 (Nov 2025 missing), FY26-27 (Apr–Sep)",
  ]);
}

// 5 ---------------------------------------------------------------- vs India & peers
{
  const s = slide("Peers grew past pre-COVID levels – Madurai did not", PEER_SRC);
  const rows = [...peers.map((p) => ({ n: p.airport.replace(/ \(.*/, ""), v: p.index_vs_1819 })), { n: "All India", v: d.india.index_vs_1819 }]
    .sort((a, b) => b.v - a.v);
  s.addChart(pres.charts.BAR, [{ name: "FY25-26 traffic (FY18-19 = 100)", labels: rows.map((r) => r.n), values: rows.map((r) => r.v) }],
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, barDir: "bar", catAxisOrientation: "maxMin", showLegend: false, showValue: true, dataLabelPosition: "outEnd",
      dataLabelFormatCode: "0.0", chartColors: [TEAL], ...axis(), valAxisMaxVal: 160 });
  side(s, [
    "Index: FY 2025-26 passengers as % of FY 2018-19 (last full pre-COVID year)",
    `Madurai ${ixm.index_vs_1819} – the only one below 100`,
    `All India ${d.india.index_vs_1819}; Trichy ${trz.index_vs_1819}`,
    `Madurai's annual change: ${ixm.cagr_1819_2526}% a year vs India +${d.india.cagr_1819_2526}%`,
  ]);
}

// 6 ---------------------------------------------------------------- ranks
{
  const s = slide("Falling down the national table", PEER_SRC);
  const head = ["Airport", "FY 2018-19", "FY 2025-26", "Change", "Rank 18-19", "Rank 25-26"].map((t) => ({ text: t, options: { bold: true, color: WHITE, fill: { color: INK } } }));
  const body = [...peers].sort((a, b) => b.fy2526 - a.fy2526).map((p) => {
    const hl = p.airport.startsWith("Madurai");
    const o = hl ? { bold: true, color: MAROON } : {};
    return [p.airport, fmt(p.fy1819), fmt(p.fy2526), `${p.index_vs_1819 >= 100 ? "+" : ""}${(p.index_vs_1819 - 100).toFixed(1)}%`, `#${p.rank_1819}`, `#${p.rank_2526}`]
      .map((t) => ({ text: t, options: o }));
  });
  s.addTable([head, ...body], { x: 0.5, y: 1.1, w: 9, colW: [2.6, 1.35, 1.35, 1.1, 1.3, 1.3], fontSize: 11.5, fontFace: FONT_B, color: INK,
    border: { type: "solid", pt: 0.5, color: GRID }, rowH: 0.36 });
  bullets(s, [`In FY 2018-19 Madurai (${fmt(ixm.fy1819)}) and Trichy (${fmt(trz.fy1819)}) were neck and neck; by FY 2025-26 Trichy handled ${fmt(trz.fy2526 - ixm.fy2526)} more passengers a year.`],
    0.5, 4.0, 9, 0.8, 12);
}

// 7 ---------------------------------------------------------------- monthly trend
{
  const s = slide("Month by month since 2016", AAI);
  const m = d.monthly;
  const ylab = m.map((r) => r.month.slice(0, 4));
  s.addChart(pres.charts.LINE, [{ name: "Passengers", labels: ylab, values: m.map((r) => r.pax_total) },
    { name: "International", labels: ylab, values: m.map((r) => r.pax_intl || 0) }],
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, chartColors: [MAROON, GOLD], lineSize: 1.75, lineDataSymbol: "none", showLegend: true, legendPos: "b",
      ...axis(), catAxisLabelFrequency: 12, catAxisLabelRotate: 0 });
  const best = m.reduce((a, b) => (b.pax_total > a.pax_total ? b : a));
  side(s, [
    `Busiest month on record: ${mlab(best.month)} (${fmt(best.pax_total)})`,
    "Mar 2020 – mid 2022: COVID collapse and slow recovery",
    "From Mar 2026: Gulf flights suspended – international traffic drops to a fraction",
    `Latest: ${mlab(m[m.length - 1].month)} ${fmt(m[m.length - 1].pax_total)} passengers`,
  ]);
}

// 8 ---------------------------------------------------------------- seasonality
{
  const s = slide("A festival and holiday rhythm airlines can plan around", AAI + " (seasonal model, COVID months excluded)");
  s.addChart(pres.charts.BAR, [{ name: "Seasonal index", labels: d.season.map((x) => x.name), values: d.season.map((x) => x.index) }],
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, barDir: "col", chartColors: [GOLD], showLegend: false, showValue: true, dataLabelPosition: "outEnd",
      dataLabelFormatCode: "0.00", ...axis(), valAxisMinVal: 0.8, valAxisMaxVal: 1.15, valAxisLabelFormatCode: "0.00" });
  const srt = [...d.season].sort((a, b) => b.index - a.index);
  side(s, [
    "1.00 = an average month",
    `Peaks: ${srt.slice(0, 3).map((x) => `${x.name} ${x.index.toFixed(2)}`).join(", ")} – Pongal, Dec holidays/Sabarimala, summer holidays`,
    `Lows: ${srt.slice(-2).map((x) => `${x.name} ${x.index.toFixed(2)}`).join(", ")}`,
    "Peak months run about 15–20% above the quietest – a case for seasonal extra flights",
  ]);
}

// 9 ---------------------------------------------------------------- international over 10 years
{
  const s = slide("International travel: once a quarter of all passengers", AAI);
  const labels = FY.map((f) => f.fy + (f.months < 12 ? "*" : ""));
  s.addChart(pres.charts.BAR, [{ name: "International passengers", labels, values: FY.map((f) => f.pax_intl || 0) }],
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, barDir: "col", chartColors: [GOLD], showLegend: false, ...axis() });
  side(s, [
    `International share: ${fy("2019-20").intl_share}% in FY19-20 → ${fy("2024-25").intl_share}% in FY24-25 → ${fy("2025-26").intl_share}% in FY25-26*`,
    `Peak international year: FY 2019-20 (${fmt(fy("2019-20").pax_intl)})`,
    `FY 2024-25: ${fmt(fy("2024-25").pax_intl)} – still ${Math.round(100 - 100 * fy("2024-25").pax_intl / fy("2019-20").pax_intl)}% below peak`,
    "Madurai serves a large Gulf & South-East Asian diaspora market – the biggest growth lever",
  ]);
}

// 10 ---------------------------------------------------------------- 2026 shock
{
  const s = slide("2026: the Gulf suspension – and a weak domestic first half", AAI + "; DT Next, 26 Jun 2026");
  const x = d.intl_2026; const labels = x.map((r) => MON[+r.month.slice(5) - 1]);
  s.addChart(pres.charts.BAR, [{ name: "International 2025", labels, values: x.map((r) => r.intl_2025) },
    { name: "International 2026", labels, values: x.map((r) => r.intl_2026) }],
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, barDir: "col", barGrouping: "clustered", chartColors: [PALE, MAROON], showLegend: true, legendPos: "b", ...axis() });
  const dom = x.filter((r) => r.month <= "2026-06");
  side(s, [
    "Dubai & Abu Dhabi flights suspended from end-Feb 2026 (Gulf conflict); resumption from 14 Aug",
    `Mar–Jul 2026: about ${fmt(d.intl_lost_mar_jul_2026)} fewer international passengers than a year earlier`,
    `Domestic was also down ${Math.abs(Math.max(...dom.map((r) => r.dom_change_pct)))}–${Math.abs(Math.min(...dom.map((r) => r.dom_change_pct)))}% year on year in Jan–Jun 2026`,
    `Recovery: domestic ${x[x.length - 1].dom_change_pct > 0 ? "+" : ""}${x[x.length - 1].dom_change_pct}% and international ${x[x.length - 1].change_pct}% in ${mlab(x[x.length - 1].month)}`,
  ], 6.85, 1.15, 2.65, 3.7, 11);
}

// 11 ---------------------------------------------------------------- movements & aircraft size
{
  const s = slide("Fewer flights, fuller flights", AAI);
  const rows = FY.filter((f) => f.mov_total && f.mov_months === f.months);
  const labels = rows.map((f) => f.fy + (f.months < 12 ? "*" : ""));
  s.addChart(pres.charts.BAR, [{ name: "Aircraft movements", labels, values: rows.map((f) => f.mov_total) }],
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, barDir: "col", chartColors: [INDIGO], showLegend: false, ...axis() });
  const ppm = rows.filter((f) => f.pax_per_mov);
  side(s, [
    `Movements peaked at ${fmt(fy("2019-20").mov_total)} in FY19-20; ${fmt(fy("2024-25").mov_total)} in FY24-25`,
    `Passengers per movement: ${ppm.slice(-4).map((f) => `FY${f.fy.slice(2)}: ${f.pax_per_mov}`).join(", ")} (FY19-20: ${fy("2019-20").pax_per_mov})`,
    "Airlines carry similar volumes with fewer, larger aircraft – frequency (choice of times) has fallen",
  ]);
}

// 12 ---------------------------------------------------------------- cargo
{
  const s = slide("Air cargo: climbing back towards its 2018-19 peak", AAI);
  const rows = d.cargo_fy.filter((c) => c.tonnes !== null);
  const labels = rows.map((c) => c.fy + (c.months < 12 ? "*" : ""));
  s.addChart(pres.charts.BAR, [{ name: "Cargo (tonnes)", labels, values: rows.map((c) => c.tonnes) }],
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, barDir: "col", chartColors: [TEAL], showLegend: false, ...axis() });
  side(s, [
    `Cargo operations began in Dec 2017 and peaked at ${fmt(fy("2018-19").frt_total)} t in FY 2018-19 (confirmed by AAI's revised figures)`,
    `FY 2024-25: ${fmt(fy("2024-25").frt_total)} t; FY 2025-26: ${fmt(fy("2025-26").frt_total)} t in 11 months`,
    `FY 2026-27 so far: ${fmt(fy("2026-27").frt_total)} t in ${fy("2026-27").frt_months} months`,
    "Cargo is growing while passengers stagnate – most travels in passenger-aircraft holds, so more and larger flights also lift cargo",
  ]);
}

// 13 ---------------------------------------------------------------- network
{
  const s = slide("The network today: few destinations, one dominant airline", ADB);
  const head = ["Destination", ...nmonths.map((m) => `Dep/week ${mlab(m)}`), `Airlines (${mlab(d.ref_month)})`]
    .map((t) => ({ text: t, options: { bold: true, color: WHITE, fill: { color: INK } } }));
  const iatas = [...new Set(nmonths.flatMap((m) => d.network[m].routes.map((r) => r.iata)))];
  const name = (i) => (nmonths.map((m) => d.network[m].routes.find((r) => r.iata === i)).find(Boolean) || {}).city || i;
  const body = iatas.map((i) => [name(i) + (nmonths.some((m) => (d.network[m].routes.find((r) => r.iata === i) || {}).international) ? " ✈" : ""),
    ...nmonths.map((m) => { const r = d.network[m].routes.find((x) => x.iata === i); return r ? String(r.weekly_departures) : "–"; }),
    ((d.network[d.ref_month].routes.find((r) => r.iata === i) || {}).airlines || []).join(", ") || "suspended"]);
  s.addTable([head, ...body], { x: 0.5, y: 1.05, w: 9, colW: [2.1, ...nmonths.map(() => 1.35), 9 - 2.1 - 1.35 * nmonths.length],
    fontSize: 10.5, fontFace: FONT_B, color: INK, border: { type: "solid", pt: 0.5, color: GRID }, rowH: 0.3 });
  s.addText("✈ international. Departures per week averaged over the month; return flights not counted twice.",
    { x: 0.5, y: 4.6, w: 9, h: 0.3, fontSize: 9.5, color: MUTED, fontFace: FONT_B, isTextBox: true });
}

// 14 ---------------------------------------------------------------- concentration & fleet
{
  const s = slide("Turboprops on busy routes, one airline dominates", ADB);
  const labs = nmonths.map(mlab);
  const atr = (i) => nmonths.map((m) => (d.network[m].routes.find((r) => r.iata === i) || {}).atr_share_pct || 0);
  s.addChart(pres.charts.BAR, [{ name: "Chennai", labels: labs, values: atr("MAA") }, { name: "Bengaluru", labels: labs, values: atr("BLR") }],
    { x: 0.4, y: 1.05, w: 4.5, h: 3.8, barDir: "col", barGrouping: "clustered", chartColors: [MAROON, GOLD], showLegend: true, legendPos: "b",
      showValue: true, dataLabelPosition: "outEnd", ...axis(), valAxisMaxVal: 110, showTitle: true, title: "% of flights on 78-seat ATR 72" });
  const igo = nmonths.map((m) => (d.network[m].airlines.find((a) => a.airline === "IndiGo") || {}).share_pct || 0);
  s.addChart(pres.charts.BAR, [{ name: "IndiGo share of movements %", labels: labs, values: igo }],
    { x: 5.1, y: 1.05, w: 4.4, h: 3.8, barDir: "col", chartColors: [INDIGO], showLegend: false, showValue: true, dataLabelPosition: "outEnd",
      dataLabelFormatCode: "0.0", ...axis(), valAxisMaxVal: 110, showTitle: true, title: "IndiGo share of all movements, %" });
}

// 15 ---------------------------------------------------------------- daily profile
{
  const nm = nmonths[0]; const h = d.network[nm].hourly;
  const s = slide("Daytime only: no scheduled flights 22:00–06:00", ADB);
  s.addChart(pres.charts.BAR, [{ name: "Movements", labels: h.map((_, i) => String(i).padStart(2, "0")), values: h }],
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, barDir: "col", chartColors: [MAROON], showLegend: false, ...axis(), showTitle: true,
      title: `Scheduled movements by hour (local), ${mlab(nm)}` });
  side(s, [
    "24-hour operations started in Oct 2024 (reported)",
    `Night movements (22:00–06:00): ${nmonths.map((m) => `${mlab(m)} ${d.network[m].night_movements}`).join(", ")}`,
    "Gulf and South-East Asian carriers typically schedule late-evening and night departures – unused night capacity is an opportunity",
  ]);
}

// 16 ---------------------------------------------------------------- infrastructure
{
  const s = slide("Infrastructure: terminal headroom, runway limits", "Swarajya 22 Aug 2025; Wikipedia 'Madurai Airport'; Mysuru Infra Hub 5 Oct 2024");
  stat(s, 0.5, 1.1, 2.15, `${Math.round(100 * ixm.fy2526 / 2900000)}%`, "terminal capacity used", "1.39M of 2.9M passengers a year", MAROON);
  stat(s, 2.8, 1.1, 2.15, "2,285 m", "runway today", "3,810 m planned (wide-body)");
  stat(s, 5.1, 1.1, 2.15, "543 / 653", "acres handed over", "Aug 2025 – no completion date");
  stat(s, 7.4, 1.1, 2.1, "Mar 2026", "international airport status", "Union Cabinet approval");
  bullets(s, [
    "The terminal is not the bottleneck this decade: even the fastest what-if path (slide 17) reaches about " + `${scen[scen.length - 1].terminal_use_pct}% of capacity by FY 2030-31.`,
    "The runway is: wide-body aircraft (A330/B777) need the 3,810 m extension – essential for long-haul and heavy cargo.",
    "Madurai has been outside bilateral air service agreements, which kept foreign airlines away – the new international status is the moment to change this.",
  ], 0.5, 2.85, 9, 2.0, 12);
}

// 17 ---------------------------------------------------------------- outlook
{
  const s = slide("Outlook: decisions, not destiny", AAI + "; scenario growth rates from AAI annual figures");
  const labels = scen[0].path.map((p) => p.fy);
  s.addChart(pres.charts.LINE, scen.map((x) => ({ name: `${x.name} (${x.cagr_pct > 0 ? "+" : ""}${x.cagr_pct}%/yr)`, labels, values: x.path.map((p) => p.passengers) })),
    { x: 0.4, y: 1.05, w: 6.3, h: 3.85, chartColors: [PALE, TEAL, MAROON], lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 5,
      showLegend: true, legendPos: "b", ...axis(), valAxisMinVal: 1000000 });
  const fc = d.forecast;
  side(s, [
    "What-if paths from the FY 2025-26 published total, using growth rates actually observed FY18-19→FY25-26:",
    ...scen.map((x) => `${x.name}: ${lakh(x.fy2030_31)} by FY 2030-31`),
    fc.available ? `Statistical 12-month forecast (Oct 26–Sep 27): about ${lakh(fc.points.reduce((t, p) => t + p.forecast, 0))} (backtest error ${fc.backtest_mape_pct}%)` : "",
  ].filter(Boolean), 6.85, 1.15, 2.65, 3.7, 10.5);
}

// 18-19 ---------------------------------------------------------------- recommendations
const recs = d.recommendations;
[[0, 3, "What Madurai should ask for (1/3)"], [3, 6, "What Madurai should ask for (2/3)"], [6, 9, "What Madurai should ask for (3/3)"]].forEach(([a, b, title]) => {
  const s = slide(title, "Evidence computed from AAI and AeroDataBox data in this review; context sources listed in the Excel workbook");
  const head = ["#", "Ask", "Evidence", "To whom", "Priority"].map((t) => ({ text: t, options: { bold: true, color: WHITE, fill: { color: INK } } }));
  const body = recs.slice(a, b).map((r) => [String(r[0]), r[1], r[2], r[3], r[4]].map((t, i) => ({ text: t,
    options: i === 4 ? { bold: true, color: r[4] === "High" ? MAROON : r[4] === "Medium" ? SAFFRON : MUTED } : i === 1 ? { bold: true } : {} })));
  s.addTable([head, ...body], { x: 0.4, y: 1.0, w: 9.2, colW: [0.35, 2.45, 3.9, 1.7, 0.8], fontSize: 11, fontFace: FONT_B, color: INK,
    border: { type: "solid", pt: 0.5, color: GRID }, valign: "top" });
});

// 20 ---------------------------------------------------------------- opportunities
{
  const s = slide("Opportunities to create");
  const ops = [
    ["Diaspora corridors", "Gulf, Singapore, Malaysia and Sri Lanka routes – international was 21–25% of traffic before COVID (AAI). Target: restore and exceed FY19-20's " + fmt(fy("2019-20").pax_intl) + " international passengers."],
    ["Heritage & pilgrim gateway", "Meenakshi Amman Temple, Rameswaram and Kodaikanal are within reach; Dec–Jan peaks (Pongal, Sabarimala season) support seasonal and charter flights. (Qualitative – no visitor data in this review.)"],
    ["Air cargo from the south", "Cargo grew while passengers stalled. International status plus customs and cold-chain facilities can serve agricultural and regional exporters."],
    ["Night slots & based aircraft", "Zero scheduled night movements despite 24-hour operations. An airline basing aircraft overnight in Madurai enables early departures and late returns."],
  ];
  ops.forEach(([h, t], i) => {
    const x = 0.5 + (i % 2) * 4.55, y = 1.05 + Math.floor(i / 2) * 1.92;
    card(s, x, y, 4.4, 1.78);
    s.addText(h, { x: x + 0.18, y: y + 0.1, w: 4.0, h: 0.4, fontSize: 14, bold: true, color: [MAROON, GOLD, TEAL, INDIGO][i], fontFace: FONT_H, isTextBox: true });
    s.addText(t, { x: x + 0.18, y: y + 0.5, w: 4.05, h: 1.2, fontSize: 12, color: INK, fontFace: FONT_B, valign: "top", isTextBox: true });
  });
}

// 21 ---------------------------------------------------------------- next steps & limits
{
  const s = pres.addSlide(); s.background = { color: INK };
  s.addText("Next steps and limits of this review", { x: 0.5, y: 0.35, w: 9, h: 0.6, fontSize: 24, bold: true, color: WHITE, fontFace: FONT_H, isTextBox: true });
  bullets(s, [
    "Share this evidence with AAI Madurai, the Ministry of Civil Aviation, the State Government and airlines; track progress monthly on the IXM Pulse dashboard.",
    "Ask DGCA/AAI for route-level origin–destination data – it would turn route proposals from hypotheses into business cases.",
    `Limits: AAI months ${d.aai_missing.join(" and ")} not available; flight-level detail covers ${d.flight_days} days (AeroDataBox keeps 365 days of history); peer figures are AAI totals via Wikipedia.`,
    "Scenarios are illustrative what-ifs using observed growth rates; the 12-month forecast is a statistical model, not an official projection.",
    "Dashboard: jarunprasath.github.io/madurai-airport-tracker · Contact: linkedin.com/in/arunprasathj",
  ], 0.5, 1.15, 9, 3.8, 13, "E5E7EB");
}

pres.writeFile({ fileName: outPath }).then(() => console.log(`wrote ${outPath}`));

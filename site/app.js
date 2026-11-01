/* IXM Pulse dashboard – reads the JSON files in ./data built by `python -m ixm build`. */
(() => {
  "use strict";
  const REPO = "jarunprasath/madurai-airport-tracker";
  const AIRPORT = { lat: 9.8336, lon: 78.0894 };
  const BBOX = { lamin: 9.3, lamax: 10.4, lomin: 77.5, lomax: 78.7 };
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  // Categorical palette (validated for colour-vision deficiency, light and dark): kumkum, marigold,
  // peacock teal, saffron, indigo, leaf, plum. Fixed order - colour follows the series, never its rank.
  const SERIES = () => [1, 2, 3, 4, 5, 6, 7].map((i) => css(`--s${i}`));
  const C = () => { const s = SERIES(); return { maroon: s[0], gold: s[1], teal: s[2], saffron: s[3], indigo: s[4],
    ink: css("--ink"), muted: css("--muted"), line: css("--line"), card: css("--card") }; };
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monthLabel = (ym) => `${MON[+ym.slice(5, 7) - 1]} ${ym.slice(2, 4)}`;          // "Jan 26"
  const dayLabel = (d) => `${+d.slice(8, 10)} ${MON[+d.slice(5, 7) - 1]}`;            // "5 Nov"
  const niceDate = (d) => (d ? `${+d.slice(8, 10)} ${MON[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}` : "–");
  const alpha = (hex, a) => { const h = hex.replace("#", ""); const n = parseInt(h.length === 3 ? h.replace(/./g, "$&$&") : h, 16);
    return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };
  // Continuous axes: every day / month between first and last appears, missing ones as gaps
  function fillDays(rows) {
    if (!rows.length) return rows;
    const by = Object.fromEntries(rows.map((r) => [r.date, r])); const out = [];
    for (let t = Date.parse(rows[0].date + "T00:00:00Z"), end = Date.parse(rows[rows.length - 1].date + "T00:00:00Z"); t <= end; t += 864e5) {
      const k = new Date(t).toISOString().slice(0, 10); out.push(by[k] || { date: k, missing: true });
    }
    return out;
  }
  // Regular tick labels: months -> quarter starts (or Januaries on long spans); days -> 1st/8th/15th/22nd (or 1st only)
  const monthTicks = (labels) => ({ autoSkip: false, maxRotation: 0, callback: (v, i) => {
    const ym = labels[i]; const mo = +ym.slice(5, 7);
    const narrow = window.innerWidth < 640;
    const every = labels.length > 48 ? 12 : labels.length > 18 ? (narrow ? 6 : 3) : labels.length > 9 ? (narrow ? 3 : 1) : 1;
    return (mo - 1) % every === 0 ? (every === 12 ? ym.slice(0, 4) : monthLabel(ym)) : ""; } });
  const dayTicks = (dates) => ({ autoSkip: false, maxRotation: 0, callback: (v, i) => {
    const day = +dates[i].slice(8, 10);
    if (dates.length > 62) return day === 1 ? `${MON[+dates[i].slice(5, 7) - 1]}${dates[i].slice(5, 7) === "01" ? " " + dates[i].slice(2, 4) : ""}` : "";
    return [1, 8, 15, 22].includes(day) ? dayLabel(dates[i]) : ""; } });
  const nf = new Intl.NumberFormat("en-IN");
  const fmt = (v) => (v === null || v === undefined || Number.isNaN(v) ? "–" : nf.format(Math.round(v)));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (id) => document.getElementById(id);
  const charts = {};

  async function get(name) {
    try {
      const r = await fetch(`data/${name}?v=${Date.now() >> 16}`);
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (e) { return null; }
  }

  function table(el, cols, rows, empty) {
    if (!rows || !rows.length) { el.innerHTML = `<tr><td class="empty">${esc(empty || "No data yet.")}</td></tr>`; return; }
    el.innerHTML = `<thead><tr>${cols.map((c) => `<th class="${c.num ? "num" : ""}">${esc(c.h)}</th>`).join("")}</tr></thead>` +
      `<tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.html ? c.f(r) : esc(c.f(r))}</td>`).join("")}</tr>`).join("")}</tbody>`;
  }

  function chart(id, config) {
    if (charts[id]) charts[id].destroy();
    const c = C();
    const D = Chart.defaults;
    D.color = c.muted; D.borderColor = c.line;
    D.font.family = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"; D.font.size = 11.5;
    D.elements.bar.borderRadius = 4; D.elements.bar.borderSkipped = "start";
    D.elements.line.borderWidth = 2.25; D.elements.line.tension = 0.32;
    D.elements.point.radius = 0; D.elements.point.hoverRadius = 5; D.elements.point.hitRadius = 10;
    D.elements.arc.borderColor = c.card; D.elements.arc.borderWidth = 2;
    D.plugins.legend.labels.usePointStyle = true; D.plugins.legend.labels.pointStyle = "rectRounded"; D.plugins.legend.labels.boxWidth = 10;
    Object.assign(D.plugins.tooltip, { backgroundColor: c.card, titleColor: c.ink, bodyColor: c.ink, borderColor: c.line,
      borderWidth: 1, padding: 10, cornerRadius: 10, boxPadding: 4, usePointStyle: true });
    D.plugins.tooltip.callbacks.label = (t) => {
      const v = typeof t.parsed === "number" ? t.parsed : (t.chart.options.indexAxis === "y" ? t.parsed.x : t.parsed.y);
      return v === null || v === undefined ? null : ` ${t.dataset.label || t.label}: ${fmt(v)}`; };
    const o = config.options || {};
    o.responsive = true; o.maintainAspectRatio = false;
    o.interaction = o.interaction || { mode: config.type === "doughnut" ? "nearest" : "index", intersect: config.type === "doughnut" };
    if (config.type !== "doughnut") {
      o.scales = o.scales || {};
      for (const ax of ["x", "y"]) {
        const sc = (o.scales[ax] = o.scales[ax] || {});
        const valueAxis = (ax === "y") !== (o.indexAxis === "y");
        sc.border = { display: false };
        sc.grid = Object.assign(valueAxis ? { color: alpha(c.muted.startsWith("#") ? c.muted : "#888888", 0.18), drawTicks: false } : { display: false }, sc.grid || {});
        if (valueAxis) { sc.beginAtZero = true; sc.ticks = Object.assign({ padding: 6, precision: 0, maxTicksLimit: 6, callback: (v) => fmt(v) }, sc.ticks || {}); }
      }
    }
    config.options = o;
    // stacked bar segments get a 1px gap in the card colour
    const n = (config.data.labels || []).length;
    if (config.type === "bar") for (const ds of config.data.datasets) {
      if (ds.stack && n <= 60) { ds.borderColor = c.card; ds.borderWidth = { top: 1.5 }; }
      if (n > 60) { ds.borderRadius = 1; ds.barPercentage = 1; ds.categoryPercentage = 0.92; }
    }
    charts[id] = new Chart($(id), config);
  }
  const noData = (id, msg) => {
    const cv = $(id); const ctx = cv.getContext("2d");
    if (charts[id]) { charts[id].destroy(); delete charts[id]; }
    cv.width = cv.clientWidth; cv.height = cv.clientHeight;
    ctx.fillStyle = C().muted; ctx.font = "14px system-ui"; ctx.textAlign = "center";
    ctx.fillText(msg, cv.width / 2, cv.height / 2);
  };

  // ---------------------------------------------------------------- tabs
  const tabs = document.querySelectorAll(".tabs button");
  function show(name) {
    tabs.forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name ? "true" : "false"));
    document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${name}`));
    if (name === "live" && map) setTimeout(() => map.invalidateSize(), 50);
    history.replaceState(null, "", `#${name}`);
  }
  tabs.forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));

  // ---------------------------------------------------------------- live map
  let map, layer;
  function initMap() {
    map = L.map("map", { zoomControl: true }).setView([AIRPORT.lat, AIRPORT.lon], 9);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 13,
      attribution: "© OpenStreetMap contributors" }).addTo(map);
    L.circleMarker([AIRPORT.lat, AIRPORT.lon], { radius: 7, color: C().maroon, fillOpacity: 0.9 })
      .addTo(map).bindTooltip("Madurai Airport (IXM)", { permanent: false });
    layer = L.layerGroup().addTo(map);
  }
  const AIRLINES = { IGO: "IndiGo", SEJ: "SpiceJet", AIC: "Air India", AXB: "Air India Express", ALK: "SriLankan",
    FDB: "flydubai", AKJ: "Akasa Air", BDA: "Blue Dart", QJT: "Quikjet", IAD: "AirAsia India" };
  function haversine(a, b, c, d) {
    const R = 6371, r = Math.PI / 180, x = Math.sin((c - a) * r / 2) ** 2 +
      Math.cos(a * r) * Math.cos(c * r) * Math.sin((d - b) * r / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
  }
  function fromOpenSky(js) {
    return (js.states || []).filter((s) => s[5] !== null && s[6] !== null).map((s) => {
      const cs = (s[1] || "").trim(), alt = s[7] ?? s[13], vr = s[11] || 0;
      const phase = s[8] ? "on ground" : alt !== null && alt < 3000 && vr < -1 ? "approaching" : alt !== null && alt < 3000 && vr > 1 ? "departing" : "overflying";
      return { callsign: cs, airline: AIRLINES[cs.slice(0, 3)] || cs.slice(0, 3) || "–", lat: s[6], lon: s[5],
        alt_m: alt === null ? null : Math.round(alt), speed_kmh: s[9] === null ? null : Math.round(s[9] * 3.6),
        track: s[10], phase, distance_km: Math.round(haversine(AIRPORT.lat, AIRPORT.lon, s[6], s[5]) * 10) / 10 };
    }).sort((a, b) => a.distance_km - b.distance_km);
  }
  async function loadLive() {
    let aircraft = null, label = "";
    try { // direct browser query (works when OpenSky allows cross-origin requests)
      const q = new URLSearchParams(BBOX).toString();
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 8000);
      const r = await fetch(`https://opensky-network.org/api/states/all?${q}`, { signal: ctl.signal });
      clearTimeout(t);
      if (r.ok) { aircraft = fromOpenSky(await r.json()); label = `live · ${new Date().toLocaleTimeString()}`; }
    } catch (e) { /* fall back to snapshot */ }
    if (!aircraft) {
      const snap = await get("live.json");
      aircraft = (snap && snap.aircraft) || [];
      label = snap && snap.generated_utc ? `snapshot · ${new Date(snap.generated_utc * 1000).toLocaleString()}` : "no live data yet";
    }
    $("live-status").textContent = `${aircraft.length} aircraft · ${label}`;
    layer.clearLayers();
    aircraft.forEach((a) => {
      const icon = L.divIcon({ className: "", html: `<div class="plane-icon" style="font-size:24px;transform:rotate(${(a.track || 0) - 45}deg)">✈</div>`,
        iconSize: [26, 26], iconAnchor: [13, 13] });
      L.marker([a.lat, a.lon], { icon }).addTo(layer)
        .bindTooltip(esc(a.callsign || a.airline || "aircraft"), { permanent: true, direction: "right", offset: [10, 0], className: "plane-label" })
        .bindPopup(`<b>${esc(a.callsign || "unknown")}</b><br>${esc(a.airline)}<br>${a.alt_m ?? "–"} m · ${a.speed_kmh ?? "–"} km/h<br>${esc(a.phase)} · ${a.distance_km} km`);
    });
    table($("live-table"), [
      { h: "Call sign", f: (a) => a.callsign || "–" }, { h: "Airline", f: (a) => a.airline },
      { h: "Status", f: (a) => a.phase }, { h: "Altitude m", f: (a) => fmt(a.alt_m), num: true },
      { h: "Speed km/h", f: (a) => fmt(a.speed_kmh), num: true }, { h: "Distance km", f: (a) => a.distance_km, num: true },
    ], aircraft, "No aircraft visible right now within ~60 km of the airport.");
  }

  // ---------------------------------------------------------------- today
  const statusClass = (s) => { s = (s || "").toLowerCase(); return /cancel|divert/.test(s) ? "bad" : /delay/.test(s) ? "warn" : /arrived|departed|landed|approaching|enroute|boarding|checkin|gateclosed/.test(s) ? "ok" : ""; };
  const hhmm = (s) => (s ? s.slice(11, 16) : "");
  let board = [];
  function renderBoard(dir) {
    const rows = board.filter((r) => dir === "all" || r.direction === dir);
    table($("board"), [
      { h: "Time", f: (r) => hhmm(r.sched_local) }, { h: "Exp/Act", f: (r) => hhmm(r.actual_local || r.revised_local) },
      { h: "", f: (r) => (r.direction === "arrival" ? "↓" : "↑") }, { h: "Flight", f: (r) => r.flight_no },
      { h: "Airline", f: (r) => r.airline }, { h: "From / To", f: (r) => `${r.other_city || r.other_name} ${r.other_iata ? "(" + r.other_iata + ")" : ""}` },
      { h: "Aircraft", f: (r) => r.aircraft_model || "–" },
      { h: "Status", html: true, f: (r) => `<span class="st ${statusClass(r.status)}">${esc(r.status || "Scheduled")}</span>${r.is_cargo ? ' <span class="tag">cargo</span>' : ""}` },
    ], rows, "No schedule data for today yet. It appears after the next flight collection run (06:00 and 14:00 IST).");
  }
  document.querySelectorAll("#board-seg button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#board-seg button").forEach((x) => x.classList.toggle("on", x === b));
    renderBoard(b.dataset.dir);
  }));

  // ---------------------------------------------------------------- render all
  async function main() {
    initMap();
    loadLive();
    setInterval(loadLive, 60000);
    $("run-link").href = `https://github.com/${REPO}/actions/workflows/report.yml`;

    const [summary, daily, aaiM, annual, airlines, routes, aircraft, hourly, fc, reports] = await Promise.all([
      get("summary.json"), get("daily.json"), get("aai_monthly.json"), get("aai_annual.json"), get("airlines.json"),
      get("routes.json"), get("aircraft.json"), get("hourly.json"), get("forecast.json"), get("reports.json")]);
    const c = C();

    if (summary) {
      $("updated").textContent = `Updated ${new Date(summary.generated_utc).toLocaleString()}`;
      $("lf-note").textContent = `currently ${Math.round(summary.load_factor.value * 100)}% – ${summary.load_factor.note}`;
      board = summary.board || [];
      const k = summary.kpi, a = summary.latest_aai_month;
      const cards = [
        ["Flights, last 7 days", fmt(k.last7.movements), k.last7.days ? `${fmt(k.last7.movements / k.last7.days)} per day over ${k.last7.days} day${k.last7.days > 1 ? "s" : ""} of data · ${k.last7.international} international` : "no flight data yet"],
        ["Est. passengers, last 7 days", fmt(k.last7.est_pax), "estimate (seats × load factor)"],
        ["Flights, last 30 days", fmt(k.last30.movements), `${k.last30.days || 0} day${k.last30.days === 1 ? "" : "s"} of data · ${k.last30.cargo} cargo · ${k.last30.cancelled} cancelled`],
        a ? [`AAI passengers, ${a.month}`, fmt(a.pax_total), a.pax_yoy_pct !== null ? `${a.pax_yoy_pct > 0 ? "+" : ""}${a.pax_yoy_pct}% year on year` : "official"]
          : ["AAI passengers", "–", "official monthly data not collected yet"],
      ];
      $("kpis").innerHTML = cards.map(([l, v, s]) => `<div class="kpi"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div><div class="s">${esc(s)}</div></div>`).join("");
    } else {
      $("updated").textContent = "Data not built yet";
    }
    renderBoard("all");

    table($("next7"), [{ h: "Date", f: (r) => r.date }, { h: "Flights", f: (r) => r.flights, num: true },
      { h: "Est. passengers", f: (r) => fmt(r.est_pax), num: true }, { h: "International", f: (r) => r.international, num: true },
      { h: "Cargo", f: (r) => r.cargo, num: true }], fc && fc.next7, "No upcoming schedule data yet.");

    // daily
    const allDays = fillDays(daily || []);
    function renderDaily(range) {
      if (!allDays.length) { noData("c-daily", "Daily data appears after the first collection run"); return; }
      const d = range === "all" ? allDays : allDays.slice(-Number(range));
      const dates = d.map((x) => x.date);
      const have = d.filter((x) => !x.missing);
      chart("c-daily", { type: "bar", data: { labels: dates.map(dayLabel), datasets: [
        { label: "Arrivals", data: d.map((x) => x.missing ? null : x.arrivals), backgroundColor: c.maroon, stack: "s" },
        { label: "Departures", data: d.map((x) => x.missing ? null : x.departures), backgroundColor: c.gold, stack: "s" }] },
        options: { scales: { x: { stacked: true, ticks: dayTicks(dates) }, y: { stacked: true } } } });
      $("daily-note").textContent = `${niceDate(dates[0])} – ${niceDate(dates[dates.length - 1])} · ${have.length} of ${d.length} days have flight data` +
        (have.length < d.length ? " (days without data are left blank)" : "");
    }
    document.querySelectorAll("#daily-seg button").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll("#daily-seg button").forEach((x) => x.classList.toggle("on", x === b));
      renderDaily(b.dataset.r);
    }));
    renderDaily("all");

    // AAI monthly
    const am = (aaiM || []).filter((r) => r.pax_total);
    // continuous month axis: missing months become gaps instead of silently joining neighbours
    const fillMonths = (rows) => {
      if (!rows.length) return rows;
      const by = Object.fromEntries(rows.map((r) => [r.month, r])); const out = [];
      let [y, mo] = rows[0].month.split("-").map(Number); const [ey, em] = rows[rows.length - 1].month.split("-").map(Number);
      while (y < ey || (y === ey && mo <= em)) {
        const key = `${y}-${String(mo).padStart(2, "0")}`;
        out.push(by[key] || { month: key, missing: true });
        mo += 1; if (mo === 13) { y += 1; mo = 1; }
      }
      return out;
    };
    if (am.length) {
      const m = fillMonths(am).slice(-36);
      const split = m.every((r) => r.missing || (r.pax_dom !== null && r.pax_intl !== null));
      const months = m.map((r) => r.month);
      chart("c-aai", { type: split ? "bar" : "line", data: { labels: months.map(monthLabel), datasets: split ? [
        { label: "Domestic", data: m.map((r) => r.pax_dom ?? null), backgroundColor: c.maroon, stack: "p" },
        { label: "International", data: m.map((r) => r.pax_intl ?? null), backgroundColor: c.gold, stack: "p" }]
        : [{ label: "Passengers", data: m.map((r) => r.pax_total ?? null), borderColor: c.maroon, backgroundColor: alpha(c.maroon, 0.12), fill: true }] },
        options: { scales: { x: { stacked: split, ticks: monthTicks(months) }, y: { stacked: split } } } });
      const gaps = m.filter((r) => r.missing).map((r) => r.month);
      $("aai-note").textContent = `Source: AAI monthly Traffic News. ${am.length} months collected; latest ${am[am.length - 1].month}.` +
        (gaps.length ? ` Not yet collected: ${gaps.join(", ")} (shown as gaps).` : "");
      const fr = fillMonths(am).slice(-36);
      const hasFr = fr.some((r) => r.frt_total !== null && r.frt_total !== undefined);
      const frMonths = fr.map((r) => r.month);
      if (hasFr) chart("c-freight", { type: "bar", data: { labels: frMonths.map(monthLabel),
        datasets: [{ label: "Cargo (tonnes)", data: fr.map((r) => r.frt_total ?? null), backgroundColor: c.teal }] },
        options: { plugins: { legend: { display: false } }, scales: { x: { ticks: monthTicks(frMonths) } } } });
      else noData("c-freight", "No cargo data yet");
    } else {
      noData("c-aai", "AAI monthly data not collected yet"); noData("c-freight", "No cargo data yet");
      $("aai-note").textContent = "Run the 'AAI monthly' workflow once with a start month to backfill history.";
    }
    table($("aai-table"), [{ h: "Month", f: (r) => r.month }, { h: "Passengers", f: (r) => fmt(r.pax_total), num: true },
      { h: "Domestic", f: (r) => fmt(r.pax_dom), num: true }, { h: "International", f: (r) => fmt(r.pax_intl), num: true },
      { h: "YoY %", f: (r) => (r.pax_yoy_pct === null ? "–" : r.pax_yoy_pct), num: true },
      { h: "Per day", f: (r) => fmt(r.pax_per_day), num: true }, { h: "Movements", f: (r) => fmt(r.mov_total), num: true },
      { h: "Cargo t", f: (r) => (r.frt_total === null ? "–" : r.frt_total), num: true }],
      am.slice().reverse().slice(0, 36), "No AAI monthly data yet.");

    if (annual && annual.length) {
      chart("c-annual", { type: "bar", data: { labels: annual.map((r) => r.fiscal_year),
        datasets: [{ label: "Passengers", data: annual.map((r) => Number(r.passengers)),
          backgroundColor: annual.map((r) => (/2020-21|2021-22/.test(r.fiscal_year) ? alpha(c.maroon, 0.45) : c.maroon)) }] },
        options: { plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: (t) => annual[t.dataIndex].source } } },
          scales: { x: { ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 8, callback: (v, i) => annual[i].fiscal_year.replace(/^20/, "") } } } } });
    } else noData("c-annual", "No annual data");

    // airlines
    const periodText = (pd) => (pd && pd.days ? `${pd.label}: ${niceDate(pd.from)} – ${niceDate(pd.to)} · ${pd.days} day${pd.days > 1 ? "s" : ""} of flight data` : "No flight data in this period yet");
    const setPeriod = (group, pd) => document.querySelectorAll(`[data-period="${group}"]`).forEach((e) => { e.textContent = periodText(pd); });
    function renderAirlines(p) {
      const al = (airlines && airlines[p]) || [], ac = (aircraft && aircraft[p]) || [];
      setPeriod("al", airlines && airlines.periods && airlines.periods[p]);
      if (al.length) chart("c-airlines", { type: "doughnut", data: { labels: al.map((a) => a.airline),
        datasets: [{ data: al.map((a) => a.flights), backgroundColor: al.map((a, i) => SERIES()[Math.min(i, 6)]), hoverOffset: 6 }] },
        options: { cutout: "62%", plugins: { legend: { position: "bottom" },
          tooltip: { callbacks: { label: (t) => ` ${t.label}: ${fmt(t.parsed)} flights (${al[t.dataIndex].share_pct}%)` } } } } });
      else noData("c-airlines", "No airline data yet");
      if (ac.length) chart("c-aircraft", { type: "bar", data: { labels: ac.slice(0, 8).map((a) => a.aircraft),
        datasets: [{ label: "Movements", data: ac.slice(0, 8).map((a) => a.flights), backgroundColor: c.gold, barPercentage: 0.7 }] },
        options: { indexAxis: "y", plugins: { legend: { display: false } } } });
      else noData("c-aircraft", "No aircraft data yet");
      table($("al-table"), [{ h: "Airline", f: (a) => a.airline }, { h: "Code", f: (a) => a.code },
        { h: "Flights", f: (a) => a.flights, num: true }, { h: "Share %", f: (a) => a.share_pct, num: true },
        { h: "Intl", f: (a) => a.international, num: true }, { h: "Cargo", f: (a) => a.cargo, num: true },
        { h: "Est. pax", f: (a) => fmt(a.est_pax), num: true }, { h: "On-time %", f: (a) => a.on_time_pct ?? "–", num: true },
        { h: "Aircraft", f: (a) => a.aircraft }, { h: "Routes", f: (a) => a.routes }], al, "No airline data yet.");
    }
    document.querySelectorAll("#al-seg button").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll("#al-seg button").forEach((x) => x.classList.toggle("on", x === b));
      renderAirlines(b.dataset.p);
    }));
    renderAirlines("last30");

    // routes + hourly
    const rt = (routes && routes.last30) || [];
    setPeriod("rt", routes && routes.periods && routes.periods.last30);
    if (rt.length) chart("c-routes", { type: "bar", data: { labels: rt.slice(0, 12).map((r) => `${r.city || r.iata}${r.international ? " ✈" : ""}`),
      datasets: [{ label: "Movements", data: rt.slice(0, 12).map((r) => r.flights),
        backgroundColor: rt.slice(0, 12).map((r) => (r.international ? c.saffron : c.teal)), barPercentage: 0.7 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } } } });
    else noData("c-routes", "No route data yet");
    const hr = hourly && hourly.last30;
    if (hr && hr.some((x) => x)) chart("c-hourly", { type: "bar", data: { labels: hr.map((_, h) => String(h).padStart(2, "0")),
      datasets: [{ label: "Movements", data: hr, backgroundColor: c.maroon }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { ticks: { autoSkip: false, maxRotation: 0, callback: (v, i) => (i % 3 === 0 ? `${String(i).padStart(2, "0")}:00` : "") } } } } });
    else noData("c-hourly", "No timing data yet");
    table($("rt-table"), [{ h: "Destination", f: (r) => `${r.city || r.iata || "Unknown"}${r.iata && r.city ? ` (${r.iata})` : ""}` }, { h: "Country", f: (r) => r.country || "–" },
      { h: "Flights", f: (r) => r.flights, num: true }, { h: "Per day", f: (r) => r.per_day, num: true },
      { h: "Est. pax", f: (r) => fmt(r.est_pax), num: true }, { h: "Airlines", f: (r) => r.airlines }], rt, "No route data yet.");

    // forecast
    const mf = fc && fc.monthly;
    if (mf && mf.available) {
      const hist = fillMonths(am).slice(-24);
      const months = [...hist.map((r) => r.month), ...mf.points.map((p) => p.month)];
      const pad = (arr, n) => Array(n).fill(null).concat(arr);
      const lastActual = hist.map((r) => r.pax_total ?? null);
      // join forecast to the last actual point so the lines connect
      const join = (arr) => { const a = pad(arr, hist.length); a[hist.length - 1] = lastActual[hist.length - 1]; return a; };
      chart("c-forecast", { type: "line", data: { labels: months.map(monthLabel), datasets: [
        { label: "Actual (AAI)", data: lastActual, borderColor: c.maroon, backgroundColor: alpha(c.maroon, 0.06), fill: true, spanGaps: false },
        { label: "Forecast", data: join(mf.points.map((p) => p.forecast)), borderColor: c.gold, borderDash: [6, 4], backgroundColor: c.gold },
        { label: "80% range", data: join(mf.points.map((p) => p.high)), borderColor: "transparent", backgroundColor: alpha(c.gold, 0.18), fill: "+1" },
        { label: "low", data: join(mf.points.map((p) => p.low)), borderColor: "transparent", fill: false }] },
        options: { plugins: { legend: { labels: { filter: (i) => i.text !== "low" } }, tooltip: { filter: (t) => t.dataset.label !== "low" } },
          scales: { x: { ticks: monthTicks(months) } } } });
      $("fc-note").textContent = `${mf.method}. Trained on ${mf.trained_on}` +
        (mf.interpolated_months && mf.interpolated_months.length ? ` (${mf.interpolated_months.join(", ")} not published yet – filled by interpolation)` : "") +
        `. Backtest error ${mf.backtest_mape_pct ?? "–"}%. Statistical estimate, not an official projection.`;
      table($("fc-table"), [{ h: "Month", f: (p) => p.month }, { h: "Forecast", f: (p) => fmt(p.forecast), num: true },
        { h: "Range (80%)", f: (p) => `${fmt(p.low)} – ${fmt(p.high)}` }, { h: "Season index", f: (p) => p.seasonal_index, num: true },
        { h: "Festivals / season", html: true, f: (p) => p.season.map((s) => `<span class="tag">${esc(s)}</span>`).join("") || "–" }], mf.points);
    } else {
      noData("c-forecast", "Forecast needs 24+ months of AAI data");
      $("fc-note").textContent = mf ? mf.reason : "";
      table($("fc-table"), [], [], "The forecast appears once enough AAI monthly history is collected.");
    }

    // reports
    table($("reports"), [{ h: "Report", f: (r) => r.title }, { h: "Period", f: (r) => r.period },
      { h: "Download", html: true, f: (r) => r.files.map((f) => `<a href="${esc(f.href)}">${esc(f.label)}</a>`).join(" · ") }],
      reports, "No reports generated yet.");

    const want = location.hash.slice(1);
    if (want && document.getElementById(`tab-${want}`)) show(want);
  }
  main();
})();

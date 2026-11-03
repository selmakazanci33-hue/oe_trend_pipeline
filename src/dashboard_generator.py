"""
Renders the self-contained interactive HTML dashboard.

plotly.js is embedded inline so the file opens locally without a web server or
network access. Only aggregated daily counts are embedded — no identifiers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from plotly.offline import get_plotlyjs

logger = logging.getLogger(__name__)


def _safe_json(payload: dict) -> str:
    return json.dumps(payload, default=str).replace("</", "<\\/")


def generate_dashboard(payload: dict, output_file: Path) -> Path:
    html = (
        TEMPLATE.replace("__TITLE__", payload["title"])
        .replace("__PLOTLYJS__", get_plotlyjs())
        .replace("__PAYLOAD__", _safe_json(payload))
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html, encoding="utf-8")
    logger.info("Dashboard written — %s (%.1f MB)", output_file, output_file.stat().st_size / 1e6)
    return output_file


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<script>__PLOTLYJS__</script>
<style>
  :root {
    --navy: #0B2545; --ink: #1d2733; --muted: #5d6b7a; --line: #dde3ea; --bg: #f4f6f9;
    --card: #ffffff; --accent: #13315C; --ok: #1e7b4a; --warn: #b26a00; --bad: #b3261e; --pend: #6b5b95;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: var(--ink); background: var(--bg); }
  header { background: linear-gradient(120deg, var(--navy), var(--accent)); color: #fff; padding: 26px 36px 22px; }
  header h1 { margin: 0; font-size: 26px; font-weight: 600; letter-spacing: .2px; }
  header p { margin: 6px 0 0; opacity: .85; font-size: 15px; }
  header .runmeta { margin-top: 12px; font-size: 12px; opacity: .75; }
  main { padding: 22px 36px 40px; max-width: 1400px; margin: 0 auto; }
  .banner { border-radius: 8px; padding: 12px 16px; margin-bottom: 14px; font-size: 14px; }
  .banner.bad { background: #fdecea; border: 1px solid #f3b8b3; color: var(--bad); }
  .banner.warn { background: #fff4e0; border: 1px solid #f2d29b; color: #7a4a00; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
  .controls { display: grid; grid-template-columns: auto 1fr; gap: 14px 22px; align-items: center; }
  .label { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
  .group { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .sep { width: 1px; height: 26px; background: var(--line); margin: 0 6px; }
  button.metric, button.mode, label.py { font: inherit; font-size: 13px; border: 1px solid #c5ced8; background: #fff; color: var(--ink);
    padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; letter-spacing: .6px; transition: all .12s; }
  button.metric:hover, button.mode:hover, label.py:hover { border-color: var(--accent); }
  button.metric.active, button.mode.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  button.metric.pending.active { background: var(--pend); border-color: var(--pend); }
  button.clear { background: #fff; color: var(--bad); border-color: #e6b3af; }
  .segmented { display: inline-flex; }
  .segmented button { border-radius: 0; margin: 0; }
  .segmented button:first-child { border-radius: 6px 0 0 6px; }
  .segmented button:last-child { border-radius: 0 6px 6px 0; border-left: none; }
  label.py { display: inline-flex; gap: 8px; align-items: center; font-weight: 600; }
  label.py input { accent-color: var(--accent); }
  label.py.disabled { opacity: .55; cursor: not-allowed; background: #f1f3f6; border-style: dashed; }
  .swatch { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
  .badge { display: inline-block; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px; letter-spacing: .4px; white-space: nowrap; }
  .b-MATCHED { background: #e3f4ea; color: var(--ok); }
  .b-EXPLAINED { background: #fff4e0; color: var(--warn); }
  .b-UNEXPLAINED { background: #fdecea; color: var(--bad); }
  .b-PENDING { background: #eeeaf6; color: var(--pend); }
  .kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; margin-bottom: 18px; }
  .kpi { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px; border-top: 4px solid var(--accent); }
  .kpi .k-label { font-size: 12px; color: var(--muted); font-weight: 600; }
  .kpi .k-value { font-size: 28px; font-weight: 700; margin: 4px 0; font-variant-numeric: tabular-nums; }
  .kpi .k-sub { font-size: 12px; color: var(--muted); }
  .chart-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; }
  .chart-head h2 { margin: 0; font-size: 18px; }
  .chart-head .meta { font-size: 12px; color: var(--muted); }
  #chart { width: 100%; height: 480px; }
  .placeholder { height: 480px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--muted); text-align: center; gap: 10px; padding: 0 40px; }
  .placeholder h3 { margin: 0; color: var(--ink); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  th { font-size: 11px; text-transform: uppercase; letter-spacing: .7px; color: var(--muted); background: #f8fafc; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .note { font-size: 12px; color: var(--muted); margin-top: 10px; }
  details { border: 1px solid var(--line); border-radius: 8px; padding: 10px 14px; margin-bottom: 10px; background: #fff; }
  details > summary { cursor: pointer; font-weight: 600; }
  details dl { display: grid; grid-template-columns: 160px 1fr; gap: 6px 14px; margin: 12px 0 4px; font-size: 13px; }
  details dt { color: var(--muted); font-weight: 600; }
  details dd { margin: 0; }
  code { background: #f1f3f6; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
  h2.section { font-size: 16px; margin: 0 0 12px; }
  footer { font-size: 12px; color: var(--muted); padding: 0 36px 30px; max-width: 1400px; margin: 0 auto; }
  a.reset { font-size: 12px; color: var(--accent); cursor: pointer; text-decoration: underline; }
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <p id="subtitle"></p>
  <div class="runmeta" id="runmeta"></div>
</header>
<main>
  <div id="banners"></div>

  <section class="card">
    <div class="controls">
      <div class="label">Plan Year</div>
      <div class="group" id="py-controls"></div>
      <div class="label">Metric</div>
      <div class="group" id="metric-controls"></div>
      <div class="label">View</div>
      <div class="group">
        <div class="segmented">
          <button class="mode active" data-mode="daily">Daily</button>
          <button class="mode" data-mode="cumulative">Cumulative</button>
        </div>
      </div>
    </div>
  </section>

  <div class="kpis" id="kpis"></div>

  <section class="card">
    <div class="chart-head">
      <h2 id="chart-title"></h2>
      <div class="meta" id="chart-meta"></div>
    </div>
    <div id="chart"></div>
    <div id="placeholder" class="placeholder" style="display:none"></div>
  </section>

  <section class="card">
    <div class="chart-head">
      <h2 class="section">Comparison</h2>
      <a class="reset" id="reset-selection" style="display:none">Reset to latest date</a>
    </div>
    <table>
      <thead><tr>
        <th>Plan Year</th><th>Metric</th><th>Selected / Latest Date</th>
        <th style="text-align:right">Daily Count</th><th style="text-align:right">Cumulative Count</th>
        <th>Grain</th><th>Validation Status</th>
      </tr></thead>
      <tbody id="comparison-body"></tbody>
    </table>
    <div class="note">
      Click a point on the chart to select that date for its Plan Year. Year-over-year percentages are not calculated:
      dates in different Plan Years are not aligned until official OE start dates (OE_Day) are confirmed.
    </div>
  </section>

  <section class="card">
    <h2 class="section">Metric Definitions</h2>
    <div id="definitions"></div>
  </section>

  <section class="card">
    <h2 class="section">Plan Year Availability</h2>
    <div id="py-availability"></div>
  </section>

  <section class="card">
    <details>
      <summary>Validation Results (Level 1 totals · Level 2 issuer · Level 3 status category)</summary>
      <div class="note">Control totals are validation references only; displayed values always come from the query output.
      A matched total does not by itself make a metric production-ready.</div>
      <table style="margin-top:10px">
        <thead><tr><th>Metric</th><th>PY</th><th>Level</th><th>Check</th>
          <th style="text-align:right">Expected</th><th style="text-align:right">Actual</th>
          <th style="text-align:right">Difference</th><th>Status</th><th>Note</th></tr></thead>
        <tbody id="validation-body"></tbody>
      </table>
    </details>
  </section>
</main>
<footer>
  Internal Georgia Access POC. Enrollment counts distinct people; Cancellation and Termination count distinct policies —
  they are shown on separate charts and are not directly comparable. Raw row counts are never used as business counts.
</footer>

<script type="application/json" id="payload">__PAYLOAD__</script>
<script>
(function () {
  const P = JSON.parse(document.getElementById("payload").textContent);
  const fmt = n => (n === null || n === undefined || n === "") ? "—" : Number(n).toLocaleString("en-US");
  const fmtDate = s => {
    if (!s) return "—";
    const d = new Date(s + "T00:00:00");
    return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  };
  const el = (tag, attrs = {}, text) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v; else if (k === "style") e.style.cssText = v; else e.setAttribute(k, v);
    }
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const badge = status => {
    const key = (status || "VALIDATION PENDING").split(" ")[0].replace("VALIDATION", "PENDING");
    return el("span", { class: "badge b-" + key }, status || "VALIDATION PENDING");
  };
  const metricByName = Object.fromEntries(P.metrics.map(m => [m.name, m]));

  const state = {
    metric: (P.metrics.find(m => m.has_data) || {}).name || null,
    mode: "daily",
    years: new Set(P.plan_years.filter(p => p.available && p.has_data).map(p => p.year)),
    selected: {}
  };

  // Header
  document.getElementById("title").textContent = P.title;
  document.getElementById("subtitle").textContent = P.subtitle;
  const r = P.run || {};
  document.getElementById("runmeta").textContent =
    `Generated ${r.generated_at || "—"} · Data extracted ${r.extracted_at || "—"} · Data mode: ${r.data_mode || "—"}`;

  // Banners
  const banners = document.getElementById("banners");
  const unexplained = P.validation.filter(v => v.Status === "UNEXPLAINED DIFFERENCE");
  if (unexplained.length) {
    const items = [...new Set(unexplained.map(v => `${v.Metric} PY${v.Plan_Year}`))].join(", ");
    banners.appendChild(el("div", { class: "banner bad" },
      `Validation failure — unexplained difference(s) for: ${items}. Values shown are the actual query output; see Validation Results.`));
  }
  if (r.data_mode && r.data_mode !== "live") {
    banners.appendChild(el("div", { class: "banner warn" },
      `Data mode: ${r.data_mode} — this dashboard was not produced by a live Azure query in this run.`));
  }

  // Plan Year controls
  const pyBox = document.getElementById("py-controls");
  P.plan_years.forEach(p => {
    const enabled = p.available && p.has_data;
    const lab = el("label", { class: "py" + (enabled ? "" : " disabled"), title: enabled ? "" : (p.pending_reason || "No data") });
    const cb = el("input", { type: "checkbox" });
    cb.checked = state.years.has(p.year);
    cb.disabled = !enabled;
    cb.addEventListener("change", () => { cb.checked ? state.years.add(p.year) : state.years.delete(p.year); render(); });
    lab.appendChild(cb);
    lab.appendChild(el("span", { class: "swatch", style: `background:${P.colors[p.year] || "#999"}` }));
    lab.appendChild(document.createTextNode(p.label));
    pyBox.appendChild(lab);
  });

  // Metric controls
  const mBox = document.getElementById("metric-controls");
  P.metrics.forEach(m => {
    const b = el("button", { class: "metric" + (m.status !== "ACTIVE" ? " pending" : ""), "data-metric": m.name }, m.name.toUpperCase());
    b.addEventListener("click", () => { state.metric = m.name; state.selected = {}; render(); });
    mBox.appendChild(b);
  });
  mBox.appendChild(el("span", { class: "sep" }));
  const clear = el("button", { class: "metric clear" }, "CLEAR ALL");
  clear.addEventListener("click", () => { state.metric = null; state.selected = {}; render(); });
  mBox.appendChild(clear);

  document.querySelectorAll("button.mode").forEach(b => b.addEventListener("click", () => { state.mode = b.dataset.mode; render(); }));
  document.getElementById("reset-selection").addEventListener("click", () => { state.selected = {}; render(); });

  // Definitions
  const defs = document.getElementById("definitions");
  P.metrics.forEach(m => {
    const d = el("details");
    const s = el("summary"); s.appendChild(document.createTextNode(m.name + "  "));
    s.appendChild(badge(m.status === "ACTIVE" ? summaryStatus(m.name) : "VALIDATION PENDING"));
    d.appendChild(s);
    const dl = el("dl");
    const add = (k, v, code) => { dl.appendChild(el("dt", {}, k)); const dd = el("dd"); code ? dd.appendChild(el("code", {}, v)) : dd.textContent = v; dl.appendChild(dd); };
    add("Grain", m.grain); add("Identifier", m.identifier, m.identifier !== "Pending");
    add("Activity Date", m.date_field, m.date_field !== "Pending"); add("Date Semantics", m.date_semantics);
    add("Source", m.source_table); add("Filters", m.filters); add("Method", m.method);
    add("Validation", m.validation_note); add("Known Limitations", (m.limitations || []).join(" "));
    d.appendChild(dl);
    defs.appendChild(d);
  });

  // Plan Year availability
  const pyAvail = document.getElementById("py-availability");
  const tbl = el("table"); const th = el("thead"); const trh = el("tr");
  ["Plan Year", "Status", "Notes"].forEach(h => trh.appendChild(el("th", {}, h))); th.appendChild(trh); tbl.appendChild(th);
  const tb = el("tbody");
  P.plan_years.forEach(p => {
    const tr = el("tr");
    tr.appendChild(el("td", {}, p.label));
    tr.appendChild(el("td", {}, p.available ? (p.has_data ? "Available" : "No data returned") : "Source Pending"));
    tr.appendChild(el("td", {}, p.available ? "" : `${p.pending_reason} Data-owner question: “${p.data_owner_question}”`));
    tb.appendChild(tr);
  });
  tbl.appendChild(tb); pyAvail.appendChild(tbl);

  // Validation table
  const vb = document.getElementById("validation-body");
  P.validation.forEach(v => {
    const tr = el("tr");
    tr.appendChild(el("td", {}, v.Metric)); tr.appendChild(el("td", {}, v.Plan_Year)); tr.appendChild(el("td", {}, v.Level));
    tr.appendChild(el("td", {}, v.Check));
    tr.appendChild(el("td", { class: "num" }, fmt(v.Expected))); tr.appendChild(el("td", { class: "num" }, fmt(v.Actual)));
    tr.appendChild(el("td", { class: "num" }, v.Difference === null ? "—" : fmt(v.Difference)));
    const st = el("td"); st.appendChild(badge(v.Status)); tr.appendChild(st);
    tr.appendChild(el("td", {}, v.Note || ""));
    vb.appendChild(tr);
  });

  function summaryStatus(metric) {
    const s = P.series[metric] || {};
    const statuses = Object.values(s).map(x => x.status);
    if (!statuses.length) return "VALIDATION PENDING";
    for (const k of ["UNEXPLAINED DIFFERENCE", "EXPLAINED DIFFERENCE", "VALIDATION PENDING"]) if (statuses.includes(k)) return k;
    return "MATCHED";
  }

  function rowFor(metric, year) {
    const s = (P.series[metric] || {})[String(year)];
    if (!s || !s.dates.length) return null;
    const sel = state.selected[year];
    let i = s.dates.length - 1;
    if (sel) { const j = s.dates.indexOf(sel); if (j >= 0) i = j; }
    return { date: s.dates[i], daily: s.daily[i], cumulative: s.cumulative[i], grain: s.grain, status: s.status,
             source: s.source, date_field: s.date_field, selected: !!sel && s.dates[i] === sel };
  }

  const chartDiv = document.getElementById("chart");
  const ph = document.getElementById("placeholder");
  function showPlaceholder(title, lines) {
    Plotly.purge(chartDiv); chartDiv._clickBound = false; chartDiv.style.display = "none"; ph.style.display = "flex"; ph.innerHTML = "";
    ph.appendChild(el("h3", {}, title)); lines.forEach(l => ph.appendChild(el("div", {}, l)));
  }

  function render() {
    document.querySelectorAll("button.metric[data-metric]").forEach(b => b.classList.toggle("active", b.dataset.metric === state.metric));
    document.querySelectorAll("button.mode").forEach(b => b.classList.toggle("active", b.dataset.mode === state.mode));
    const m = state.metric ? metricByName[state.metric] : null;
    const modeLabel = state.mode === "daily" ? "Daily" : "Cumulative";
    const kpis = document.getElementById("kpis"); kpis.innerHTML = "";
    const body = document.getElementById("comparison-body"); body.innerHTML = "";
    document.getElementById("reset-selection").style.display = Object.keys(state.selected).length ? "" : "none";

    if (!m) {
      document.getElementById("chart-title").textContent = "No metric selected";
      document.getElementById("chart-meta").textContent = "";
      showPlaceholder("Select a metric", ["Choose ENROLLMENT, CANCELLATION, TERMINATION, or EDE above."]);
      return;
    }
    document.getElementById("chart-title").textContent = `${m.name} — ${modeLabel}`;
    document.getElementById("chart-meta").textContent =
      `Grain: ${m.grain} · Identifier: ${m.identifier} · Date: ${m.date_field} · Source: ${m.source_table}`;

    if (m.status !== "ACTIVE" || !m.has_data) {
      showPlaceholder(`${m.name} — Validation Pending`, [m.validation_note, m.method]);
      const tr = el("tr"); tr.appendChild(el("td", { colspan: "7" }, `${m.name}: no values are produced until the definition is validated.`));
      body.appendChild(tr);
      return;
    }

    const years = [...state.years].sort();
    if (!years.length) {
      showPlaceholder("No Plan Year selected", ["Select at least one available Plan Year."]);
      return;
    }

    const traces = (P.traces[`${m.name}|${state.mode}`] || []).filter(t => state.years.has(t.meta.plan_year));
    const layout = JSON.parse(JSON.stringify(P.layout));
    layout.yaxis.title = { text: `${modeLabel} Count (${m.grain === "Person" ? "people" : "policies"})` };
    chartDiv.style.display = ""; ph.style.display = "none";
    Plotly.react(chartDiv, traces, layout, { responsive: true, displaylogo: false }).then(() => {
      if (!chartDiv._clickBound) { chartDiv.on("plotly_click", onPointClick); chartDiv._clickBound = true; }
    });

    years.forEach(y => {
      const row = rowFor(m.name, y); if (!row) return;
      const p = P.plan_years.find(p => p.year === y);
      const k = el("div", { class: "kpi", style: `border-top-color:${P.colors[y] || "#999"}` });
      k.appendChild(el("div", { class: "k-label" }, `${p.label} · ${m.name} · Cumulative`));
      k.appendChild(el("div", { class: "k-value" }, fmt(row.cumulative)));
      const sub = el("div", { class: "k-sub" }, `${row.selected ? "Selected" : "Latest"} date ${fmtDate(row.date)} · ${row.grain} grain  `);
      sub.appendChild(badge(row.status)); k.appendChild(sub);
      kpis.appendChild(k);

      const tr = el("tr");
      tr.appendChild(el("td", {}, p.label)); tr.appendChild(el("td", {}, m.name));
      tr.appendChild(el("td", {}, `${fmtDate(row.date)} (${row.selected ? "selected" : "latest"})`));
      tr.appendChild(el("td", { class: "num" }, fmt(row.daily))); tr.appendChild(el("td", { class: "num" }, fmt(row.cumulative)));
      tr.appendChild(el("td", {}, row.grain));
      const st = el("td"); st.appendChild(badge(row.status)); tr.appendChild(st);
      body.appendChild(tr);
    });
    P.plan_years.filter(p => !p.available).forEach(p => {
      const tr = el("tr", { style: "color:#8a94a0" });
      tr.appendChild(el("td", {}, p.label)); tr.appendChild(el("td", {}, m.name));
      tr.appendChild(el("td", { colspan: "4" }, "Source Pending — no data"));
      const st = el("td"); st.appendChild(badge("VALIDATION PENDING")); tr.appendChild(st);
      body.appendChild(tr);
    });
  }

  function onPointClick(ev) {
    const pt = ev.points && ev.points[0]; if (!pt) return;
    state.selected = { ...state.selected, [pt.data.meta.plan_year]: String(pt.x).slice(0, 10) };
    render();
  }

  render();
})();
</script>
</body>
</html>
"""

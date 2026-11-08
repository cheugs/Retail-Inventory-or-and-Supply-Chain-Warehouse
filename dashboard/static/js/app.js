/* Page logic: load the data, then fill every chapter.
   Data source: the live API (/api/snapshot, local Docker stack) or, if it is not
   available (static online demo), the exported file data/snapshot.json. */

let DATA = null;
let SOURCE = "snapshot";

async function loadData() {
  try {
    const res = await fetch("api/snapshot", { cache: "no-store" });
    if (res.ok && (res.headers.get("content-type") || "").includes("json")) {
      SOURCE = "live";
      return await res.json();
    }
  } catch (e) { /* no API: static hosting */ }
  const res = await fetch("data/snapshot.json", { cache: "no-store" });
  if (!res.ok) throw new Error("snapshot not found");
  SOURCE = "snapshot";
  return await res.json();
}

function icon(name) { return `<svg><use href="#i-${name}"/></svg>`; }

function kpiTiles(container, tiles) {
  container.innerHTML = tiles.map((k, i) => `
    <div class="kpi" data-reveal style="--delay:${i * 0.07}s">
      <div class="label">${icon(k.icon)}${k.label}</div>
      <div class="value" data-count="${k.value}" data-format="${k.format}">${(FORMATTERS[k.format] || String)(0)}</div>
      <div class="hint">${k.hint || ""}</div>
    </div>`).join("");
}

function statusCell(status) {
  const ok = status === "pass";
  return `<span class="status ${ok ? "pass" : "fail"}">${icon(ok ? "check" : "x")}${t(ok ? "pass" : "fail")}</span>`;
}

function renderMeta(d) {
  const m = d.meta;
  document.getElementById("metaPeriod").textContent = `${fmt.date(m.period_start)} - ${fmt.date(m.period_end)}`;
  document.getElementById("metaSource").textContent = t(SOURCE === "live" ? "live" : "snapshot");
  document.getElementById("metaUpdated").textContent = new Date(m.generated_at).toLocaleDateString(locale());
  const recon = d.quality.reconciliation;
  const hero = [
    ["heroSales", m.sales_rows, "int"], ["heroInventory", m.inventory_rows, "int"],
    ["heroStores", m.stores, "int"], ["heroChecks", recon.length, "int"],
  ];
  hero.forEach(([id, v, f]) => {
    const node = document.getElementById(id);
    node.dataset.count = v; node.dataset.format = f; delete node.dataset.counted;
    node.textContent = FORMATTERS[f](v);
  });
}

function renderOverview(d) {
  const k = d.kpis;
  kpiTiles(document.getElementById("kpisOverview"), [
    { icon: "euro", label: t("revenue"), value: k.revenue_eur, format: "eur", hint: t("h_revenue") },
    { icon: "box", label: t("units"), value: k.units_sold, format: "int" },
    { icon: "trend", label: t("margin_rate"), value: k.gross_margin_rate, format: "pct" },
    { icon: "refresh", label: t("turnover"), value: k.annualized_turnover, format: "num1", hint: `${fmt.num(k.days_of_inventory, 1)} ${t("days")} · ${t("days_inv").toLowerCase()}` },
  ]);
  const labels = d.daily.map((r) => r.date);
  legend(document.getElementById("legendDaily"), [
    { name: t("revenue"), color: "var(--series-1)" }, { name: t("margin"), color: "var(--series-3)" },
  ]);
  lineChart(document.getElementById("chartDaily"), {
    labels, area: true, xFormat: fmt.date, yFormat: fmt.eurShort,
    series: [
      { name: t("revenue"), color: "#3987e5", values: d.daily.map((r) => r.revenue_eur) },
      { name: t("margin"), color: "#199e70", values: d.daily.map((r) => r.margin_eur), area: false },
    ],
  });
  hbarChart(document.getElementById("chartCategory"), d.by_category.map((c) => ({
    label: c.category, value: c.revenue_eur,
    tip: `<div class="tt-row"><span>${t("revenue")}</span><span>${fmt.eur(c.revenue_eur)}</span></div><div class="tt-row"><span>${t("margin_rate")}</span><span>${fmt.pct(c.margin_rate)}</span></div>`,
  })), { format: fmt.eurShort, labelWidth: 110 });
  hbarChart(document.getElementById("chartStore"), d.by_store.map((s) => ({
    label: `${s.store_name} (${s.currency})`, value: s.revenue_eur,
    tip: `<div class="tt-row"><span>${s.city}, ${s.country}</span><span>${fmt.eur(s.revenue_eur)}</span></div>`,
  })), { format: fmt.eurShort, labelWidth: 200, color: "var(--series-1)" });
}

function renderStockouts(d) {
  const k = d.kpis, so = d.stockouts;
  const worstCat = so.by_category[0];
  kpiTiles(document.getElementById("kpisStockouts"), [
    { icon: "package-x", label: t("stockout_rate"), value: k.stockout_rate, format: "pct", hint: t("h_stockout") },
    { icon: "euro", label: t("lost"), value: k.est_lost_revenue_eur, format: "eur", hint: fmt.pct(k.est_lost_revenue_eur / k.revenue_eur) + " " + t("revenue").toLowerCase() },
    { icon: "alert", label: worstCat.category, value: worstCat.stockout_rate, format: "pct", hint: t("stockout_rate").toLowerCase() },
  ]);
  lineChart(document.getElementById("chartStockoutDaily"), {
    labels: d.daily.map((r) => r.date), area: true, xFormat: fmt.date, yFormat: (v) => fmt.pct(v, 1),
    series: [{ name: t("stockout_rate"), color: "#d95926", values: d.daily.map((r) => r.stockout_rate) }],
  });
  const wd = t("weekdays");
  const maxWd = Math.max(...so.by_weekday.map((r) => r.stockout_rate));
  columnChart(document.getElementById("chartWeekday"), so.by_weekday.map((r) => ({
    label: wd[r.weekday - 1], value: r.stockout_rate,
  })), { format: (v) => fmt.pct(v, 1), color: "var(--series-1)", highlight: (r) => r.value === maxWd });
  const lostSub = (r) => fmt.eurShort(r.lost) + " " + t("lost_short");
  hbarChart(document.getElementById("chartStockoutCategory"), so.by_category.map((c) => ({
    label: c.category, value: c.stockout_rate, lost: c.lost_revenue_eur,
    tip: `<div class="tt-row"><span>${t("stockout_rate")}</span><span>${fmt.pct(c.stockout_rate)}</span></div><div class="tt-row"><span>${t("lost")}</span><span>${fmt.eur(c.lost_revenue_eur)}</span></div>`,
  })), { format: (v) => fmt.pct(v), sub: lostSub, color: "var(--series-2)", labelWidth: 110 });
  hbarChart(document.getElementById("chartStockoutStore"), so.by_store.map((s) => ({
    label: s.store_name, value: s.stockout_rate, lost: s.lost_revenue_eur,
    tip: `<div class="tt-row"><span>${t("stockout_rate")}</span><span>${fmt.pct(s.stockout_rate)}</span></div><div class="tt-row"><span>${t("lost")}</span><span>${fmt.eur(s.lost_revenue_eur)}</span></div>`,
  })), { format: (v) => fmt.pct(v), sub: lostSub, color: "var(--series-2)", labelWidth: 130 });
  table(document.getElementById("tableTopStockouts"), [
    { label: t("product"), render: (r) => `${r.product_name} <span class="pill">${r.product_id}</span>` },
    { label: t("category"), key: "category" },
    { label: t("supplier"), key: "supplier_id" },
    { label: t("store_days"), num: true, render: (r) => fmt.int(r.stockout_store_days) },
    { label: t("stockout_rate"), num: true, render: (r) => `${fmt.pct(r.stockout_rate)}<span class="meter"><i style="width:${Math.min(100, r.stockout_rate * 300)}%;background:var(--series-2)"></i></span>` },
    { label: t("units"), num: true, render: (r) => fmt.int(r.units_sold) },
  ], so.top_products);
}

function renderSuppliers(d) {
  const k = d.kpis, su = d.suppliers;
  const evaluable = su.summary.reduce((a, s) => a + s.order_lines, 0);
  kpiTiles(document.getElementById("kpisSuppliers"), [
    { icon: "truck", label: t("otif"), value: k.otif_rate, format: "pct", hint: `${fmt.int(evaluable)} ${t("h_otif")}` },
    { icon: "box", label: t("fill_rate"), value: k.fill_rate, format: "pct" },
    { icon: "clock", label: t("lead_time"), value: k.avg_lead_time_days, format: "days" },
  ]);
  hbarChart(document.getElementById("chartOtif"), su.summary.map((s) => ({
    label: `${s.supplier_id} · ${s.supplier_name}`, value: s.otif_rate,
    tip: `<div class="tt-row"><span>${t("otif")}</span><span>${fmt.pct(s.otif_rate)}</span></div>
          <div class="tt-row"><span>${t("on_time")}</span><span>${fmt.pct(s.on_time_rate)}</span></div>
          <div class="tt-row"><span>${t("in_full")}</span><span>${fmt.pct(s.in_full_rate)}</span></div>
          <div class="tt-row"><span>${t("fill_rate")}</span><span>${fmt.pct(s.fill_rate)}</span></div>`,
  })), { format: (v) => fmt.pct(v, 0), color: "var(--series-3)", labelWidth: 190 });
  legend(document.getElementById("legendLead"), [
    { name: t("promised"), color: "var(--series-1)" }, { name: t("actual"), color: "var(--series-2)" },
  ]);
  dumbbellChart(document.getElementById("chartLead"), [...su.summary].sort((a, b) =>
    (b.avg_actual_lead_time_days - b.avg_promised_lead_time_days) - (a.avg_actual_lead_time_days - a.avg_promised_lead_time_days)).map((s) => ({
    label: s.supplier_id, name: s.supplier_name, a: s.avg_promised_lead_time_days, b: s.avg_actual_lead_time_days,
  })), { aName: t("promised"), bName: t("actual"), format: (v) => fmt.num(v, 1) + " " + t("days") });
  legend(document.getElementById("legendMonthly"), [
    { name: t("otif"), color: "var(--series-3)" }, { name: t("on_time"), color: "var(--series-1)" }, { name: t("in_full"), color: "var(--series-4)" },
  ]);
  lineChart(document.getElementById("chartSupplierMonthly"), {
    labels: su.monthly.map((r) => r.month), xFormat: fmt.month, yFormat: (v) => fmt.pct(v, 0), height: 240,
    series: [
      { name: t("otif"), color: "#199e70", values: su.monthly.map((r) => r.otif_rate) },
      { name: t("on_time"), color: "#3987e5", values: su.monthly.map((r) => r.on_time_rate) },
      { name: t("in_full"), color: "#c98500", values: su.monthly.map((r) => r.in_full_rate) },
    ],
  });
  const names = t("status_names");
  hbarChart(document.getElementById("chartPoStatus"), su.status.map((s) => ({
    label: names[s.status] || s.status, value: s.lines,
  })), { format: fmt.int, color: "var(--series-1)", labelWidth: 100 });
}

function renderTurnover(d) {
  const k = d.kpis, tu = d.turnover;
  kpiTiles(document.getElementById("kpisTurnover"), [
    { icon: "refresh", label: t("turnover"), value: k.annualized_turnover, format: "num1" },
    { icon: "clock", label: t("days_inv"), value: k.days_of_inventory, format: "days", hint: t("h_days") },
    { icon: "euro", label: t("inv_value"), value: k.avg_inventory_value_eur, format: "eur" },
  ]);
  hbarChart(document.getElementById("chartTurnover"), tu.by_category.map((c) => ({
    label: c.category, value: c.annualized_turnover,
  })), { format: (v) => fmt.num(v, 1), color: "var(--series-4)", labelWidth: 110 });
  const byDays = [...tu.by_category].sort((a, b) => b.days_of_inventory - a.days_of_inventory);
  hbarChart(document.getElementById("chartDaysInventory"), byDays.map((c) => ({
    label: c.category, value: c.days_of_inventory,
  })), { format: (v) => fmt.num(v, 1) + " " + t("days"), color: "var(--series-1)", labelWidth: 110 });
  lineChart(document.getElementById("chartInventoryValue"), {
    labels: d.daily.map((r) => r.date), area: true, xFormat: fmt.date, yFormat: fmt.eurShort, height: 240,
    series: [{ name: t("inv_value"), color: "#c98500", values: d.daily.map((r) => r.inventory_value_eur) }],
  });
  table(document.getElementById("tableSlow"), [
    { label: t("product"), render: (r) => `${r.product_name}` },
    { label: t("category"), key: "category" },
    { label: t("cover"), num: true, render: (r) => fmt.num(r.days_of_cover, 1) },
  ], tu.slow_movers);
}

function renderQuality(d) {
  const q = d.quality;
  const rowsLoaded = q.raw_rows.reduce((a, r) => a + r.rows, 0);
  const rejected = q.rejected.reduce((a, r) => a + r.rows, 0);
  const dup = q.rejected.filter((r) => r.reason.startsWith("duplicate")).reduce((a, r) => a + r.rows, 0);
  const late = q.late_arrivals.filter((r) => r.delay_days > 0).reduce((a, r) => a + r.rows, 0);
  const passed = q.reconciliation.filter((r) => r.status === "pass").length;
  kpiTiles(document.getElementById("kpisQuality"), [
    { icon: "database", label: t("rows_loaded"), value: rowsLoaded, format: "int", hint: t("h_rows") },
    { icon: "shield", label: t("rejected"), value: rejected, format: "int", hint: `${fmt.int(dup)} ${t("h_rejected")}` },
    { icon: "clock", label: t("late"), value: late, format: "int", hint: t("h_late") },
    { icon: "box", label: t("early"), value: q.early_facts.sales_rows || 0, format: "int", hint: t("h_early") },
    { icon: "layers", label: t("scd2"), value: q.scd2.new_versions || 0, format: "int", hint: t("h_scd2") },
    { icon: "check", label: t("recon_ok"), value: passed, format: "int", hint: `${passed} / ${q.reconciliation.length} · ${t("h_recon")}` },
  ]);
  hbarChart(document.getElementById("chartRejected"), q.rejected.map((r) => ({
    label: `${r.reason.replaceAll("_", " ")}`, value: r.rows,
    tip: `<div class="tt-row"><span>${r.entity}</span><span>${fmt.int(r.rows)}</span></div>`,
  })), { format: fmt.int, color: "var(--series-5)", labelWidth: 190, rowH: 26 });
  columnChart(document.getElementById("chartLate"), q.late_arrivals.filter((r) => r.delay_days > 0).map((r) => ({
    label: t("delay")(r.delay_days), value: r.rows,
  })), { format: fmt.int, color: "var(--series-1)", height: 200 });
  table(document.getElementById("tableRecon"), [
    { label: t("check"), render: (r) => `<code>${r.check_name}</code>` },
    { label: t("scope"), key: "scope" },
    { label: t("expected"), num: true, render: (r) => fmt.num(r.expected, Number.isInteger(r.expected) ? 0 : 2) },
    { label: t("actual_v"), num: true, render: (r) => fmt.num(r.actual, Number.isInteger(r.actual) ? 0 : 2) },
    { label: t("diff"), num: true, render: (r) => fmt.num(r.difference, 2) },
    { label: t("status"), render: (r) => statusCell(r.status) },
  ], q.reconciliation);
  table(document.getElementById("tableRuns"), [
    { label: t("step"), render: (r) => `<code>${r.step}</code>` },
    { label: t("runs"), num: true, key: "runs" },
    { label: t("ok"), num: true, key: "success" },
    { label: t("failed"), num: true, key: "failed" },
    { label: t("avg_s"), num: true, render: (r) => r.avg_duration_s == null ? "-" : fmt.num(r.avg_duration_s, 2) },
  ], q.pipeline_runs);
  table(document.getElementById("tableAnomalies"), [
    { label: t("indicator"), render: (r) => `<span class="status" style="color:var(--warning)">${icon("alert")}${r.indicator.replaceAll("_", " ")}</span>` },
    { label: t("count"), num: true, render: (r) => fmt.int(r.rows) },
    { label: t("rule"), render: (r) => `<span style="font-size:12px">${r.rule}</span>` },
  ], q.anomalies);

  if (d.benchmark && d.benchmark.runs) {
    document.getElementById("benchPanel").hidden = false;
    table(document.getElementById("tableBench"), [
      { label: t("bench_rows"), num: true, render: (r) => fmt.int(r.sales_rows) },
      { label: t("bench_ingest"), num: true, render: (r) => fmt.num(r.ingest_s, 1) },
      { label: t("bench_dbt"), num: true, render: (r) => fmt.num(r.dbt_build_s, 1) },
      { label: t("bench_total"), num: true, render: (r) => fmt.num(r.total_s, 1) },
      { label: t("bench_rate"), num: true, render: (r) => fmt.int(r.rows_per_s) },
      { label: t("bench_recon"), render: (r) => statusCell(r.reconciliation === "pass" ? "pass" : "fail") },
    ], d.benchmark.runs);
  }
}

function renderAll() {
  applyStaticTranslations();
  renderMeta(DATA);
  renderOverview(DATA);
  renderStockouts(DATA);
  renderSuppliers(DATA);
  renderTurnover(DATA);
  renderQuality(DATA);
  Motion.observe();
}

(async function start() {
  applyStaticTranslations();
  try {
    DATA = await loadData();
    renderAll();
  } catch (e) {
    console.error(e);
    document.getElementById("main").insertAdjacentHTML("afterbegin",
      `<div class="chapter"><div class="error-box">${t("load_error")}</div></div>`);
  }
  document.getElementById("loader").classList.add("done");

  document.getElementById("langToggle").addEventListener("click", () => {
    LANG = LANG === "fr" ? "en" : "fr";
    try { localStorage.setItem("lang", LANG); } catch (e) { /* ignore */ }
    if (DATA) renderAll(); else applyStaticTranslations();
  });

  // charts are drawn at the container width: redraw after a resize
  let timer;
  let lastWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    if (Math.abs(window.innerWidth - lastWidth) < 40) return;
    lastWidth = window.innerWidth;
    clearTimeout(timer);
    timer = setTimeout(() => { if (DATA) renderAll(); }, 250);
  });
})();

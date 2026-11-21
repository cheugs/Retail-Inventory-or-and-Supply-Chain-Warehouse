/* Translations: French is the main language, English the second one.
   Static texts use data-i18n="key" in index.html; scripts call t("key"). */
const I18N = {
  fr: {},   // French texts are the ones written in index.html (read at start-up)
  en: {
    brand_sub: "Retail data warehouse",
    nav_overview: "Overview", nav_stockouts: "Stockouts", nav_suppliers: "Suppliers",
    nav_turnover: "Inventory turnover", nav_quality: "Quality and pipeline", nav_architecture: "Architecture",
    meta_period: "Period", meta_source: "Source", meta_updated: "Updated",
    hero_eyebrow: "Student project · Data engineering",
    hero_l1: "From imperfect", hero_l2: "source files to a", hero_l3: "reliable warehouse.",
    hero_lede: "Orders, product catalog, supplier deliveries, inventory and sales of a simulated store chain, brought together in a star schema. Three business questions: where is stock missing, which suppliers keep their promises, and how fast does the stock turn?",
    hero_sales: "sales lines", hero_inventory: "stock counts", hero_stores: "stores (EUR and CHF)",
    hero_checks: "reconciliation checks", scroll: "Scroll",
    ov_eyebrow: "Overview", ov_title: "The business at a glance",
    ov_lede: "Revenue converted to euros at the daily rate, margin computed with the cost valid at the time of the sale (SCD type 2 history).",
    ov_daily: "Revenue and margin per day", ov_daily_sub: "EUR, all stores. Saturday peaks come from promotions.",
    ov_category: "By category", ov_category_sub: "Revenue, EUR",
    ov_store: "By store", ov_store_sub: "Swiss stores sell in CHF: amounts converted to EUR.",
    so_eyebrow: "Stockouts", so_title: "Where the shelf is empty",
    so_lede: "A product is out of stock when its end-of-day stock is zero. Lost sales are an estimate: the product's average daily sales on the days it was available.",
    so_daily: "Stockout rate per day", so_daily_sub: "Share of store x product pairs at zero at the end of the day",
    so_weekday: "By day of week", so_weekday_sub: "Average stockout rate",
    so_category: "By category", so_category_sub: "Stockout rate and estimated lost sales",
    so_store: "By store", so_store_sub: "Stockout rate and estimated lost sales",
    so_top: "Products most often out of stock", so_top_sub: "Store-days out of stock over the whole period",
    su_eyebrow: "Supplier performance", su_title: "Who keeps their promises",
    su_lede: "Each order line follows its milestones: ordered, promised, delivered. OTIF = delivered on time AND in full. Only lines delivered or past their promised date are counted.",
    su_otif: "OTIF rate per supplier", su_otif_sub: "Sorted from best to worst",
    su_lead: "Promised vs actual lead time", su_lead_sub: "Days between order and first delivery",
    su_monthly: "Monthly trend", su_monthly_sub: "By order month",
    su_status: "Order line status", su_status_sub: "On the last loaded date",
    tu_eyebrow: "Inventory turnover", tu_title: "Stock that sleeps",
    tu_lede: "Turnover = cost of goods sold / average stock value (at cost), scaled to one year to compare periods of different length. Days of inventory = how long the average stock lasts.",
    tu_category: "Annualized turnover by category", tu_category_sub: "The longer the bar, the faster the stock turns",
    tu_days: "Days of inventory by category", tu_days_sub: "How many days of sales the average stock covers",
    tu_value: "Stock value per day", tu_value_sub: "EUR at cost, all stores",
    tu_slow: "Slow-moving products", tu_slow_sub: "Highest days of cover",
    qa_eyebrow: "Data quality and pipeline", qa_title: "Nothing gets lost silently",
    qa_lede: "Every source row ends up either in the warehouse or in quarantine with its reason. Duplicates do not inflate amounts, late rows are placed at their real date, and every load is reconciled with the totals sent by the source.",
    qa_rejected: "Rows isolated by reason", qa_rejected_sub: "quarantine.* tables, all sources",
    qa_late: "Sales that arrived late", qa_late_sub: "Days between the sale and the file, same-day excluded",
    qa_recon: "Reconciliation with source totals", qa_recon_sub: "Last run, audit.reconciliation table",
    qa_runs: "Pipeline steps", qa_runs_sub: "audit.pipeline_runs table",
    qa_anomalies: "Simulated anomaly indicators", qa_anomalies_sub: "Simple, explainable rules. They are not proof of theft or fraud.",
    qa_bench: "Performance tests", qa_bench_sub: "benchmarks/run_benchmark.py, on a laptop",
    ar_eyebrow: "Architecture", ar_title: "The journey of a record",
    ar_lede: "Every day Airflow runs the load, the dbt transformation, the tests and the reconciliation. Layers are separated: raw, cleaned, star schema, quarantine and audit.",
    ar_n1: "Catalog, POS", ar_n1s: "products, sales", ar_n2: "Stock, purchasing", ar_n2s: "counts, orders",
    ar_n3: "Receiving, finance", ar_n3s: "deliveries, FX rates", ar_n4: "Python ingestion", ar_n4s: "idempotent per day",
    ar_n5s: "raw text, then typed", ar_n5s2: "quality rules, dedup", ar_n6: "Star schema", ar_n6s: "incremental facts",
    ar_n7: "Dashboard", ar_n8s: "rejected rows + reason", ar_n9s: "logs, reconciliation", ar_n10: "Airflow, one run per day",
    ar_c1: "Facts", ar_c1t: "fct_sales (receipt line, incremental), fct_inventory_daily (daily snapshot, incremental), fct_purchase_order_lines (accumulating snapshot).",
    ar_c2: "Dimensions", ar_c2t: "dim_product (SCD type 2: price, cost, supplier), dim_store and dim_supplier (SCD type 1), dim_date.",
    ar_c3: "Late data", ar_c3t: "3-day reprocessing window, \"unknown product\" member fixed at the next run, SCD2 history rebuilt at every run.",
    footer: "Student project by Chengho Fongang Marie Louise. Fully synthetic data: no real company is represented.",
  },
  // texts built by the scripts (charts, tables, KPI tiles)
  dyn: {
    fr: {
      revenue: "Chiffre d'affaires", margin: "Marge brute", units: "Unités vendues", margin_rate: "Taux de marge",
      stockout_rate: "Taux de rupture", lost: "Ventes perdues (estim.)", lost_short: "perdues",
      otif: "OTIF", on_time: "A l'heure", in_full: "En totalité", fill_rate: "Taux de service",
      lead_time: "Délai moyen", promised: "Promis", actual: "Réel", days: "j",
      turnover: "Rotation annualisée", days_inv: "Jours de stock", inv_value: "Stock moyen (au coût)",
      rows_loaded: "Lignes chargées", rejected: "Lignes en quarantaine", late: "Lignes en retard",
      early: "Ventes avant leur produit", scd2: "Nouvelles versions produit",
      recon_ok: "Contrôles réussis", product: "Produit", category: "Catégorie", supplier: "Fournisseur",
      store_days: "Jours en rupture", cover: "Couverture (j)", check: "Contrôle", scope: "Portée",
      expected: "Attendu", actual_v: "Obtenu", diff: "Ecart", status: "Statut", pass: "OK", fail: "Echec",
      step: "Etape", runs: "Exécutions", ok: "Succès", failed: "Echecs", avg_s: "Durée moy. (s)",
      indicator: "Indicateur", rule: "Règle", count: "Lignes",
      weekdays: ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
      status_names: { complete: "Complète", partial: "Partielle", overdue: "En retard", open: "Ouverte" },
      delay: (d) => `+${d} j`,
      h_revenue: "sur la période", h_stockout: "couples magasin x produit", h_otif: "lignes évaluables",
      h_days: "au rythme moyen des ventes", h_rows: "8 types de fichiers", h_rejected: "dont doublons",
      h_late: "rangées à leur vraie date", h_early: "rattachées au bon produit ensuite",
      h_scd2: "changements de prix ou de fournisseur", h_recon: "source = entrepôt",
      bench_rows: "Lignes de vente", bench_ingest: "Ingestion (s)", bench_dbt: "dbt build (s)",
      bench_total: "Total (s)", bench_rate: "Lignes/s (bout en bout)", bench_recon: "Rapprochement",
      live: "base en direct", snapshot: "snapshot JSON",
      load_error: "Impossible de charger les données du tableau de bord.",
      products_lbl: "produits", stockout_lbl: "rupture",
    },
    en: {
      revenue: "Revenue", margin: "Gross margin", units: "Units sold", margin_rate: "Margin rate",
      stockout_rate: "Stockout rate", lost: "Lost sales (est.)", lost_short: "lost",
      otif: "OTIF", on_time: "On time", in_full: "In full", fill_rate: "Fill rate",
      lead_time: "Average lead time", promised: "Promised", actual: "Actual", days: "d",
      turnover: "Annualized turnover", days_inv: "Days of inventory", inv_value: "Average stock (at cost)",
      rows_loaded: "Rows loaded", rejected: "Rows in quarantine", late: "Late rows",
      early: "Sales before their product", scd2: "New product versions",
      recon_ok: "Checks passed", product: "Product", category: "Category", supplier: "Supplier",
      store_days: "Store-days out", cover: "Cover (d)", check: "Check", scope: "Scope",
      expected: "Expected", actual_v: "Actual", diff: "Difference", status: "Status", pass: "Pass", fail: "Fail",
      step: "Step", runs: "Runs", ok: "Success", failed: "Failed", avg_s: "Avg duration (s)",
      indicator: "Indicator", rule: "Rule", count: "Rows",
      weekdays: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
      status_names: { complete: "Complete", partial: "Partial", overdue: "Overdue", open: "Open" },
      delay: (d) => `+${d} d`,
      h_revenue: "over the period", h_stockout: "store x product pairs", h_otif: "evaluable lines",
      h_days: "at the average sales pace", h_rows: "8 file types", h_rejected: "including duplicates",
      h_late: "placed at their real date", h_early: "linked to the right product later",
      h_scd2: "price or supplier changes", h_recon: "source = warehouse",
      bench_rows: "Sales lines", bench_ingest: "Ingestion (s)", bench_dbt: "dbt build (s)",
      bench_total: "Total (s)", bench_rate: "Rows/s (end to end)", bench_recon: "Reconciliation",
      live: "live database", snapshot: "JSON snapshot",
      load_error: "Could not load the dashboard data.",
      products_lbl: "products", stockout_lbl: "stockout",
    },
  },
};

let LANG = "fr";
try { LANG = localStorage.getItem("lang") || "fr"; } catch (e) { /* storage blocked: keep French */ }

function t(key) { return I18N.dyn[LANG][key] ?? key; }

function applyStaticTranslations() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (!(key in I18N.fr)) I18N.fr[key] = el.textContent;   // remember the French original
    el.textContent = LANG === "fr" ? I18N.fr[key] : (I18N.en[key] ?? I18N.fr[key]);
  });
  const label = document.getElementById("langLabel");
  if (label) label.textContent = LANG === "fr" ? "EN" : "FR";
}

function locale() { return LANG === "fr" ? "fr-FR" : "en-GB"; }
const fmt = {
  eur: (v) => new Intl.NumberFormat(locale(), { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(v),
  eurShort: (v) => new Intl.NumberFormat(locale(), { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 }).format(v),
  int: (v) => new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(v),
  num: (v, d = 1) => new Intl.NumberFormat(locale(), { maximumFractionDigits: d, minimumFractionDigits: d }).format(v),
  pct: (v, d = 1) => new Intl.NumberFormat(locale(), { style: "percent", maximumFractionDigits: d, minimumFractionDigits: d }).format(v),
  date: (s) => new Date(s + "T00:00:00").toLocaleDateString(locale(), { day: "numeric", month: "short" }),
  month: (s) => new Date(s + "T00:00:00").toLocaleDateString(locale(), { month: "short", year: "numeric" }),
};

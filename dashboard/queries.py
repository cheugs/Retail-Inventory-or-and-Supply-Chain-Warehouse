"""SQL queries behind the dashboard.

Everything the dashboard shows is computed here from the warehouse marts, and
returned as one JSON-friendly dictionary ("snapshot"). The same function is used:
  * live, by the FastAPI app (dashboard/app.py), and
  * offline, by export_snapshot.py, which saves it to static/data/snapshot.json
    for the online demo (static hosting, no database needed).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _clean(value):
    """Convert database types to plain JSON types."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _rows(cur, sql: str, params=None) -> list[dict]:
    cur.execute(sql, params)
    return [{k: _clean(v) for k, v in row.items()} for row in cur.fetchall()]


def _one(cur, sql: str, params=None) -> dict:
    rows = _rows(cur, sql, params)
    return rows[0] if rows else {}


def build_snapshot(conn: psycopg.Connection) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        meta = _one(cur, """
            select min(cast(sold_at as date)) as period_start, max(cast(sold_at as date)) as period_end,
                   (select count(*) from marts.dim_store) as stores,
                   (select count(*) from marts.dim_product where is_current and product_key <> '-1') as products,
                   (select count(*) from marts.dim_product where product_key <> '-1') as product_versions,
                   (select count(*) from marts.dim_supplier) as suppliers,
                   count(*) as sales_rows,
                   (select count(*) from marts.fct_inventory_daily) as inventory_rows,
                   (select count(*) from marts.fct_purchase_order_lines) as po_rows
            from marts.fct_sales
        """)
        meta["generated_at"] = datetime.now().isoformat(timespec="seconds")

        # ---------------- headline KPIs ----------------
        kpis = _one(cur, """
            with s as (
                select sum(net_amount_eur) as revenue, sum(cost_amount_eur) as cost, sum(quantity) as units
                from marts.fct_sales
            ),
            so as (
                select sum(stockout_days) * 1.0 / sum(product_days) as stockout_rate,
                       sum(est_lost_revenue_eur) as lost_revenue
                from marts.mart_stockouts_daily
            ),
            sup as (
                select avg(case when is_otif then 1.0 else 0 end) as otif,
                       sum(least(qty_received, qty_ordered)) * 1.0 / sum(qty_ordered) as fill_rate,
                       avg(actual_lead_time_days) as lead_time
                from marts.fct_purchase_order_lines where is_evaluable
            ),
            inv as (
                select avg(v) as avg_inventory_value, count(*) as days
                from (select snapshot_date, sum(on_hand_value_eur) as v
                      from marts.fct_inventory_daily group by 1) d
            )
            select round(s.revenue, 0) as revenue_eur, s.units as units_sold,
                   round((s.revenue - s.cost) / s.revenue, 4) as gross_margin_rate,
                   round(so.stockout_rate, 4) as stockout_rate, round(so.lost_revenue, 0) as est_lost_revenue_eur,
                   round(sup.otif, 4) as otif_rate, round(sup.fill_rate, 4) as fill_rate,
                   round(sup.lead_time, 2) as avg_lead_time_days,
                   round(inv.avg_inventory_value, 0) as avg_inventory_value_eur,
                   round(s.cost / inv.avg_inventory_value * 365.0 / inv.days, 2) as annualized_turnover,
                   round(inv.days / (s.cost / inv.avg_inventory_value), 1) as days_of_inventory
            from s, so, sup, inv
        """)

        daily = _rows(cur, """
            with s as (
                select sale_date, sum(revenue_eur) as revenue, sum(gross_margin_eur) as margin, sum(units_sold) as units
                from marts.mart_daily_sales group by 1
            ),
            so as (
                select snapshot_date, sum(stockout_days) * 1.0 / sum(product_days) as stockout_rate,
                       sum(est_lost_revenue_eur) as lost
                from marts.mart_stockouts_daily group by 1
            ),
            inv as (
                select snapshot_date, sum(on_hand_value_eur) as inventory_value
                from marts.fct_inventory_daily group by 1
            )
            select s.sale_date as date, round(s.revenue, 2) as revenue_eur, round(s.margin, 2) as margin_eur,
                   s.units, round(so.stockout_rate, 4) as stockout_rate, round(so.lost, 2) as lost_revenue_eur,
                   round(inv.inventory_value, 2) as inventory_value_eur
            from s
            left join so on so.snapshot_date = s.sale_date
            left join inv on inv.snapshot_date = s.sale_date
            order by 1
        """)

        by_category = _rows(cur, """
            select category, round(sum(revenue_eur), 2) as revenue_eur,
                   round(sum(gross_margin_eur) / nullif(sum(revenue_eur), 0), 4) as margin_rate,
                   sum(units_sold) as units
            from marts.mart_daily_sales group by 1 order by 2 desc
        """)
        by_store = _rows(cur, """
            select m.store_id, d.store_name, d.city, d.country, d.currency,
                   round(sum(m.revenue_eur), 2) as revenue_eur, sum(m.units_sold) as units
            from marts.mart_daily_sales m join marts.dim_store d using (store_id)
            group by 1, 2, 3, 4, 5 order by 6 desc
        """)

        # ---------------- stockouts ----------------
        stockouts = {
            "by_category": _rows(cur, """
                select category, round(sum(stockout_days) * 1.0 / sum(product_days), 4) as stockout_rate,
                       round(sum(est_lost_revenue_eur), 0) as lost_revenue_eur, sum(stockout_days) as stockout_days
                from marts.mart_stockouts_daily group by 1 order by 2 desc
            """),
            "by_store": _rows(cur, """
                select m.store_id, d.store_name, round(sum(stockout_days) * 1.0 / sum(product_days), 4) as stockout_rate,
                       round(sum(est_lost_revenue_eur), 0) as lost_revenue_eur
                from marts.mart_stockouts_daily m join marts.dim_store d using (store_id)
                group by 1, 2 order by 3 desc
            """),
            "by_weekday": _rows(cur, """
                select d.iso_day_of_week as weekday,
                       round(sum(stockout_days) * 1.0 / sum(product_days), 4) as stockout_rate
                from marts.mart_stockouts_daily m join marts.dim_date d on d.date_day = m.snapshot_date
                group by 1 order by 1
            """),
            "top_products": _rows(cur, """
                select product_id, product_name, category, supplier_id, stockout_store_days,
                       stockout_rate, units_sold, days_of_cover
                from marts.mart_product_inventory_health
                order by stockout_store_days desc, units_sold desc limit 10
            """),
        }

        # ---------------- suppliers ----------------
        suppliers = {
            "summary": _rows(cur, """
                select f.supplier_id, s.supplier_name, s.country, count(*) as order_lines,
                       round(avg(case when is_otif then 1.0 else 0 end), 4) as otif_rate,
                       round(avg(case when is_on_time then 1.0 else 0 end), 4) as on_time_rate,
                       round(avg(case when is_in_full then 1.0 else 0 end), 4) as in_full_rate,
                       round(sum(least(qty_received, qty_ordered)) * 1.0 / sum(qty_ordered), 4) as fill_rate,
                       round(avg(f.actual_lead_time_days), 2) as avg_actual_lead_time_days,
                       round(avg(f.promised_lead_time_days), 2) as avg_promised_lead_time_days,
                       sum(case when status = 'overdue' then 1 else 0 end) as overdue_lines
                from marts.fct_purchase_order_lines f join marts.dim_supplier s using (supplier_id)
                where is_evaluable
                group by 1, 2, 3 order by otif_rate desc
            """),
            "monthly": _rows(cur, """
                select order_month as month,
                       round(sum(otif_rate * evaluable_lines) / nullif(sum(evaluable_lines), 0), 4) as otif_rate,
                       round(sum(on_time_rate * evaluable_lines) / nullif(sum(evaluable_lines), 0), 4) as on_time_rate,
                       round(sum(in_full_rate * evaluable_lines) / nullif(sum(evaluable_lines), 0), 4) as in_full_rate
                from marts.mart_supplier_performance_monthly group by 1 order by 1
            """),
            "status": _rows(cur, """
                select status, count(*) as lines from marts.fct_purchase_order_lines group by 1 order by 2 desc
            """),
        }

        # ---------------- inventory turnover ----------------
        turnover = {
            "by_category": _rows(cur, """
                select category, round(sum(cogs_eur), 0) as cogs_eur,
                       round(avg(avg_inventory_value_eur), 0) as avg_inventory_value_eur,
                       round(sum(cogs_eur) / nullif(avg(avg_inventory_value_eur), 0) * 365.0 / sum(days_in_period), 2) as annualized_turnover,
                       round(sum(days_in_period) / nullif(sum(cogs_eur) / nullif(avg(avg_inventory_value_eur), 0), 0), 1) as days_of_inventory
                from marts.mart_inventory_turnover_monthly group by 1 order by 4 desc
            """),
            "monthly": _rows(cur, """
                select month_start as month, category, annualized_turnover, days_of_inventory
                from marts.mart_inventory_turnover_monthly order by 1, 2
            """),
            "slow_movers": _rows(cur, """
                select product_id, product_name, category, days_of_cover, annualized_turnover, avg_on_hand_units
                from marts.mart_product_inventory_health where days_of_cover is not null
                order by days_of_cover desc limit 8
            """),
        }

        # ---------------- data quality and pipeline health ----------------
        quality = {
            "raw_rows": _rows(cur, """
                select entity, sum(rows_loaded) as rows, count(distinct batch_date) as batches,
                       max(unknown_columns) as unknown_columns
                from (select distinct on (batch_date, entity) * from audit.load_log
                      order by batch_date, entity, finished_at desc) l
                group by 1 order by 2 desc
            """),
            "rejected": _rows(cur, """
                select 'sales' as entity, rejection_reason as reason, count(*) as rows from quarantine.rejected_sales group by 2
                union all
                select 'inventory', rejection_reason, count(*) from quarantine.rejected_inventory group by 2
                union all
                select 'deliveries', rejection_reason, count(*) from quarantine.rejected_deliveries group by 2
                union all
                select 'purchase_orders', rejection_reason, count(*) from quarantine.rejected_purchase_orders group by 2
                order by 3 desc
            """),
            "late_arrivals": _rows(cur, """
                select arrival_delay_days as delay_days, count(*) as rows
                from marts.fct_sales group by 1 order by 1
            """),
            "early_facts": _one(cur, """
                -- sales received before the catalog row of their product (early-arriving facts)
                with first_catalog as (
                    select product_id, min(_batch_date) as first_batch from raw.products group by 1
                )
                select count(*) as sales_rows, count(distinct f.product_id) as products,
                       sum(case when f.product_key = '-1' then 1 else 0 end) as still_unknown
                from marts.fct_sales f join first_catalog c using (product_id)
                where f.batch_date < c.first_batch
            """),
            "scd2": _one(cur, """
                select count(*) filter (where version_number > 1) as new_versions,
                       count(distinct product_id) filter (where version_number > 1) as products_changed
                from marts.dim_product
            """),
            "reconciliation": _rows(cur, """
                select check_name, scope, expected, actual, difference, status, checked_at
                from audit.reconciliation
                where run_id = (select run_id from audit.reconciliation order by checked_at desc limit 1)
                order by check_id
            """),
            "pipeline_runs": _rows(cur, """
                select step, count(*) as runs,
                       sum(case when status = 'success' then 1 else 0 end) as success,
                       sum(case when status = 'failed' then 1 else 0 end) as failed,
                       round(avg(duration_s), 2) as avg_duration_s,
                       max(finished_at) as last_finished_at
                from audit.pipeline_runs group by 1 order by 6 desc nulls last
            """),
            "anomalies": _rows(cur, """
                select indicator, count(*) as rows, min(rule) as rule
                from marts.mart_anomaly_indicators group by 1
            """),
            "anomaly_examples": _rows(cur, """
                select indicator, event_date, store_id, product_id, gap_value
                from marts.mart_anomaly_indicators order by abs(gap_value) desc limit 8
            """),
        }

    snapshot = {
        "meta": meta, "kpis": kpis, "daily": daily, "by_category": by_category, "by_store": by_store,
        "stockouts": stockouts, "suppliers": suppliers, "turnover": turnover, "quality": quality,
    }
    # Benchmark results are produced by benchmarks/run_benchmark.py (optional)
    bench = PROJECT_ROOT / "benchmarks" / "results.json"
    if bench.exists():
        snapshot["benchmark"] = json.loads(bench.read_text(encoding="utf-8"))
    return snapshot

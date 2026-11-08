"""Reconciliation: compare the warehouse with the totals sent by the source.

Three levels of checks, all written to audit.reconciliation:

1. Completeness of the load (per day and per file):
       rows and sums in raw.*  ==  rows and sums in the source _manifest.json
2. Conservation (nothing lost, nothing counted twice):
       raw rows   ==  rows in the fact table + rows in quarantine
       raw units  ==  units in the fact table + units in quarantine
3. Aggregation (marts add up to the facts):
       revenue in mart_daily_sales  ==  revenue in fct_sales

If a check fails, the step raises an error: in Airflow the task turns red and
the problem cannot go unnoticed.
"""
from __future__ import annotations

import argparse
import logging
from decimal import Decimal

from retail_pipeline.db import connect, new_run_id, track_step

log = logging.getLogger("reconcile")

# entity -> (raw table, numeric column used for the control sum)
MEASURES = {
    "sales": "quantity",
    "inventory": "on_hand_qty",
    "purchase_orders": "qty_ordered",
    "deliveries": "qty_received",
}

# A value "counts" in a sum only if it is a valid number (same rule as the source manifest)
NUM = "case when pg_input_is_valid({col}, 'numeric') then {col}::numeric else 0 end"

CONSERVATION_CHECKS = {
    # name: (expected SQL, actual SQL)
    "sales_rows_raw_vs_fact_plus_quarantine": (
        "select count(*) from raw.sales",
        "select (select count(*) from marts.fct_sales) + (select count(*) from quarantine.rejected_sales)",
    ),
    "sales_units_raw_vs_fact_plus_quarantine": (
        f"select coalesce(sum({NUM.format(col='quantity')}), 0) from raw.sales",
        "select (select coalesce(sum(quantity), 0) from marts.fct_sales) + "
        f"(select coalesce(sum({NUM.format(col='quantity_raw')}), 0) from quarantine.rejected_sales)",
    ),
    "inventory_rows_raw_vs_fact_plus_quarantine": (
        "select count(*) from raw.inventory",
        "select (select count(*) from marts.fct_inventory_daily) + (select count(*) from quarantine.rejected_inventory)",
    ),
    "po_lines_raw_vs_fact_plus_quarantine": (
        "select count(*) from raw.purchase_orders",
        "select (select count(*) from marts.fct_purchase_order_lines) + "
        "(select count(*) from quarantine.rejected_purchase_orders)",
    ),
    "delivered_units_valid_vs_fact": (
        "select coalesce(sum(qty_received), 0) from staging.stg_deliveries_checked d "
        "where rejection_reason is null and exists (select 1 from marts.fct_purchase_order_lines f "
        "where f.po_line_id = d.po_line_id)",
        "select coalesce(sum(qty_received), 0) from marts.fct_purchase_order_lines",
    ),
    "revenue_mart_vs_fact": (
        "select coalesce(round(sum(net_amount_eur), 2), 0) from marts.fct_sales",
        "select coalesce(round(sum(revenue_eur), 2), 0) from marts.mart_daily_sales",
    ),
}


def _record(cur, run_id: str, name: str, scope: str, expected, actual, tolerance=Decimal("0.05")) -> bool:
    expected = Decimal(str(expected or 0))
    actual = Decimal(str(actual or 0))
    diff = actual - expected
    ok = abs(diff) <= tolerance
    cur.execute(
        "INSERT INTO audit.reconciliation (run_id, check_name, scope, expected, actual, difference, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (run_id, name, scope, expected, actual, diff, "pass" if ok else "fail"),
    )
    if not ok:
        log.error("Reconciliation FAILED %s [%s]: expected %s, got %s", name, scope, expected, actual)
    return ok


def run_reconciliation(run_id: str | None = None) -> dict:
    """Run every check. Returns {"passed": n, "failed": n}; raises if something failed."""
    run_id = run_id or new_run_id()
    passed = failed = 0
    with track_step(run_id, "reconcile") as step, connect() as conn, conn.cursor() as cur:
        # 1. completeness per batch and per file: raw vs source manifest
        for entity, col in MEASURES.items():
            cur.execute(f"""
                select m.batch_date, m.row_count, coalesce(m.measure_sum, 0),
                       count(r._batch_date), coalesce(sum({NUM.format(col='r.' + col)}), 0)
                from audit.source_manifest m
                left join raw.{entity} r on r._batch_date = m.batch_date
                where m.entity = %s
                group by m.batch_date, m.row_count, m.measure_sum
            """, (entity,))
            rows = cur.fetchall()
            bad_rows = [r for r in rows if r[1] != r[3]]
            bad_sums = [r for r in rows if abs(Decimal(r[2]) - Decimal(r[4])) > Decimal("0.01")]
            # one summary line per entity (one line per day would flood the table)
            ok = _record(cur, run_id, f"{entity}_rows_manifest_vs_raw", f"{len(rows)} batches",
                         sum(r[1] for r in rows), sum(r[3] for r in rows), tolerance=Decimal(0))
            ok &= _record(cur, run_id, f"{entity}_{col}_manifest_vs_raw", f"{len(rows)} batches",
                          sum(Decimal(r[2]) for r in rows), sum(Decimal(r[4]) for r in rows))
            for r in bad_rows + bad_sums:
                log.error("Batch %s %s: manifest %s rows / %s, raw %s rows / %s", r[0], entity, r[1], r[2], r[3], r[4])
            if ok and not bad_rows and not bad_sums:
                passed += 2
            else:
                failed += 1

        # 2 and 3. conservation and aggregation
        for name, (expected_sql, actual_sql) in CONSERVATION_CHECKS.items():
            expected = cur.execute(expected_sql).fetchone()[0]
            actual = cur.execute(actual_sql).fetchone()[0]
            if _record(cur, run_id, name, "all data", expected, actual):
                passed += 1
            else:
                failed += 1
        conn.commit()
        step["rows"] = passed + failed
        step["message"] = f"{passed} passed, {failed} failed"

    log.info("Reconciliation: %s checks passed, %s failed", passed, failed)
    if failed:
        raise RuntimeError(f"{failed} reconciliation check(s) failed, see audit.reconciliation (run {run_id})")
    return {"passed": passed, "failed": failed}


def main() -> None:
    argparse.ArgumentParser(description="Reconcile the warehouse with source totals").parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    run_reconciliation()


if __name__ == "__main__":
    main()

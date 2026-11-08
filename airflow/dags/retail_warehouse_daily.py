"""Daily warehouse load, orchestrated by Airflow.

One DAG run = one business day (the logical date):

    wait_for_source_files -> ingest_batch -> dbt_build -> reconcile -> export_dashboard_snapshot

* catchup=True: Airflow replays every day since start_date, which is also how a
  backfill (or a full replay of history) is done.
* max_active_runs=1: days are processed in order, one at a time, because the
  incremental models depend on what was loaded before.
* retries: a failed task is retried automatically (for example if the database
  restarted). Every step is idempotent, so a retry never duplicates data.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor

START = datetime.fromisoformat(os.getenv("SIM_START_DATE", "2026-01-01"))
END = START + timedelta(days=int(os.getenv("SIM_DAYS", "90")) - 1)

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}


def _batch_date(ds: str) -> date:
    return date.fromisoformat(ds)


def wait_for_files(ds: str, **_) -> bool:
    """The day can start once the source has written its manifest (written last)."""
    from retail_pipeline.config import settings
    return (settings.landing_dir / ds / "_manifest.json").exists()


def ingest(ds: str, run_id: str, **_) -> int:
    from retail_pipeline.ingest import ingest_batch
    return ingest_batch(_batch_date(ds), run_id=run_id)


def dbt_build(run_id: str, **_) -> None:
    from retail_pipeline.run import run_dbt
    run_dbt(run_id, "build")


def reconcile(run_id: str, **_) -> dict:
    from retail_pipeline.reconcile import run_reconciliation
    return run_reconciliation(run_id)


def export_snapshot(**_) -> str:
    from dashboard.export_snapshot import export_snapshot as export
    return str(export())


with DAG(
    dag_id="retail_warehouse_daily",
    description="Load one day of retail source files into the star-schema warehouse",
    start_date=START,
    end_date=END,
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    default_args=default_args,
    tags=["retail", "dbt", "warehouse"],
) as dag:
    wait = PythonSensor(
        task_id="wait_for_source_files",
        python_callable=wait_for_files,
        poke_interval=30,
        timeout=60 * 60,
        mode="reschedule",
    )
    load = PythonOperator(task_id="ingest_batch", python_callable=ingest)
    build = PythonOperator(task_id="dbt_build", python_callable=dbt_build)
    check = PythonOperator(task_id="reconcile", python_callable=reconcile)
    export = PythonOperator(task_id="export_dashboard_snapshot", python_callable=export_snapshot)

    wait >> load >> build >> check >> export

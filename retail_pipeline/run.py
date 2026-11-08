"""Command line entry point: run the whole pipeline, or one step.

    python -m retail_pipeline.run all          # generate -> ingest every day -> dbt build -> reconcile -> export
    python -m retail_pipeline.run init-db      # create raw and audit schemas
    python -m retail_pipeline.run generate     # simulate the source files
    python -m retail_pipeline.run ingest [--date 2026-01-15]
    python -m retail_pipeline.run dbt [--full-refresh]
    python -m retail_pipeline.run reconcile
    python -m retail_pipeline.run export       # write the dashboard snapshot (JSON)
    python -m retail_pipeline.run replay       # rebuild the whole warehouse from the raw layer

Airflow calls the same functions (see airflow/dags/retail_warehouse_daily.py).
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from datetime import date

from retail_pipeline.config import settings
from retail_pipeline.db import init_database, new_run_id, track_step

log = logging.getLogger("run")


def dbt_command() -> list[str]:
    """Find dbt: the DBT_BIN setting, the dbt executable, or the Python module."""
    if settings.dbt_bin != "dbt" or shutil.which("dbt"):
        return [settings.dbt_bin]
    return [sys.executable, "-m", "dbt.cli.main"]


def run_dbt(run_id: str, command: str = "build", full_refresh: bool = False, extra: list[str] | None = None) -> None:
    """Run a dbt command (build = run models + run tests, in dependency order)."""
    args = dbt_command() + [command, "--project-dir", str(settings.dbt_project_dir),
                            "--profiles-dir", str(settings.dbt_project_dir), "--target", settings.dbt_target]
    if full_refresh:
        args.append("--full-refresh")
    args += extra or []
    env = {**os.environ, "POSTGRES_HOST": settings.pg_host, "POSTGRES_PORT": str(settings.pg_port),
           "POSTGRES_DB": settings.pg_db, "POSTGRES_USER": settings.pg_user,
           "POSTGRES_PASSWORD": settings.pg_password}
    with track_step(run_id, f"dbt_{command}") as step:
        log.info("Running: %s", " ".join(args[-8:]))
        result = subprocess.run(args, env=env, capture_output=True, text=True)
        # keep the end of the dbt log for the audit table and print it for the console
        tail = "\n".join(result.stdout.strip().splitlines()[-6:])
        print(result.stdout[-4000:])
        step["message"] = tail[-1000:]
        if result.returncode != 0:
            print(result.stderr[-2000:], file=sys.stderr)
            raise RuntimeError(f"dbt {command} failed (exit code {result.returncode}):\n{tail}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Retail warehouse pipeline")
    parser.add_argument("step", choices=["all", "init-db", "generate", "ingest", "dbt", "reconcile", "export", "replay"])
    parser.add_argument("--date", help="only this batch date (ingest)")
    parser.add_argument("--full-refresh", action="store_true", help="rebuild incremental models from scratch")
    parser.add_argument("--skip-generate", action="store_true", help="'all' without re-generating source files")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    # imported here so that "generate" works even without a database
    from retail_pipeline import generate, ingest, reconcile

    if args.step == "generate":
        generate.main_from_settings()
        return

    run_id = new_run_id()
    log.info("Run id: %s", run_id)
    init_database()

    if args.step in ("all",) and not args.skip_generate:
        generate.main_from_settings()

    if args.step in ("all", "ingest"):
        days = [date.fromisoformat(args.date)] if args.date else ingest.available_batches()
        for d in days:
            ingest.ingest_batch(d, run_id)

    if args.step in ("all", "dbt", "replay"):
        run_dbt(run_id, "build", full_refresh=args.full_refresh or args.step == "replay")

    if args.step in ("all", "reconcile", "replay"):
        reconcile.run_reconciliation(run_id)

    if args.step in ("all", "export", "replay"):
        from dashboard.export_snapshot import export_snapshot
        with track_step(run_id, "export_snapshot") as step:
            path = export_snapshot()
            step["message"] = str(path)


if __name__ == "__main__":
    main()

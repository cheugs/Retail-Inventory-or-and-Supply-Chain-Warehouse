"""Performance benchmark: about 10 000, 100 000 and 1 000 000 sales lines.

For each size the script:
  1. creates an empty database (retail_bench) and generates the source files,
  2. loads every day (ingestion), 3. runs `dbt build` (models + tests),
  4. runs the reconciliation, and measures each step.

Results go to benchmarks/results.json (read by the dashboard) and results.md.

    python -m benchmarks.run_benchmark              # the three sizes
    python -m benchmarks.run_benchmark --sizes 10k  # only one
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

# Must be set before retail_pipeline is imported (its settings read the environment)
os.environ["POSTGRES_DB"] = os.environ.get("BENCH_POSTGRES_DB", "retail_bench")
os.environ["LANDING_DIR"] = os.path.join(tempfile.gettempdir(), "retail_bench_landing")

import psycopg  # noqa: E402

from retail_pipeline.config import settings  # noqa: E402

HERE = Path(__file__).resolve().parent

# stores x products x 90 days; about 2 receipt lines per store, product and day
SIZES = {
    "10k": dict(stores=3, products=30, days=90, suppliers=6),
    "100k": dict(stores=6, products=100, days=90, suppliers=10),
    "1m": dict(stores=20, products=320, days=90, suppliers=20),
}


def reset_database() -> None:
    admin = settings.dsn.replace(f"dbname={settings.pg_db}", "dbname=postgres")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {settings.pg_db} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {settings.pg_db}")


def postgres_memory() -> str | None:
    """Memory used by the PostgreSQL container, if Docker is available."""
    try:
        out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", "retail_postgres"],
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip().split(" / ")[0] or None
    except (OSError, subprocess.SubprocessError):
        return None


def slowest_models(n: int = 3) -> list[dict]:
    """Read dbt's run_results.json to find the slowest models (the bottlenecks)."""
    path = settings.dbt_project_dir / "target" / "run_results.json"
    if not path.exists():
        return []
    results = json.loads(path.read_text(encoding="utf-8"))["results"]
    models = [r for r in results if r["unique_id"].startswith("model.")]
    models.sort(key=lambda r: r["execution_time"], reverse=True)
    return [{"model": r["unique_id"].split(".")[-1], "seconds": round(r["execution_time"], 1)} for r in models[:n]]


def run_size(name: str) -> dict:
    from retail_pipeline.db import init_database
    from retail_pipeline.generate import generate
    from retail_pipeline.ingest import available_batches, ingest_batch
    from retail_pipeline.reconcile import run_reconciliation
    from retail_pipeline.run import run_dbt

    cfg = SIZES[name]
    print(f"\n=== benchmark {name}: {cfg}")
    reset_database()
    init_database()
    if settings.landing_dir.exists():
        shutil.rmtree(settings.landing_dir)

    t0 = time.perf_counter()
    summary = generate(settings.landing_dir, date(2026, 1, 1), cfg["days"], cfg["stores"],
                       cfg["products"], cfg["suppliers"], seed=42)
    t_generate = time.perf_counter() - t0

    t0 = time.perf_counter()
    raw_rows = sum(ingest_batch(d, run_id=f"bench-{name}") for d in available_batches())
    t_ingest = time.perf_counter() - t0

    t0 = time.perf_counter()
    run_dbt(f"bench-{name}", "build")
    t_dbt = time.perf_counter() - t0
    memory = postgres_memory()

    t0 = time.perf_counter()
    try:
        recon = run_reconciliation(f"bench-{name}")
        recon_status = "pass" if recon["failed"] == 0 else "fail"
    except RuntimeError:
        recon_status = "fail"
    t_recon = time.perf_counter() - t0

    with psycopg.connect(settings.dsn) as conn:
        fact_rows = conn.execute("select count(*) from marts.fct_sales").fetchone()[0]
        db_size = conn.execute("select pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]

    total = t_ingest + t_dbt + t_recon
    result = {
        "size": name, "sales_rows": summary["sales"], "all_source_rows": raw_rows,
        "fact_sales_rows": fact_rows, "generate_s": round(t_generate, 1), "ingest_s": round(t_ingest, 1),
        "dbt_build_s": round(t_dbt, 1), "reconcile_s": round(t_recon, 1), "total_s": round(total, 1),
        "rows_per_s": round(raw_rows / total), "ingest_rows_per_s": round(raw_rows / t_ingest),
        "reconciliation": recon_status, "database_size": db_size, "postgres_memory": memory,
        "slowest_models": slowest_models(),
    }
    print(json.dumps(result, indent=2))
    return result


def write_markdown(results: dict) -> None:
    lines = [
        "# Benchmark results", "",
        f"Machine: {results['machine']}  ",
        f"Date: {results['date']}", "",
        "| Size | Sales lines | All source rows | Ingestion (s) | dbt build (s) | Reconciliation (s) | Total (s) | Rows/s end to end | Reconciliation | DB size | PostgreSQL memory |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for r in results["runs"]:
        lines.append(f"| {r['size']} | {r['sales_rows']:,} | {r['all_source_rows']:,} | {r['ingest_s']} | {r['dbt_build_s']} | "
                     f"{r['reconcile_s']} | {r['total_s']} | {r['rows_per_s']:,} | {r['reconciliation']} | "
                     f"{r['database_size']} | {r['postgres_memory'] or '-'} |")
    lines += ["", "Slowest dbt models (bottlenecks):", ""]
    for r in results["runs"]:
        models = ", ".join(f"{m['model']} ({m['seconds']} s)" for m in r["slowest_models"])
        lines.append(f"- {r['size']}: {models}")
    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", default=list(SIZES), choices=list(SIZES))
    args = parser.parse_args()
    runs = [run_size(name) for name in args.sizes]
    # keep the results of sizes that were not run this time
    previous = HERE / "results.json"
    if previous.exists():
        done = {r["size"] for r in runs}
        old_runs = [r for r in json.loads(previous.read_text(encoding="utf-8"))["runs"] if r["size"] not in done]
        runs = sorted(old_runs + runs, key=lambda r: list(SIZES).index(r["size"]))
    results = {
        "date": datetime.now().isoformat(timespec="minutes"),
        "machine": f"{platform.system()} {platform.release()}, {os.cpu_count()} CPU threads, PostgreSQL 16 in Docker",
        "runs": runs,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_markdown(results)
    print(f"\nResults written to {HERE / 'results.json'} and results.md")


if __name__ == "__main__":
    main()

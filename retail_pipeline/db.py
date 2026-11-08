"""Small helpers around the PostgreSQL connection and the audit tables."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import psycopg

from retail_pipeline.config import PROJECT_ROOT, settings

log = logging.getLogger("db")


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(settings.dsn, autocommit=autocommit)


def new_run_id() -> str:
    """Short id shared by every step of one pipeline run (easy to search in logs)."""
    return time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


def init_database() -> None:
    """Create the raw and audit schemas (safe to run several times)."""
    sql = (PROJECT_ROOT / "sql" / "01_raw_and_audit.sql").read_text(encoding="utf-8")
    with connect(autocommit=True) as conn:
        conn.execute(sql)
    log.info("Raw and audit schemas are ready")


@contextmanager
def track_step(run_id: str, step: str, batch_date: date | None = None):
    """Record a pipeline step in audit.pipeline_runs (start, end, duration, status).

    Usage:
        with track_step(run_id, "ingest", day) as info:
            ...
            info["rows"] = 1234
    The row is written with autocommit, so a failed step is still visible afterwards.
    """
    info: dict = {"rows": None, "message": None}
    start = time.perf_counter()
    with connect(autocommit=True) as conn:
        step_id = conn.execute(
            "INSERT INTO audit.pipeline_runs (run_id, step, batch_date, status) "
            "VALUES (%s, %s, %s, 'running') RETURNING id",
            (run_id, step, batch_date),
        ).fetchone()[0]
    try:
        yield info
    except Exception as exc:
        _finish_step(step_id, "failed", info["rows"], f"{type(exc).__name__}: {exc}"[:1000], start)
        log.error("Step %s failed (run %s, batch %s): %s", step, run_id, batch_date, exc)
        raise
    _finish_step(step_id, "success", info["rows"], info["message"], start)


def _finish_step(step_id: int, status: str, rows, message, start: float) -> None:
    with connect(autocommit=True) as conn:
        conn.execute(
            "UPDATE audit.pipeline_runs SET status=%s, rows_processed=%s, message=%s, "
            "finished_at=now(), duration_s=%s WHERE id=%s",
            (status, rows, message, round(time.perf_counter() - start, 3), step_id),
        )


def run_sql_file(path: Path) -> None:
    with connect(autocommit=True) as conn:
        conn.execute(path.read_text(encoding="utf-8"))

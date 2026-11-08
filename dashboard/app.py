"""Dashboard web server (local stack).

  GET /api/snapshot   live data computed from the warehouse
  GET /healthz        health check
  GET /               the dashboard (static files)

If the database cannot be reached, /api/snapshot answers with the last exported
snapshot, so the page still works (and says so).
"""
from __future__ import annotations

import json
import logging
import os
import time

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

try:  # works both from the project root (python -m) and inside the Docker image
    from dashboard.queries import build_snapshot
    from dashboard.export_snapshot import SNAPSHOT_PATH
except ImportError:  # pragma: no cover
    from queries import build_snapshot
    from export_snapshot import SNAPSHOT_PATH

log = logging.getLogger("dashboard")
app = FastAPI(title="Retail warehouse dashboard")

CACHE_SECONDS = 60
_cache: dict = {"at": 0.0, "data": None}


def _dsn() -> str:
    return (f"host={os.getenv('POSTGRES_HOST', 'localhost')} port={os.getenv('POSTGRES_PORT', '5433')} "
            f"dbname={os.getenv('POSTGRES_DB', 'retail_dw')} user={os.getenv('POSTGRES_USER', 'retail')} "
            f"password={os.getenv('POSTGRES_PASSWORD', 'retail')}")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/snapshot")
def snapshot():
    # small cache: the warehouse changes once a day, no need to query it at every page view
    if _cache["data"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    try:
        with psycopg.connect(_dsn(), connect_timeout=3) as conn:
            data = build_snapshot(conn)
        data["meta"]["source"] = "live"
        _cache.update(at=time.time(), data=data)
        return data
    except psycopg.Error as exc:
        log.warning("Database not reachable, serving the saved snapshot: %s", exc)
        if SNAPSHOT_PATH.exists():
            data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            data["meta"]["source"] = "saved snapshot (database unreachable)"
            return data
        return JSONResponse({"error": "database unreachable and no snapshot"}, status_code=503)


# Static files last, so /api/* routes are matched first
app.mount("/", StaticFiles(directory=str(SNAPSHOT_PATH.parent.parent), html=True), name="static")

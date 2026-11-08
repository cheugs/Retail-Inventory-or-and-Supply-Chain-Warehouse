"""Save the dashboard data to dashboard/static/data/snapshot.json.

The online demo is a static website: it reads this file instead of calling the
database. Run it after the pipeline:  python -m dashboard.export_snapshot
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).resolve().parent / "static" / "data" / "snapshot.json"
log = logging.getLogger("export")


def export_snapshot(path: Path = SNAPSHOT_PATH) -> Path:
    # imported here so that the dashboard server (which only needs SNAPSHOT_PATH)
    # does not depend on the pipeline package
    from dashboard.queries import build_snapshot
    from retail_pipeline.db import connect

    with connect() as conn:
        snapshot = build_snapshot(conn)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf-8")
    log.info("Dashboard snapshot written to %s (%.0f KB)", path, path.stat().st_size / 1024)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    export_snapshot()

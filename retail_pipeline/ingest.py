"""Ingestion: load one day of source files into the raw schema.

Main rules:
  * One batch = one day folder. The whole batch is loaded in ONE transaction:
    either every file of the day is in the warehouse, or none is.
  * Loads are idempotent: the rows of the batch are deleted before being inserted
    again, so re-running a day (retry, replay, backfill) never creates duplicates.
  * Schema evolution: missing optional columns become NULL, unknown new columns
    are ignored and written in audit.load_log, and a missing mandatory column
    stops the load with a clear error (better to stop than to load wrong data).
  * The source control totals (_manifest.json) are stored in audit.source_manifest
    so the reconciliation step can compare them with what was loaded.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from retail_pipeline.config import settings
from retail_pipeline.db import connect, new_run_id, track_step

log = logging.getLogger("ingest")

# For each source file: the raw table columns (in order) and the mandatory ones.
# Optional columns may be absent from older files (for example "channel").
ENTITIES: dict[str, dict] = {
    "stores": {
        "columns": ["store_id", "store_name", "city", "country", "currency", "region", "manager_name", "updated_at"],
        "required": ["store_id", "currency", "updated_at"],
    },
    "suppliers": {
        "columns": ["supplier_id", "supplier_name", "country", "city", "promised_lead_time_days", "updated_at"],
        "required": ["supplier_id", "updated_at"],
    },
    "products": {
        "columns": ["product_id", "sku", "product_name", "category", "subcategory", "brand", "supplier_id",
                    "unit_cost", "unit_price", "currency", "is_active", "updated_at"],
        "required": ["product_id", "unit_cost", "unit_price", "updated_at"],
    },
    "fx_rates": {
        "columns": ["rate_date", "currency", "rate_to_eur"],
        "required": ["rate_date", "currency", "rate_to_eur"],
    },
    "sales": {
        "columns": ["sale_line_id", "receipt_id", "store_id", "product_id", "sold_at", "quantity",
                    "unit_price", "discount_amount", "currency", "channel"],
        "required": ["sale_line_id", "store_id", "product_id", "sold_at", "quantity", "unit_price", "currency"],
    },
    "inventory": {
        "columns": ["snapshot_date", "store_id", "product_id", "on_hand_qty"],
        "required": ["snapshot_date", "store_id", "product_id", "on_hand_qty"],
    },
    "purchase_orders": {
        "columns": ["po_line_id", "po_id", "supplier_id", "store_id", "product_id", "order_date",
                    "promised_date", "qty_ordered", "unit_cost"],
        "required": ["po_line_id", "supplier_id", "product_id", "order_date", "promised_date", "qty_ordered"],
    },
    "deliveries": {
        "columns": ["delivery_id", "po_line_id", "store_id", "received_date", "qty_received"],
        "required": ["delivery_id", "po_line_id", "received_date", "qty_received"],
    },
}


class SchemaError(Exception):
    """A file does not have a mandatory column: we refuse to load it."""


def check_header(entity: str, header: list[str]) -> tuple[list[str], list[str]]:
    """Compare a file header with the expected schema.

    Returns (columns_to_load, unknown_columns). Raises SchemaError if a mandatory
    column is missing.
    """
    spec = ENTITIES[entity]
    missing = [c for c in spec["required"] if c not in header]
    if missing:
        raise SchemaError(f"{entity}: mandatory column(s) missing: {', '.join(missing)}")
    unknown = [c for c in header if c not in spec["columns"]]
    return spec["columns"], unknown


def read_rows(path: Path, entity: str) -> tuple[list[str], list[str], list]:
    """Read a CSV file. Returns (columns, unknown_columns, rows) where each row is
    ordered like the raw table (absent columns -> None) with its line number."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        columns, unknown = check_header(entity, header)
        position = {name: i for i, name in enumerate(header)}
        index = [position.get(c) for c in columns]
        rows = []
        for row_number, values in enumerate(reader, start=1):
            # Empty strings become NULL, which is how a missing value is represented
            rows.append(([(values[i] or None) if i is not None and i < len(values) else None for i in index],
                         row_number))
    return columns, unknown, rows


def ingest_batch(batch_date: date, run_id: str | None = None, landing_dir: Path | None = None,
                 fail_after: str | None = None) -> int:
    """Load every file of one day. Returns the number of rows loaded.

    `fail_after` is only used by the tests: it simulates a crash after a given
    file to prove that a half-loaded batch is rolled back.
    """
    run_id = run_id or new_run_id()
    landing_dir = landing_dir or settings.landing_dir
    day_dir = landing_dir / batch_date.isoformat()
    manifest_path = day_dir / "_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No export for {batch_date}: {manifest_path} not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    total = 0
    log_rows = []
    with track_step(run_id, "ingest", batch_date) as step, connect() as conn:
        # All files of the batch in one transaction (psycopg opens it automatically)
        for entity in ENTITIES:
            path = day_dir / f"{entity}.csv"
            started = datetime.now(timezone.utc)
            conn.execute(f"DELETE FROM raw.{entity} WHERE _batch_date = %s", (batch_date,))
            if not path.exists():
                log_rows.append((run_id, batch_date, entity, path.name, 0, None, "missing", None, started))
                continue
            columns, unknown, rows = read_rows(path, entity)
            if unknown:
                log.warning("%s %s: unknown column(s) ignored: %s", batch_date, entity, unknown)
            n = 0
            copy_sql = (f"COPY raw.{entity} ({', '.join(columns)}, _batch_date, _file_name, _row_number) "
                        "FROM STDIN")
            with conn.cursor().copy(copy_sql) as copy:
                for values, row_number in rows:
                    copy.write_row(values + [batch_date, f"{batch_date}/{path.name}", row_number])
                    n += 1
            total += n
            log_rows.append((run_id, batch_date, entity, path.name, n,
                             ",".join(unknown) or None, "success", None, started))
            log.info("%s %-16s %7d rows", batch_date, entity, n)
            if fail_after == entity:
                raise RuntimeError(f"simulated crash after loading {entity}")

        # Source control totals, replaced if the batch is loaded again
        conn.execute("DELETE FROM audit.source_manifest WHERE batch_date = %s", (batch_date,))
        for entity, entry in manifest["files"].items():
            measure = next((k for k in entry if k.startswith("sum_")), None)
            conn.execute(
                "INSERT INTO audit.source_manifest (batch_date, entity, row_count, measure_name, measure_sum) "
                "VALUES (%s, %s, %s, %s, %s)",
                (batch_date, entity, entry["row_count"], measure[4:] if measure else None,
                 entry.get(measure) if measure else None),
            )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO audit.load_log (run_id, batch_date, entity, file_name, rows_loaded, "
                "unknown_columns, status, error, started_at, finished_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
                log_rows,
            )
        conn.commit()
        step["rows"] = total
    return total


def available_batches(landing_dir: Path | None = None) -> list[date]:
    """Every day folder that contains a manifest, in date order."""
    landing_dir = landing_dir or settings.landing_dir
    days = []
    for p in sorted(landing_dir.glob("????-??-??")):
        if (p / "_manifest.json").exists():
            days.append(date.fromisoformat(p.name))
    return days


def main() -> None:
    parser = argparse.ArgumentParser(description="Load source files into the raw schema")
    parser.add_argument("--date", help="batch date YYYY-MM-DD (default: every available day)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    run_id = new_run_id()
    days = [date.fromisoformat(args.date)] if args.date else available_batches()
    for d in days:
        ingest_batch(d, run_id)


if __name__ == "__main__":
    main()

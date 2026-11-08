"""Integration and end-to-end tests on a real PostgreSQL database.

They follow the life of the warehouse day after day, in order:
  1. load the first days, build, check the results,
  2. prove that loads are idempotent and that a crash loses nothing,
  3. inject hand-made "difficult" records (late sale, early-arriving product,
     duplicate, late catalog update) and check how each one is handled,
  4. replay the whole history and compare with the incremental result,
  5. compare the dashboard figures with the database.

Run with:  pytest -m integration   (needs the PostgreSQL container, see README)
The tests use their own database (retail_test), never the real warehouse.
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import psycopg
import pytest

from retail_pipeline.config import settings

pytestmark = pytest.mark.integration

START = date(2026, 1, 1)
DAYS = 62
DAY = lambda n: START + timedelta(days=n)  # noqa: E731  day number -> date


# ----------------------------------------------------------------- helpers
def admin_dsn() -> str:
    return settings.dsn.replace(f"dbname={settings.pg_db}", "dbname=postgres")


def query(sql: str, params=None):
    with psycopg.connect(settings.dsn) as conn:
        return conn.execute(sql, params).fetchall()


def scalar(sql: str, params=None):
    return query(sql, params)[0][0]


def append_rows(day: date, entity: str, rows: list[dict]) -> None:
    """Add hand-made rows to a source file and keep its manifest consistent."""
    from retail_pipeline.ingest import ENTITIES

    folder = settings.landing_dir / day.isoformat()
    path = folder / f"{entity}.csv"
    header, existing = ENTITIES[entity]["columns"], []
    if path.exists():   # some days have no file for an entity (no catalog change that day)
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header, existing = reader.fieldnames, list(reader)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(existing + [{k: r.get(k, "") for k in header} for r in rows])
    manifest_path = folder / "_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = manifest["files"].setdefault(entity, {"row_count": 0})
    entry["row_count"] += len(rows)
    for key in [k for k in entry if k.startswith("sum_")]:
        entry[key] = round(entry[key] + sum(float(r[key[4:]]) for r in rows), 2)
    manifest_path.write_text(json.dumps(manifest))


# ----------------------------------------------------------------- fixture
@pytest.fixture(scope="module")
def warehouse():
    """Fresh test database + small simulated company (3 stores, 16 products, 62 days)."""
    try:
        with psycopg.connect(admin_dsn(), autocommit=True, connect_timeout=3) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {settings.pg_db} WITH (FORCE)")
            conn.execute(f"CREATE DATABASE {settings.pg_db}")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")

    from retail_pipeline.db import init_database
    from retail_pipeline.generate import generate

    init_database()
    if settings.landing_dir.exists():
        shutil.rmtree(settings.landing_dir)
    generate(settings.landing_dir, START, DAYS, n_stores=3, n_products=16, n_suppliers=4, seed=3)
    return settings.landing_dir


def build():
    from retail_pipeline.run import run_dbt
    run_dbt("test", "build")


def ingest_days(first: int, last: int):
    from retail_pipeline.ingest import ingest_batch
    for n in range(first, last + 1):
        ingest_batch(DAY(n), run_id="test")


# ----------------------------------------------------------------- 1. first load
def test_first_load_and_build(warehouse):
    ingest_days(0, 54)
    build()   # dbt build fails if any dbt test fails
    assert scalar("select count(*) from marts.fct_sales") > 3000
    assert scalar("select count(*) from marts.dim_product where product_key <> '-1'") >= 16


def test_reconciliation_passes(warehouse):
    from retail_pipeline.reconcile import run_reconciliation
    result = run_reconciliation("test")
    assert result["failed"] == 0 and result["passed"] >= 10


def test_every_sale_line_counted_once(warehouse):
    total, distinct = query("select count(*), count(distinct sale_line_id) from marts.fct_sales")[0]
    assert total == distinct


def test_duplicates_do_not_inflate_amounts(warehouse):
    # units expected = valid raw lines, counting each sale_line_id once
    expected = scalar("""
        select sum(quantity) from (
            select distinct on (sale_line_id) quantity
            from staging.stg_sales_checked
            where rule_violation is null
            order by sale_line_id, _loaded_at, _batch_date, _row_number
        ) x
    """)
    assert scalar("select sum(quantity) from marts.fct_sales") == expected
    assert scalar("select count(*) from quarantine.rejected_sales where rejection_reason = 'duplicate_sale_line_id'") > 0


def test_invalid_rows_are_isolated_with_a_reason(warehouse):
    reasons = {r[0] for r in query("select distinct rejection_reason from quarantine.rejected_sales")}
    assert reasons and None not in reasons
    assert scalar("select count(*) from marts.fct_sales where quantity <= 0 or unit_price_local < 0") == 0


def test_amounts_are_converted_to_eur(warehouse):
    # CHF lines use the CHF rate of the sale day, EUR lines a rate of 1
    rows = query("""
        select f.currency, f.rate_to_eur, fx.rate_to_eur
        from marts.fct_sales f
        join staging.stg_fx_rates fx on fx.rate_date = cast(f.sold_at as date) and fx.currency = f.currency
        limit 500
    """)
    assert rows
    for currency, used, expected in rows:
        assert used == expected
        if currency == "EUR":
            assert used == 1


# ----------------------------------------------------------------- 2. reliability
def test_reloading_a_day_is_idempotent(warehouse):
    from retail_pipeline.ingest import ingest_batch
    before = scalar("select count(*) from raw.sales")
    ingest_batch(DAY(10), run_id="test-reload")
    assert scalar("select count(*) from raw.sales") == before


def test_crash_during_a_batch_rolls_back_everything(warehouse):
    from retail_pipeline.ingest import ingest_batch
    with pytest.raises(RuntimeError, match="simulated crash"):
        ingest_batch(DAY(55), run_id="test-crash", fail_after="sales")
    # nothing of the day is visible: not even the files loaded before the crash
    assert scalar("select count(*) from raw.sales where _batch_date = %s", (DAY(55),)) == 0
    assert scalar("select count(*) from raw.products where _batch_date = %s", (DAY(55),)) == 0
    assert scalar("select status from audit.pipeline_runs where run_id = 'test-crash'") == "failed"
    # the retry loads the whole day
    assert ingest_batch(DAY(55), run_id="test-retry") > 0
    assert scalar("select count(*) from raw.sales where _batch_date = %s", (DAY(55),)) > 0


def test_file_with_missing_mandatory_column_is_refused(warehouse, tmp_path):
    from retail_pipeline.ingest import SchemaError, ingest_batch
    broken = tmp_path / DAY(56).isoformat()
    shutil.copytree(settings.landing_dir / DAY(56).isoformat(), broken)
    lines = (broken / "sales.csv").read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    q = header.index("quantity")
    (broken / "sales.csv").write_text("\n".join(",".join(c for i, c in enumerate(l.split(",")) if i != q)
                                                for l in lines), encoding="utf-8")
    with pytest.raises(SchemaError):
        ingest_batch(DAY(56), run_id="test-schema", landing_dir=tmp_path)
    assert scalar("select count(*) from raw.sales where _batch_date = %s", (DAY(56),)) == 0


# ----------------------------------------------------------------- 3. difficult records
LATE_SALE = {"sale_line_id": "TEST-LATE-1", "receipt_id": "RT1", "store_id": "S01", "product_id": "P0001",
             "sold_at": f"{DAY(52)} 15:00:00", "quantity": "2", "unit_price": "5.00",
             "discount_amount": "0.00", "currency": "EUR", "channel": "store"}
EARLY_SALE = {"sale_line_id": "TEST-EARLY-1", "receipt_id": "RT2", "store_id": "S01", "product_id": "P9999",
              "sold_at": f"{DAY(57)} 11:00:00", "quantity": "1", "unit_price": "12.00",
              "discount_amount": "0.00", "currency": "EUR", "channel": "store"}
NEW_PRODUCT = {"product_id": "P9999", "sku": "SKU-TEST", "product_name": "Test lamp", "category": "Household",
               "subcategory": "Cleaning", "brand": "Optima", "supplier_id": "SUP01", "unit_cost": "6.00",
               "unit_price": "12.00", "currency": "EUR", "is_active": "true", "updated_at": f"{DAY(57)} 06:00:00"}


def test_inject_difficult_records(warehouse):
    # a sale from day 52 exported on day 57 (late), and a sale of a product whose
    # catalog row only arrives on day 58 (early-arriving fact), sent twice
    append_rows(DAY(57), "sales", [LATE_SALE, EARLY_SALE])
    append_rows(DAY(58), "sales", [EARLY_SALE])
    append_rows(DAY(58), "products", [NEW_PRODUCT])
    # price change of P0002 at noon on day 56, exported two days late (day 58)
    p2 = query("select sku, product_name, category, subcategory, brand, supplier_id, unit_cost_eur, unit_price_eur "
               "from marts.dim_product where product_id = 'P0002' and is_current")[0]
    append_rows(DAY(58), "products", [{
        "product_id": "P0002", "sku": p2[0], "product_name": p2[1], "category": p2[2], "subcategory": p2[3],
        "brand": p2[4], "supplier_id": p2[5], "unit_cost": f"{float(p2[6]) * 1.5:.2f}",
        "unit_price": f"{float(p2[7]) * 1.5:.2f}", "currency": "EUR", "is_active": "true",
        "updated_at": f"{DAY(56)} 12:00:00"}])
    ingest_days(56, 57)
    build()


def test_late_sale_lands_on_its_real_day(warehouse):
    row = query("select date_key, is_late_arrival, arrival_delay_days from marts.fct_sales "
                "where sale_line_id = 'TEST-LATE-1'")
    assert row == [(int(DAY(52).strftime("%Y%m%d")), True, 5)]


def test_early_sale_waits_on_the_unknown_product(warehouse):
    assert query("select product_key from marts.fct_sales where sale_line_id = 'TEST-EARLY-1'") == [("-1",)]


def test_next_run_fixes_early_sale_and_late_price_change(warehouse):
    ingest_days(58, DAYS - 1)
    build()
    # early-arriving fact: now linked to the real product, with its cost
    key, cost = query("select product_key, unit_cost_eur from marts.fct_sales where sale_line_id = 'TEST-EARLY-1'")[0]
    assert key != "-1" and float(cost) == 6.0
    # sent twice, counted once
    assert scalar("select count(*) from marts.fct_sales where sale_line_id = 'TEST-EARLY-1'") == 1
    # late catalog update: sales of P0002 after the change use the new version (SCD2)
    versions = query("select product_key, valid_from from marts.dim_product where product_id = 'P0002' order by valid_from")
    assert len(versions) >= 2
    wrong = scalar("""
        select count(*) from marts.fct_sales f
        join marts.dim_product p on p.product_key = f.product_key
        where f.product_id = 'P0002' and not (f.sold_at >= p.valid_from and f.sold_at < p.valid_to)
    """)
    assert wrong == 0


def test_schema_evolution_is_handled(warehouse):
    unknown = scalar("select string_agg(distinct unknown_columns, ',') from audit.load_log where entity = 'sales'")
    assert "loyalty_card" in unknown
    assert scalar("select count(*) from raw.sales where channel is not null") > 0
    assert scalar("select count(*) from marts.fct_sales where channel = 'click_collect'") > 0


def test_reconciliation_still_passes_after_incremental_runs(warehouse):
    from retail_pipeline.reconcile import run_reconciliation
    assert run_reconciliation("test")["failed"] == 0


# ----------------------------------------------------------------- 4. replay
def test_full_replay_gives_the_same_result(warehouse):
    from retail_pipeline.run import run_dbt
    sql = "select count(*), sum(net_amount_eur), sum(cost_amount_eur), count(distinct product_key) from marts.fct_sales"
    inv_sql = "select count(*), sum(on_hand_value_eur) from marts.fct_inventory_daily"
    incremental, incremental_inv = query(sql)[0], query(inv_sql)[0]
    run_dbt("test-replay", "build", full_refresh=True)
    assert query(sql)[0] == incremental
    assert query(inv_sql)[0] == incremental_inv


# ----------------------------------------------------------------- 5. dashboard
def test_dashboard_figures_match_the_database(warehouse):
    from fastapi.testclient import TestClient
    from dashboard import app as dashboard_app
    from dashboard.queries import build_snapshot

    with psycopg.connect(settings.dsn) as conn:
        snap = build_snapshot(conn)
    revenue = float(scalar("select round(sum(net_amount_eur), 0) from marts.fct_sales"))
    assert snap["kpis"]["revenue_eur"] == revenue
    assert snap["kpis"]["units_sold"] == scalar("select sum(quantity) from marts.fct_sales")
    assert snap["meta"]["sales_rows"] == scalar("select count(*) from marts.fct_sales")
    otif = float(scalar("select round(avg(case when is_otif then 1.0 else 0 end), 4) "
                        "from marts.fct_purchase_order_lines where is_evaluable"))
    assert snap["kpis"]["otif_rate"] == otif
    assert abs(sum(r["revenue_eur"] for r in snap["daily"]) - revenue) < 2

    client = TestClient(dashboard_app.app)
    response = client.get("/api/snapshot")
    assert response.status_code == 200
    assert response.json()["kpis"]["revenue_eur"] == revenue

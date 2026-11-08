-- ============================================================================
-- Raw layer and audit tables.
-- Runs once when the PostgreSQL container is created (docker-entrypoint-initdb.d)
-- and can be run again safely (IF NOT EXISTS everywhere).
--
-- Raw tables keep the source values as TEXT, exactly as they were in the files.
-- This way a badly formatted value never makes the load fail: it is loaded,
-- then detected and isolated by the dbt staging models (see dbt/models/staging).
-- Every raw row also keeps where it came from (_batch_date, _file_name,
-- _row_number) and when it was loaded (_loaded_at), so data stays traceable.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS audit;

-- ---------- raw layer (one table per source file) ----------

CREATE TABLE IF NOT EXISTS raw.products (
    product_id text, sku text, product_name text, category text, subcategory text,
    brand text, supplier_id text, unit_cost text, unit_price text, currency text,
    is_active text, updated_at text,
    _batch_date date NOT NULL, _file_name text NOT NULL, _row_number int NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.suppliers (
    supplier_id text, supplier_name text, country text, city text,
    promised_lead_time_days text, updated_at text,
    _batch_date date NOT NULL, _file_name text NOT NULL, _row_number int NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.stores (
    store_id text, store_name text, city text, country text, currency text,
    region text, manager_name text, updated_at text,
    _batch_date date NOT NULL, _file_name text NOT NULL, _row_number int NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.sales (
    sale_line_id text, receipt_id text, store_id text, product_id text, sold_at text,
    quantity text, unit_price text, discount_amount text, currency text,
    channel text,   -- added by the source during the period (schema evolution)
    _batch_date date NOT NULL, _file_name text NOT NULL, _row_number int NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.inventory (
    snapshot_date text, store_id text, product_id text, on_hand_qty text,
    _batch_date date NOT NULL, _file_name text NOT NULL, _row_number int NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.purchase_orders (
    po_line_id text, po_id text, supplier_id text, store_id text, product_id text,
    order_date text, promised_date text, qty_ordered text, unit_cost text,
    _batch_date date NOT NULL, _file_name text NOT NULL, _row_number int NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.deliveries (
    delivery_id text, po_line_id text, store_id text, received_date text, qty_received text,
    _batch_date date NOT NULL, _file_name text NOT NULL, _row_number int NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.fx_rates (
    rate_date text, currency text, rate_to_eur text,
    _batch_date date NOT NULL, _file_name text NOT NULL, _row_number int NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

-- Indexes on the batch date: a re-load deletes one batch before inserting it again
-- (idempotent loads), and incremental dbt models filter on _loaded_at.
CREATE INDEX IF NOT EXISTS ix_raw_sales_batch ON raw.sales (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_sales_loaded ON raw.sales (_loaded_at);
CREATE INDEX IF NOT EXISTS ix_raw_inventory_batch ON raw.inventory (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_inventory_loaded ON raw.inventory (_loaded_at);
CREATE INDEX IF NOT EXISTS ix_raw_po_batch ON raw.purchase_orders (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_deliveries_batch ON raw.deliveries (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_products_batch ON raw.products (_batch_date);

-- ---------- audit layer (monitoring and reconciliation) ----------

-- One row per file loaded (or rejected) by the ingestion step
CREATE TABLE IF NOT EXISTS audit.load_log (
    load_id      bigserial PRIMARY KEY,
    run_id       text NOT NULL,
    batch_date   date NOT NULL,
    entity       text NOT NULL,
    file_name    text NOT NULL,
    rows_loaded  int,
    unknown_columns text,          -- columns present in the file but unknown to the warehouse
    status       text NOT NULL,    -- success / failed / missing
    error        text,
    started_at   timestamptz NOT NULL,
    finished_at  timestamptz
);

-- Control totals sent by the source system with each daily export (_manifest.json)
CREATE TABLE IF NOT EXISTS audit.source_manifest (
    batch_date   date NOT NULL,
    entity       text NOT NULL,
    row_count    int NOT NULL,
    measure_name text,
    measure_sum  numeric,
    loaded_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_date, entity)
);

-- Result of every reconciliation check (source totals vs warehouse totals)
CREATE TABLE IF NOT EXISTS audit.reconciliation (
    check_id     bigserial PRIMARY KEY,
    run_id       text NOT NULL,
    checked_at   timestamptz NOT NULL DEFAULT now(),
    check_name   text NOT NULL,
    scope        text NOT NULL,
    expected     numeric,
    actual       numeric,
    difference   numeric,
    status       text NOT NULL     -- pass / fail
);

-- One row per pipeline step, to follow durations, volumes and failures
CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    id           bigserial PRIMARY KEY,
    run_id       text NOT NULL,
    step         text NOT NULL,
    batch_date   date,
    status       text NOT NULL,    -- running / success / failed
    rows_processed bigint,
    message      text,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    duration_s   numeric
);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started ON audit.pipeline_runs (started_at DESC);

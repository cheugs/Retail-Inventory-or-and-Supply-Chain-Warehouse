# Quality and acceptance checklist (DE02)

[Version française](../CHECKLIST.md)

The DE02 checklist was written for a **real-time** financial transaction platform (Kafka, Spark).
This project is a **batch data warehouse** for retail (Python, dbt, Airflow, PostgreSQL). Each item is
therefore translated to its batch equivalent and linked to its proof in the code. When an item does
not make sense here (for example Kafka consumer lag), this is said clearly, with the chosen equivalent.

Legend: **Yes** = done and tested · **Adapted** = batch equivalent of the item · **Partial** = partly done, limit explained

## Mapping from streaming to batch notions

| Checklist notion (streaming) | Equivalent in this project (batch) |
|---|---|
| Transaction | Till receipt line (`sale_line_id`), but also stock count, order line, delivery |
| Kafka ingestion | Daily files dropped by the source systems + manifest, loaded by `retail_pipeline/ingest.py` |
| Continuous Spark processing | Daily run orchestrated by Airflow (`catchup`), incremental dbt models |
| Event time / processing time | `sold_at` (time of sale) / `_batch_date` and `_loaded_at` (time the row arrives) |
| Watermark for late events | Rows re-processed: new since last run, changed products, unknown products, plus a 3-day window |
| Kafka consumer lag | Arrival delay of rows (`arrival_delay_days`) and duration of each step (`audit.pipeline_runs`) |
| Checkpoints | Incremental state = `max(_loaded_at)` of the fact tables; loading one day = one transaction |
| Event replay | Reload of one day, Airflow backfill, or full rebuild from the raw layer (`replay`) |
| Simulated fraud indicators | Simulated anomaly indicators: unexplained stock drop, abnormal till price |

## 1. Functional correctness

| Item | Status | Proof |
|---|---|---|
| Realistic transaction attributes | Yes | `generate.py`: prices per category, 30-90% markup, weekly seasonality, promotions, discounts. Test `test_sales_have_realistic_values` |
| Unique identifier per transaction | Yes | `sale_line_id`; dbt `unique` test on `fct_sales.sale_line_id`, `test_every_sale_line_counted_once` |
| Valid amounts, currencies, timestamps | Yes | Rules in `stg_sales_checked.sql` (quantity > 0, price >= 0, known currency, readable timestamp not in the future) |
| Events are ingested | Adapted | Files loaded with COPY into `raw.*`, logged in `audit.load_log`, row-by-row check against the manifest |
| Continuous processing | Adapted | Daily Airflow DAG `retail_warehouse_daily` (see section 3) |
| Mathematically correct aggregations | Yes | dbt test `assert_mart_sales_matches_fact`, check `revenue_mart_vs_fact` in `reconcile.py` |
| PostgreSQL stores expected results | Yes | Integration tests on a real database (`tests/integration`) |
| Dashboard matches the database | Yes | `test_dashboard_figures_match_the_database` (KPIs, rows, OTIF, FastAPI endpoint) |

## 2. Data quality and integrity

| Item | Status | Proof |
|---|---|---|
| Missing mandatory fields detected | Yes | Reasons `missing_sale_line_id`, `missing_store_id`, `missing_product_id`, `missing_key`; missing mandatory column: `SchemaError` |
| Invalid amounts rejected | Yes | `invalid_quantity`, `invalid_price` |
| Invalid timestamps handled | Yes | `invalid_timestamp`, `future_timestamp`, `invalid_date` (`try_cast` macro + `pg_input_is_valid`) |
| Duplicate ids detected | Yes | `duplicate_sale_line_id`, `duplicate_po_line_id`, `duplicate_delivery_id`, `replaced_by_newer_count` |
| Duplicates do not inflate amounts | Yes | `test_duplicates_do_not_inflate_amounts`; a line sent twice is counted once |
| Invalid records isolated | Yes | `quarantine` schema (4 tables) with the reason and the raw row |
| Integrity preserved by transformations | Yes | Test `assert_every_raw_sale_is_accounted_for`: raw = facts + quarantine; `assert_sales_amounts_are_consistent` |
| Quality rules tested automatically | Yes | 48 dbt tests at every `dbt build`, plus pytest |

## 3. Late data handling (equivalent of real-time processing)

| Item | Status | Proof |
|---|---|---|
| No manual batch execution | Adapted | Airflow schedules one run per day; sensor `wait_for_source_files` |
| Event time vs processing time | Yes | `sold_at` vs `_batch_date` / `_loaded_at`; columns `arrival_delay_days`, `is_late_arrival` |
| Out-of-order events | Yes | SCD2 history rebuilt from every received row, ordered by `updated_at`; late catalog update tested |
| Late events (watermark) | Adapted | Incremental filter of `fct_sales` (new rows, changed products, unknown product, `lookback_days` window); `test_late_sale_lands_on_its_real_day` |
| Accurate window aggregations | Adapted | Daily and monthly aggregations (`mart_*`), checked against the facts |
| Latency measurable | Adapted | Duration of each step in `audit.pipeline_runs`; arrival delay of rows |
| Throughput measurable | Yes | `benchmarks/run_benchmark.py` (rows/s) |
| Lag observable | Adapted | No Kafka: data lateness (`arrival_delay_days`) and freshness (`loaded_at_field` on dbt sources) |

## 4. Reliability and fault tolerance

| Item | Status | Proof |
|---|---|---|
| Recovery after restart | Yes | Every step is idempotent: a restarted run continues without side effects |
| Checkpoints preserve progress | Adapted | Incremental state stored in the fact tables; Airflow keeps the state of each day |
| Failed attempts can be retried | Yes | `retries: 2` in the DAG; `test_crash_during_a_batch_rolls_back_everything` (successful retry) |
| Duplicate processing does not corrupt results | Yes | Load: delete then insert the batch; facts: `delete+insert` on the key; `test_reloading_a_day_is_idempotent` |
| Historical replay | Yes | `python -m retail_pipeline.run replay`; `test_full_replay_gives_the_same_result` |
| No silent loss on recovery | Yes | One batch = one transaction (all or nothing) + reconciliation with the source manifest |
| Schema changes handled | Yes | Missing optional column = NULL, unknown column ignored and logged, missing mandatory column = stop; unit and integration tests |
| Delivery guarantees documented and tested | Yes | "Exactly once" at the result level: see README section 8, idempotency and duplicate tests |

## 5. Data architecture

| Item | Status | Proof |
|---|---|---|
| Clear responsibilities | Yes | Generator, ingestion, dbt, reconciliation, export, dashboard: one module each |
| Kafka topics and partitions | Not applicable | No Kafka. Equivalent: one file per entity and per day, one raw table per entity, index on `_batch_date` |
| Traceable flows | Yes | `_batch_date`, `_file_name`, `_row_number` kept up to `fct_sales.source_file` and in quarantine |
| Raw and transformed separated | Yes | Schemas `raw`, `staging`, `marts`, `quarantine`, `audit` |
| Well-structured tables | Yes | Star schema: 3 facts, 4 dimensions, surrogate keys, relationship tests |
| Justified indexes | Yes | Comments in `sql/01_raw_and_audit.sql` (batch reload, incremental filter) |
| Modular dbt | Yes | staging / intermediate / marts layers, cross-database macros |
| Extensible | Yes | Snowflake target in `profiles.yml`, `adapter.dispatch` macros, new source = one entry in `ENTITIES` + one staging model |

## 6. Performance and scalability

| Item | Status | Proof |
|---|---|---|
| At least 10,000 transactions | Yes | 10k benchmark and demo dataset (about 159,000 sales lines) |
| Tested with 100,000 | Yes | 100k benchmark |
| 1 million attempted | Yes | 1m benchmark (`benchmarks/results.md`) |
| Throughput in rows per second | Yes | "Rows/s" column of the benchmark |
| Latency measured | Adapted | Duration of ingestion, `dbt build` and reconciliation |
| Resources monitored | Partial | Database size and PostgreSQL container memory; no detailed CPU tracking |
| Bottlenecks identified | Yes | Slowest dbt models (from `run_results.json`) and analysis in README section 9 |
| Results documented | Yes | README section 9, `benchmarks/results.md` |

## 7. Monitoring and observability

| Item | Status | Proof |
|---|---|---|
| Ingestion monitored | Yes | `audit.load_log` (rows, unknown columns, status), "Quality and pipeline" page |
| Failures logged | Yes | `audit.pipeline_runs` (`failed` status + message), Python and Airflow logs |
| Lag monitored | Adapted | Arrival delay of rows (dashboard chart) |
| Processing delays monitored | Yes | Average duration per step |
| Duplicates counted | Yes | Quarantine, reason `duplicate_*` |
| Invalid rows counted | Yes | Quarantine, per reason |
| Recovery traceable | Yes | Each attempt has its `run_id`; `failed` then `success` rows stay visible |
| Logs good enough to investigate | Yes | Batch, file and line number kept for every row; reconciliation gaps detailed per day |

## 8. Business analytics (equivalent of financial analytics)

| Item | Status | Proof |
|---|---|---|
| Volumes | Yes | Units sold, lines, orders |
| Total amounts | Yes | Revenue, cost, margin (EUR) |
| Distribution by status | Yes | Order line status (complete, partial, overdue, open) |
| Volumes by time window | Yes | Per day, per weekday, per month |
| Currency differences | Yes | Swiss stores in CHF, converted at the daily rate (`test_amounts_are_converted_to_eur`) |
| Simulated suspicious-activity indicators | Adapted | `mart_anomaly_indicators`: unexplained stock drop, price deviation |
| Explainable rules | Yes | The rule is written in the `rule` column of each row |
| No claim of real detection | Yes | Stated in the model, the dashboard and the README |

## 9. Testing and validation

| Item | Status | Proof |
|---|---|---|
| Unit tests | Yes | `tests/unit` (generator, file schema, project files) |
| Integration tests | Yes | `tests/integration` (real PostgreSQL + dbt) |
| End-to-end tests | Yes | Generate -> ingest -> dbt -> reconcile -> dashboard; CI step `run all` |
| Duplicate scenarios | Yes | `test_duplicates_do_not_inflate_amounts` |
| Late scenarios | Yes | `test_late_sale_lands_on_its_real_day` |
| Out-of-order scenarios | Yes | Price change dated day 56 received on day 58 |
| Application failure | Yes | `test_crash_during_a_batch_rolls_back_everything` |
| Replay | Yes | `test_full_replay_gives_the_same_result` |
| Schema evolution | Yes | `test_schema_evolution_is_handled`, `test_file_with_missing_mandatory_column_is_refused` |
| Dashboard validated against the database | Yes | `test_dashboard_figures_match_the_database` |

## 10. Engineering quality

| Item | Status | Proof |
|---|---|---|
| Modular, maintainable code | Yes | One module per step, code commented in English |
| Externalized configuration | Yes | `.env` / environment variables, dbt `vars` |
| No secrets on GitHub | Yes | `.env` ignored, only `.env.example`; test `test_no_password_written_in_config_files` |
| Reproducible Docker services | Yes | `docker-compose.yml`, pinned image versions |
| CI runs the tests | Yes | `.github/workflows/ci.yml` (PostgreSQL service) |
| README explains the architecture | Yes | Sections 4 and 5 |
| Decisions and trade-offs documented | Yes | Section 8 |
| Known limitations | Yes | Section 14 |
| Reproducible by another developer | Yes | Section 13 (Docker or Python only) |

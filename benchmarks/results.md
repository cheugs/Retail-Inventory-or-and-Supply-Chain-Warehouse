# Benchmark results

Machine: Windows 11, 12 CPU threads, PostgreSQL 16 in Docker  
Date: 2026-11-08T18:53

| Size | Sales lines | All source rows | Ingestion (s) | dbt build (s) | Reconciliation (s) | Total (s) | Rows/s end to end | Reconciliation | DB size | PostgreSQL memory |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| 10k | 12,483 | 21,294 | 27.7 | 18.1 | 0.2 | 46.0 | 463 | pass | 19 MB | 285.3MiB |
| 100k | 101,833 | 160,497 | 39.1 | 47.5 | 2.5 | 89.1 | 1,800 | pass | 77 MB | 286.8MiB |
| 1m | 1,026,066 | 1,629,463 | 125.2 | 383.4 | 4.3 | 512.9 | 3,177 | pass | 896 MB | 837.5MiB |

Slowest dbt models (bottlenecks):

- 10k: rejected_purchase_orders (2.0 s), dim_product (2.0 s), rejected_sales (1.8 s)
- 100k: fct_sales (29.8 s), int_store_product_daily (2.9 s), rejected_sales (2.2 s)
- 1m: int_store_product_daily (166.4 s), mart_daily_sales (103.8 s), fct_sales (85.8 s)

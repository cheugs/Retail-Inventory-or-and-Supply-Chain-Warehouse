# Connecting Power BI to the warehouse

[Version française](../POWERBI.md)

The `marts` schema is designed to be read directly by Power BI: a star schema with surrogate keys,
already cleaned and tested. This repository has no `.pbix` file (a binary format, hard to review in
Git); this guide describes the model to rebuild.

## 1. Connection

1. Power BI Desktop > **Get data** > **PostgreSQL database**.
2. Server: `localhost:5433`, database: `retail_dw` (values from the `.env` file).
3. **Import** mode (data changes once a day).
4. Select from the `marts` schema: `fct_sales`, `fct_inventory_daily`, `fct_purchase_order_lines`,
   `dim_product`, `dim_store`, `dim_supplier`, `dim_date`.

## 2. Relationships (Model view)

| Fact table | Column | Dimension | Column | Cardinality |
|---|---|---|---|---|
| fct_sales | date_key | dim_date | date_key | many to one |
| fct_sales | product_key | dim_product | product_key | many to one |
| fct_sales | store_key | dim_store | store_key | many to one |
| fct_inventory_daily | date_key | dim_date | date_key | many to one |
| fct_inventory_daily | product_key | dim_product | product_key | many to one |
| fct_inventory_daily | store_key | dim_store | store_key | many to one |
| fct_purchase_order_lines | order_date_key | dim_date | date_key | many to one |
| fct_purchase_order_lines | supplier_key | dim_supplier | supplier_key | many to one |
| fct_purchase_order_lines | product_key | dim_product | product_key | many to one |

Single-direction filtering (dimension to fact). `dim_product` has one row per **version** of a
product (SCD type 2): to filter "the product" regardless of versions, use the `product_id` column.

## 3. DAX measures

```DAX
Revenue       = SUM ( fct_sales[net_amount_eur] )
COGS          = SUM ( fct_sales[cost_amount_eur] )
Margin rate   = DIVIDE ( [Revenue] - [COGS], [Revenue] )

Stockout rate =
DIVIDE (
    CALCULATE ( COUNTROWS ( fct_inventory_daily ), fct_inventory_daily[is_stockout] = TRUE () ),
    COUNTROWS ( fct_inventory_daily )
)

Average stock (EUR) =
AVERAGEX ( VALUES ( dim_date[date_day] ), CALCULATE ( SUM ( fct_inventory_daily[on_hand_value_eur] ) ) )

Annualized turnover =
DIVIDE ( [COGS], [Average stock (EUR)] ) * DIVIDE ( 365, DISTINCTCOUNT ( fct_inventory_daily[snapshot_date] ) )

OTIF =
CALCULATE (
    AVERAGEX ( fct_purchase_order_lines, IF ( fct_purchase_order_lines[is_otif], 1, 0 ) ),
    fct_purchase_order_lines[is_evaluable] = TRUE ()
)
```

These measures give the same values as the web dashboard (same definitions as `dashboard/queries.py`).

## 4. Suggested pages

1. **Stockouts**: stockout rate per day (line), by category and store (bars), top products (table).
2. **Suppliers**: OTIF per supplier (bars), promised vs actual lead time, order status.
3. **Turnover**: annualized turnover and days of inventory by category, stock value per day.

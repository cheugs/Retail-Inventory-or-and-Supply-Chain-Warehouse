-- One row per product (current version) summarising the whole period:
-- sales, average stock, stockout days, days of cover and turnover.
-- Useful to find slow movers (too much stock) and products often out of stock.
with per_product as (
    select
        product_id,
        count(distinct snapshot_date)                     as days_observed,
        sum(units_sold)                                   as units_sold,
        sum(revenue_eur)                                  as revenue_eur,
        sum(case when is_stockout then 1 else 0 end)      as stockout_store_days,
        count(*)                                          as store_days,
        sum(on_hand_qty) * 1.0 / count(distinct snapshot_date) as avg_on_hand_units,
        sum(on_hand_value_eur) * 1.0 / count(distinct snapshot_date) as avg_inventory_value_eur
    from {{ ref('int_store_product_daily') }}
    group by 1
),
cogs as (
    select product_id, sum(cost_amount_eur) as cogs_eur
    from {{ ref('fct_sales') }}
    group by 1
)
select
    p.product_id,
    p.product_name,
    p.category,
    p.supplier_id,
    pp.days_observed,
    pp.units_sold,
    round(pp.revenue_eur, 2)                                        as revenue_eur,
    pp.stockout_store_days,
    round(pp.stockout_store_days * 1.0 / nullif(pp.store_days, 0), 4) as stockout_rate,
    round(pp.avg_on_hand_units, 1)                                  as avg_on_hand_units,
    -- days of cover: how many days the average stock lasts at the average sales pace
    round(pp.avg_on_hand_units / nullif(pp.units_sold * 1.0 / pp.days_observed, 0), 1) as days_of_cover,
    round(coalesce(c.cogs_eur, 0) / nullif(pp.avg_inventory_value_eur, 0) * 365.0 / pp.days_observed, 2) as annualized_turnover
from per_product pp
join {{ ref('dim_product') }} p on p.product_id = pp.product_id and p.is_current and p.product_key <> '-1'
left join cogs c on c.product_id = pp.product_id

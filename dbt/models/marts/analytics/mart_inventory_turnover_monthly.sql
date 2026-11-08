-- Inventory turnover by category and month.
--   turnover          = cost of goods sold / average inventory value (both in EUR at cost)
--   days of inventory = days in the period / turnover (how long the stock lasts)
-- The average inventory is the average of the daily end-of-day stock values.
with cogs as (
    select
        p.category,
        cast(date_trunc('month', f.sold_at) as date) as month_start,
        sum(f.cost_amount_eur)                       as cogs_eur
    from {{ ref('fct_sales') }} f
    join {{ ref('dim_product') }} p on p.product_key = f.product_key
    group by 1, 2
),

daily_stock as (
    select category, snapshot_date, sum(on_hand_value_eur) as stock_value_eur
    from {{ ref('int_store_product_daily') }}
    group by 1, 2
),

avg_stock as (
    select
        category,
        cast(date_trunc('month', snapshot_date) as date) as month_start,
        avg(stock_value_eur)                              as avg_inventory_value_eur,
        count(distinct snapshot_date)                     as days_in_period
    from daily_stock
    group by 1, 2
)

select
    a.category,
    a.month_start,
    a.days_in_period,
    round(coalesce(c.cogs_eur, 0), 2)                                  as cogs_eur,
    round(a.avg_inventory_value_eur, 2)                                as avg_inventory_value_eur,
    round(coalesce(c.cogs_eur, 0) / nullif(a.avg_inventory_value_eur, 0), 3) as turnover,
    round(a.days_in_period / nullif(coalesce(c.cogs_eur, 0) / nullif(a.avg_inventory_value_eur, 0), 0), 1) as days_of_inventory,
    -- turnover scaled to one year, to compare months of different lengths
    round(coalesce(c.cogs_eur, 0) / nullif(a.avg_inventory_value_eur, 0) * 365.0 / a.days_in_period, 2) as annualized_turnover
from avg_stock a
left join cogs c on c.category = a.category and c.month_start = a.month_start

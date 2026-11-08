-- Stockout analysis by day, store and category.
--
-- A product is "out of stock" in a store when its end-of-day stock is 0.
-- Lost sales are an ESTIMATE: on a stockout day we assume the store would have
-- sold its usual quantity, i.e. the average units sold per day on the days the
-- product was available in that store.
with daily as (
    select
        *,
        avg(case when not is_stockout then units_sold end)
            over (partition by store_id, product_id) as avg_units_when_available,
        avg(case when units_sold > 0 then revenue_eur / units_sold end)
            over (partition by store_id, product_id) as avg_unit_revenue_eur
    from {{ ref('int_store_product_daily') }}
)
select
    snapshot_date,
    store_id,
    category,
    count(*)                                                as product_days,
    sum(case when is_stockout then 1 else 0 end)            as stockout_days,
    round(avg(case when is_stockout then 1.0 else 0.0 end), 4) as stockout_rate,
    round(sum(case when is_stockout then coalesce(avg_units_when_available, 0) else 0 end), 1) as est_lost_units,
    round(sum(case when is_stockout
                   then coalesce(avg_units_when_available, 0) * coalesce(avg_unit_revenue_eur, 0)
                   else 0 end), 2)                          as est_lost_revenue_eur
from daily
group by 1, 2, 3

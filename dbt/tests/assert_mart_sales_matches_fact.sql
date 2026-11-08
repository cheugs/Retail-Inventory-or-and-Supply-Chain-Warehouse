-- Aggregation check: the daily sales mart must add up to the sales fact.
with totals as (
    select
        (select round(sum(net_amount_eur), 2) from {{ ref('fct_sales') }})   as fact_revenue,
        (select round(sum(revenue_eur), 2) from {{ ref('mart_daily_sales') }}) as mart_revenue,
        (select sum(quantity) from {{ ref('fct_sales') }})                   as fact_units,
        (select sum(units_sold) from {{ ref('mart_daily_sales') }})          as mart_units
)
select *
from totals
where abs(fact_revenue - mart_revenue) > 0.05 or fact_units <> mart_units

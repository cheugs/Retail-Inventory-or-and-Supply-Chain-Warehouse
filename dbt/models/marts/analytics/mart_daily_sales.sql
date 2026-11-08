-- Daily sales by store and category, in EUR.
select
    f.date_key,
    cast(f.sold_at as date)             as sale_date,
    f.store_id,
    p.category,
    count(*)                            as sale_lines,
    sum(f.quantity)                     as units_sold,
    round(sum(f.net_amount_eur), 2)     as revenue_eur,
    round(sum(f.cost_amount_eur), 2)    as cost_eur,
    round(sum(f.net_amount_eur) - sum(f.cost_amount_eur), 2) as gross_margin_eur
from {{ ref('fct_sales') }} f
join {{ ref('dim_product') }} p on p.product_key = f.product_key
group by 1, 2, 3, 4

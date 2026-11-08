-- One row per store, product and day with everything the analyses need:
-- end-of-day stock, units sold, units received, and the previous day's stock.
-- Used by the stockout, turnover and anomaly marts.
with sales as (
    select store_id, product_id, cast(sold_at as date) as day,
           sum(quantity) as units_sold, sum(net_amount_eur) as revenue_eur
    from {{ ref('fct_sales') }}
    group by 1, 2, 3
),

received as (
    select po.store_id, po.product_id, d.received_date as day, sum(d.qty_received) as units_received
    from {{ ref('stg_deliveries_checked') }} d
    join {{ ref('stg_purchase_orders_checked') }} po
        on po.po_line_id = d.po_line_id and po.rejection_reason is null
    where d.rejection_reason is null
    group by 1, 2, 3
)

select
    i.snapshot_date,
    i.store_id,
    i.product_id,
    i.product_key,
    p.category,
    i.on_hand_qty,
    i.is_stockout,
    i.on_hand_value_eur,
    coalesce(s.units_sold, 0)      as units_sold,
    coalesce(s.revenue_eur, 0)     as revenue_eur,
    coalesce(r.units_received, 0)  as units_received,
    lag(i.on_hand_qty) over (partition by i.store_id, i.product_id order by i.snapshot_date) as previous_on_hand_qty,
    lag(i.snapshot_date) over (partition by i.store_id, i.product_id order by i.snapshot_date) as previous_snapshot_date
from {{ ref('fct_inventory_daily') }} i
left join {{ ref('dim_product') }} p on p.product_key = i.product_key
left join sales s
    on s.store_id = i.store_id and s.product_id = i.product_id and s.day = i.snapshot_date
left join received r
    on r.store_id = i.store_id and r.product_id = i.product_id and r.day = i.snapshot_date

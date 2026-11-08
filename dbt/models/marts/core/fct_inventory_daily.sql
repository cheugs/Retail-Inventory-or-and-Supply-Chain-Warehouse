-- Inventory fact table (periodic snapshot).
-- Grain: one row per store, product and day, with the stock at the end of the day.
-- INCREMENTAL on _loaded_at: a store file that arrives one day late is simply
-- added at the next run, at its own date. Rows of products whose catalog changed,
-- and rows on the "unknown" product, are re-processed too.
-- depends_on: {{ ref('stg_products') }}
-- (dbt hint: stg_products is only used inside the incremental block below)
{{
    config(
        materialized='incremental',
        unique_key='inventory_key',
        incremental_strategy='delete+insert'
    )
}}

with counts as (
    select *
    from {{ ref('stg_inventory_checked') }}
    where rejection_reason is null
    {% if is_incremental() %}
      and (
            _loaded_at > (select max(_loaded_at) from {{ this }})
         -- products whose catalog changed: the stock value uses the new cost
         or product_id in (select product_id from {{ ref('stg_products') }}
                           where _loaded_at > (select max(_loaded_at) from {{ this }}))
         or snapshot_date >= (select {{ dbt.dateadd('day', -var('lookback_days'), 'max(snapshot_date)') }} from {{ this }})
         or {{ surrogate_key(['snapshot_date', 'store_id', 'product_id']) }} in
            (select inventory_key from {{ this }} where product_key = '-1')
      )
    {% endif %}
)

select
    {{ surrogate_key(['c.snapshot_date', 'c.store_id', 'c.product_id']) }} as inventory_key,
    {{ date_key('c.snapshot_date') }}                as date_key,
    c.snapshot_date,
    st.store_key,
    coalesce(p.product_key, '-1')                    as product_key,
    c.store_id,
    c.product_id,
    c.on_hand_qty,
    c.on_hand_qty = 0                                as is_stockout,
    p.unit_cost_eur,
    round(c.on_hand_qty * p.unit_cost_eur, 2)        as on_hand_value_eur,
    c._batch_date                                    as batch_date,
    c._batch_date > c.snapshot_date                  as is_late_arrival,
    c._loaded_at
from counts c
join {{ ref('dim_store') }} st
    on st.store_id = c.store_id
left join {{ ref('dim_product') }} p
    on  p.product_id = c.product_id
    -- version valid at the end of the day
    and p.valid_from <  {{ dbt.dateadd('day', 1, 'c.snapshot_date') }}
    and p.valid_to   >= {{ dbt.dateadd('day', 1, 'c.snapshot_date') }}

-- Sales fact table. Grain: one row per receipt line (sale_line_id).
--
-- INCREMENTAL: a normal run only processes
--   1. the lines loaded since the last run (_loaded_at), which includes lines
--      that arrive late for an older day,
--   2. the lines of products whose catalog changed since the last run, so a
--      late price change is applied to the sales it concerns (SCD2 lookup again),
--   3. the lines still attached to the "unknown" product, to fix them as soon as
--      their catalog row has arrived (early-arriving facts),
--   4. the last N days (var lookback_days), as a safety net.
-- delete+insert on sale_line_id makes a re-run safe: a line is replaced, never doubled.
-- depends_on: {{ ref('stg_products') }}
-- (dbt hint: stg_products is only used inside the incremental block below)
{{
    config(
        materialized='incremental',
        unique_key='sale_line_id',
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

with sales as (
    select *
    from {{ ref('stg_sales_checked') }}
    where rejection_reason is null
    {% if is_incremental() %}
      and (
            _loaded_at > (select max(_loaded_at) from {{ this }})
         or product_id in (select product_id from {{ ref('stg_products') }}
                           where _loaded_at > (select max(_loaded_at) from {{ this }}))
         or sale_line_id in (select sale_line_id from {{ this }} where product_key = '-1')
         or sold_at >= (select {{ dbt.dateadd('day', -var('lookback_days'), 'max(sold_at)') }} from {{ this }})
      )
    {% endif %}
)

select
    s.sale_line_id,
    s.receipt_id,
    {{ date_key('s.sold_at') }}                         as date_key,
    s.sold_at,
    st.store_key,
    coalesce(p.product_key, '-1')                       as product_key,
    s.store_id,
    s.product_id,
    s.channel,
    s.currency,
    s.quantity,
    s.unit_price                                        as unit_price_local,
    s.quantity * s.unit_price                           as gross_amount_local,
    s.discount_amount                                   as discount_amount_local,
    s.quantity * s.unit_price - s.discount_amount       as net_amount_local,
    fx.rate_to_eur,
    round((s.quantity * s.unit_price - s.discount_amount) * fx.rate_to_eur, 2) as net_amount_eur,
    -- cost of the goods sold, at the cost valid when the sale happened (SCD2 lookup)
    p.unit_cost_eur,
    round(s.quantity * p.unit_cost_eur, 2)              as cost_amount_eur,
    p.unit_price_eur                                    as catalog_price_eur,
    -- traceability and late-arrival information
    s._batch_date                                       as batch_date,
    {{ dbt.datediff('cast(s.sold_at as date)', 's._batch_date', 'day') }} as arrival_delay_days,
    s._batch_date > cast(s.sold_at as date)             as is_late_arrival,
    s._file_name                                        as source_file,
    s._loaded_at
from sales s
join {{ ref('dim_store') }} st
    on st.store_id = s.store_id
left join {{ ref('dim_product') }} p
    on  p.product_id = s.product_id
    and s.sold_at >= p.valid_from
    and s.sold_at <  p.valid_to
-- rate of the sale day; if that day's rate is missing, the last known rate is used
left join {{ ref('stg_fx_rates') }} fx
    on  fx.currency  = s.currency
    and cast(s.sold_at as date) >= fx.rate_date
    and cast(s.sold_at as date) <  fx.valid_to

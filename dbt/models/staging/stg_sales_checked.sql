-- Every raw sales line, typed, with the result of the quality rules.
--   rejection_reason is NULL  -> the line is valid and goes to fct_sales
--   rejection_reason not NULL -> the line goes to quarantine.rejected_sales
-- A valid line that repeats an already seen sale_line_id is marked as a duplicate,
-- so a line sent twice is never counted twice in the revenue.
-- Materialized as a TABLE (not a view): it is read by the fact table, the quarantine
-- and several tests, so the deduplication over all raw rows is computed only once per run
-- (it was the main dbt bottleneck of the 1 million row benchmark).
{{ config(materialized='table') }}

with typed as (
    select
        sale_line_id,
        receipt_id,
        store_id,
        product_id,
        {{ try_cast('sold_at', 'timestamp') }}                   as sold_at,
        {{ try_cast('quantity', 'integer') }}                    as quantity,
        {{ try_cast('unit_price', 'numeric') }}                  as unit_price,
        coalesce({{ try_cast('discount_amount', 'numeric') }}, 0) as discount_amount,
        upper(trim(currency))                                    as currency,
        coalesce(channel, 'store')                               as channel,  -- column added later by the source
        quantity   as quantity_raw,
        _batch_date, _file_name, _row_number, _loaded_at
    from {{ source('raw', 'sales') }}
),

checked as (
    select
        t.*,
        case
            when t.sale_line_id is null                    then 'missing_sale_line_id'
            when t.store_id is null                        then 'missing_store_id'
            when t.product_id is null                      then 'missing_product_id'
            when t.sold_at is null                         then 'invalid_timestamp'
            when t.sold_at >= {{ dbt.dateadd('day', 1, 't._batch_date') }} then 'future_timestamp'
            when t.quantity is null or t.quantity <= 0     then 'invalid_quantity'
            when t.unit_price is null or t.unit_price < 0  then 'invalid_price'
            when s.store_id is null                        then 'unknown_store'
            when fx.currency is null                       then 'unknown_currency'
        end as rule_violation
    from typed t
    left join {{ ref('stg_stores') }} s on s.store_id = t.store_id
    left join (select distinct currency from {{ ref('stg_fx_rates') }}) fx on fx.currency = t.currency
),

valid_ranked as (
    -- first time we see an id = 1, every repeat > 1 (only among valid lines)
    select
        sale_line_id, _loaded_at, _batch_date, _row_number,
        row_number() over (partition by sale_line_id order by _loaded_at, _batch_date, _row_number) as occurrence
    from checked
    where rule_violation is null
)

select
    c.*,
    v.occurrence,
    case
        when c.rule_violation is not null then c.rule_violation
        when v.occurrence > 1 then 'duplicate_sale_line_id'
    end as rejection_reason
from checked c
left join valid_ranked v
    on  v.sale_line_id = c.sale_line_id
    and v._batch_date = c._batch_date
    and v._row_number = c._row_number
    and c.rule_violation is null

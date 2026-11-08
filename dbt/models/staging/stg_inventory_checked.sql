-- Every raw stock count, typed and checked. If the same (day, store, product)
-- count is received twice, the most recently loaded one is kept (a correction).
-- Materialized as a TABLE (not a view): it is read by the fact table, the quarantine
-- and several tests, so the deduplication over all raw rows is computed only once per run
-- (it was the main dbt bottleneck of the 1 million row benchmark).
{{ config(materialized='table') }}

with typed as (
    select
        {{ try_cast('snapshot_date', 'date') }}  as snapshot_date,
        store_id,
        product_id,
        {{ try_cast('on_hand_qty', 'integer') }} as on_hand_qty,
        on_hand_qty as on_hand_qty_raw,
        _batch_date, _file_name, _row_number, _loaded_at
    from {{ source('raw', 'inventory') }}
),
checked as (
    select
        *,
        case
            when store_id is null or product_id is null then 'missing_key'
            when snapshot_date is null                  then 'invalid_date'
            when on_hand_qty is null or on_hand_qty < 0 then 'invalid_quantity'
        end as rule_violation
    from typed
),
valid_ranked as (
    select
        _batch_date, _row_number,
        row_number() over (
            partition by snapshot_date, store_id, product_id
            order by _loaded_at desc, _batch_date desc, _row_number desc
        ) as recency_rank
    from checked
    where rule_violation is null
)
select
    c.*,
    case
        when c.rule_violation is not null then c.rule_violation
        when v.recency_rank > 1 then 'replaced_by_newer_count'
    end as rejection_reason
from checked c
left join valid_ranked v
    on v._batch_date = c._batch_date and v._row_number = c._row_number and c.rule_violation is null

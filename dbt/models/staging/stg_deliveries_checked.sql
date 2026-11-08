-- Goods receipts, typed and checked (the first row of each delivery_id is kept).
with typed as (
    select
        delivery_id, po_line_id, store_id,
        {{ try_cast('received_date', 'date') }}   as received_date,
        {{ try_cast('qty_received', 'integer') }} as qty_received,
        qty_received as qty_received_raw,
        _batch_date, _row_number, _loaded_at
    from {{ source('raw', 'deliveries') }}
),
checked as (
    select
        *,
        case
            when delivery_id is null or po_line_id is null then 'missing_key'
            when received_date is null                     then 'invalid_date'
            when qty_received is null or qty_received <= 0 then 'invalid_quantity'
        end as rule_violation
    from typed
),
valid_ranked as (
    select _batch_date, _row_number,
           row_number() over (partition by delivery_id order by _loaded_at, _batch_date, _row_number) as occurrence
    from checked
    where rule_violation is null
)
select
    c.*,
    case
        when c.rule_violation is not null then c.rule_violation
        when v.occurrence > 1 then 'duplicate_delivery_id'
    end as rejection_reason
from checked c
left join valid_ranked v
    on v._batch_date = c._batch_date and v._row_number = c._row_number and c.rule_violation is null

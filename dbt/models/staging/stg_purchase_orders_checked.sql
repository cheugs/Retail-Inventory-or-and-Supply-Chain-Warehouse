-- Purchase order lines, typed and checked (the first row of each po_line_id is kept).
with typed as (
    select
        po_line_id, po_id, supplier_id, store_id, product_id,
        {{ try_cast('order_date', 'date') }}     as order_date,
        {{ try_cast('promised_date', 'date') }}  as promised_date,
        {{ try_cast('qty_ordered', 'integer') }} as qty_ordered,
        {{ try_cast('unit_cost', 'numeric') }}   as unit_cost,
        _batch_date, _row_number, _loaded_at
    from {{ source('raw', 'purchase_orders') }}
),
checked as (
    select
        *,
        case
            when po_line_id is null or supplier_id is null or product_id is null then 'missing_key'
            when order_date is null or promised_date is null then 'invalid_date'
            when promised_date < order_date                  then 'promised_before_order'
            when qty_ordered is null or qty_ordered <= 0     then 'invalid_quantity'
        end as rule_violation
    from typed
),
valid_ranked as (
    select _batch_date, _row_number,
           row_number() over (partition by po_line_id order by _loaded_at, _batch_date, _row_number) as occurrence
    from checked
    where rule_violation is null
)
select
    c.*,
    case
        when c.rule_violation is not null then c.rule_violation
        when v.occurrence > 1 then 'duplicate_po_line_id'
    end as rejection_reason
from checked c
left join valid_ranked v
    on v._batch_date = c._batch_date and v._row_number = c._row_number and c.rule_violation is null

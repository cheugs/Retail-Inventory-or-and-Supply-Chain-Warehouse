-- Purchase order fact (accumulating snapshot).
-- Grain: one row per purchase order line. The row "accumulates" the milestones of
-- the order: ordered -> promised -> first delivery -> last delivery. It is rebuilt
-- at each run because its rows keep changing while deliveries arrive.
with po as (
    select * from {{ ref('stg_purchase_orders_checked') }} where rejection_reason is null
),

deliveries as (
    select
        po_line_id,
        count(*)            as delivery_count,
        sum(qty_received)   as qty_received,
        min(received_date)  as first_received_date,
        max(received_date)  as last_received_date
    from {{ ref('stg_deliveries_checked') }}
    where rejection_reason is null
    group by po_line_id
),

as_of as (
    -- the last day the warehouse knows about: an order is only "late" relative to it
    select max(_batch_date) as as_of_date from {{ source('raw', 'purchase_orders') }}
),

joined as (
    select
        po.*,
        coalesce(d.delivery_count, 0)  as delivery_count,
        coalesce(d.qty_received, 0)    as qty_received,
        d.first_received_date,
        d.last_received_date,
        a.as_of_date
    from po
    left join deliveries d on d.po_line_id = po.po_line_id
    cross join as_of a
)

select
    j.po_line_id,
    j.po_id,
    sup.supplier_key,
    st.store_key,
    coalesce(p.product_key, '-1')                         as product_key,
    j.supplier_id,
    j.store_id,
    j.product_id,
    {{ date_key('j.order_date') }}                        as order_date_key,
    j.order_date,
    j.promised_date,
    j.first_received_date,
    j.last_received_date,
    j.qty_ordered,
    j.qty_received,
    j.delivery_count,
    round(j.qty_ordered * j.unit_cost, 2)                 as ordered_value_eur,
    {{ dbt.datediff('j.order_date', 'j.promised_date', 'day') }}        as promised_lead_time_days,
    {{ dbt.datediff('j.order_date', 'j.first_received_date', 'day') }}  as actual_lead_time_days,
    -- status of the line on the as-of date
    case
        when j.qty_received >= j.qty_ordered then 'complete'
        when j.qty_received > 0              then 'partial'
        when j.promised_date < j.as_of_date  then 'overdue'
        else 'open'
    end                                                    as status,
    -- a line can be evaluated once something was delivered or the promised date has passed
    (j.qty_received > 0 or j.promised_date < j.as_of_date) as is_evaluable,
    j.first_received_date is not null and j.first_received_date <= j.promised_date as is_on_time,
    j.qty_received >= j.qty_ordered                        as is_in_full,
    j.qty_received >= j.qty_ordered and j.last_received_date <= j.promised_date as is_otif,
    least(j.qty_received, j.qty_ordered) * 1.0 / j.qty_ordered as fill_rate,
    j.as_of_date
from joined j
left join {{ ref('dim_supplier') }} sup on sup.supplier_id = j.supplier_id
left join {{ ref('dim_store') }} st on st.store_id = j.store_id
left join {{ ref('dim_product') }} p
    on  p.product_id = j.product_id
    and cast(j.order_date as timestamp) >= p.valid_from
    and cast(j.order_date as timestamp) <  p.valid_to

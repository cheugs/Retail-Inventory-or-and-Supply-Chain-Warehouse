-- Supplier performance by month of order.
--   on-time rate : first delivery on or before the promised date
--   in-full rate : everything ordered was received
--   OTIF         : on time AND in full (the usual retail KPI)
--   fill rate    : units received / units ordered
-- Only "evaluable" lines are counted (something delivered, or promised date passed),
-- so orders that are simply not due yet do not lower the scores.
select
    f.supplier_id,
    s.supplier_name,
    cast(date_trunc('month', f.order_date) as date)                     as order_month,
    count(*)                                                            as order_lines,
    sum(case when f.is_evaluable then 1 else 0 end)                     as evaluable_lines,
    round(avg(case when f.is_evaluable then (case when f.is_on_time then 1.0 else 0.0 end) end), 4) as on_time_rate,
    round(avg(case when f.is_evaluable then (case when f.is_in_full then 1.0 else 0.0 end) end), 4) as in_full_rate,
    round(avg(case when f.is_evaluable then (case when f.is_otif then 1.0 else 0.0 end) end), 4)    as otif_rate,
    round(sum(case when f.is_evaluable then least(f.qty_received, f.qty_ordered) end) * 1.0
          / nullif(sum(case when f.is_evaluable then f.qty_ordered end), 0), 4) as fill_rate,
    round(avg(f.actual_lead_time_days), 2)                              as avg_actual_lead_time_days,
    round(avg(f.promised_lead_time_days), 2)                            as avg_promised_lead_time_days,
    sum(f.qty_ordered)                                                  as units_ordered,
    sum(f.qty_received)                                                 as units_received
from {{ ref('fct_purchase_order_lines') }} f
left join {{ ref('dim_supplier') }} s on s.supplier_id = f.supplier_id
group by 1, 2, 3

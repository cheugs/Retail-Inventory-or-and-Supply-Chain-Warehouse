-- sales rows that failed a quality rule (or are duplicates), kept with the reason.
-- Nothing is deleted silently: every raw row ends up either in the warehouse or here.
select *
from {{ ref('stg_sales_checked') }}
where rejection_reason is not null

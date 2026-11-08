-- No silent loss: every raw sales line is either in fct_sales or in quarantine.
-- Returns one row if the counts differ.
with counts as (
    select
        (select count(*) from {{ source('raw', 'sales') }})            as raw_rows,
        (select count(*) from {{ ref('fct_sales') }})                  as fact_rows,
        (select count(*) from {{ ref('rejected_sales') }})             as rejected_rows
)
select *
from counts
where raw_rows <> fact_rows + rejected_rows

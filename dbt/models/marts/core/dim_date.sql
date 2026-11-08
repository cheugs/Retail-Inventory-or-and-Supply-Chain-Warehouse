-- Calendar dimension: one row per day.
with days as (
    {{ day_series(var('date_spine_start'), var('date_spine_end')) }}
)
select
    {{ date_key('date_day') }}                         as date_key,
    date_day,
    extract(year from date_day)                         as year,
    extract(quarter from date_day)                      as quarter,
    extract(month from date_day)                        as month,
    cast(date_trunc('month', date_day) as date)         as month_start,
    to_char(date_day, 'YYYY-MM')                        as year_month,
    {{ iso_day_of_week('date_day') }}                   as iso_day_of_week,
    {{ iso_day_of_week('date_day') }} in (6, 7)         as is_weekend
from days

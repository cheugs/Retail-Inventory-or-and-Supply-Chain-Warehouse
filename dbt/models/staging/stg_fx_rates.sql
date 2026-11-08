-- Daily exchange rates, typed. One row per (date, currency): if a rate is sent
-- twice, the last loaded value wins.
-- valid_to = date of the next known rate, so that a day without a rate
-- (late finance file) uses the last known rate instead of leaving amounts empty.
with typed as (
    select
        {{ try_cast('rate_date', 'date') }}        as rate_date,
        upper(trim(currency))                       as currency,
        {{ try_cast('rate_to_eur', 'numeric') }}   as rate_to_eur,
        _loaded_at,
        _row_number
    from {{ source('raw', 'fx_rates') }}
),
ranked as (
    select
        *,
        row_number() over (partition by rate_date, currency order by _loaded_at desc, _row_number desc) as rn
    from typed
),
latest as (
    select rate_date, currency, rate_to_eur
    from ranked
    where rn = 1 and rate_date is not null and rate_to_eur > 0
)
select
    rate_date,
    currency,
    rate_to_eur,
    coalesce(
        lead(rate_date) over (partition by currency order by rate_date),
        cast('9999-12-31' as date)
    ) as valid_to
from latest

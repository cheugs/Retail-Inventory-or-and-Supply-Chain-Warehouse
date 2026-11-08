-- Stores: slowly changing dimension TYPE 1.
-- A change (for example a new store manager) simply overwrites the old value:
-- we keep only the most recent row of each store.
with typed as (
    select
        trim(store_id)                            as store_id,
        store_name, city, country,
        upper(trim(currency))                     as currency,
        region, manager_name,
        {{ try_cast('updated_at', 'timestamp') }} as updated_at,
        _loaded_at
    from {{ source('raw', 'stores') }}
    where store_id is not null
),
ranked as (
    select *, row_number() over (partition by store_id order by updated_at desc nulls last, _loaded_at desc) as rn
    from typed
)
select store_id, store_name, city, country, currency, region, manager_name, updated_at
from ranked
where rn = 1

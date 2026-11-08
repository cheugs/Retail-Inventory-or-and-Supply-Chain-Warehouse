-- Suppliers: slowly changing dimension TYPE 1 (latest values only).
with typed as (
    select
        trim(supplier_id)                                    as supplier_id,
        supplier_name, country, city,
        {{ try_cast('promised_lead_time_days', 'integer') }} as promised_lead_time_days,
        {{ try_cast('updated_at', 'timestamp') }}            as updated_at,
        _loaded_at
    from {{ source('raw', 'suppliers') }}
    where supplier_id is not null
),
ranked as (
    select *, row_number() over (partition by supplier_id order by updated_at desc nulls last, _loaded_at desc) as rn
    from typed
)
select supplier_id, supplier_name, country, city, promised_lead_time_days, updated_at
from ranked
where rn = 1

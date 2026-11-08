-- Store dimension, slowly changing TYPE 1 (attributes are overwritten).
select
    {{ surrogate_key(['store_id']) }} as store_key,
    store_id, store_name, city, country, region, currency, manager_name,
    updated_at as last_updated_at
from {{ ref('stg_stores') }}

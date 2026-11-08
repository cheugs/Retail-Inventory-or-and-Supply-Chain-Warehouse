-- Supplier dimension, slowly changing TYPE 1 (attributes are overwritten).
select
    {{ surrogate_key(['supplier_id']) }} as supplier_key,
    supplier_id, supplier_name, country, city, promised_lead_time_days,
    updated_at as last_updated_at
from {{ ref('stg_suppliers') }}

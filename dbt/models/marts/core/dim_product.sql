-- Product dimension, slowly changing TYPE 2.
-- product_key  = surrogate key of one VERSION (changes when the price changes)
-- product_id   = business key (same for every version of the product)
-- Facts store the product_key of the version valid when the event happened,
-- so the cost and price of a past sale never change afterwards.
select
    {{ surrogate_key(['product_id', 'valid_from']) }} as product_key,
    product_id, sku, product_name, category, subcategory, brand, supplier_id,
    unit_cost  as unit_cost_eur,
    unit_price as unit_price_eur,
    is_active, version_number, valid_from, valid_to, is_current
from {{ ref('int_product_versions') }}

union all

-- "Unknown" member: used when a fact references a product that is not in the
-- catalog yet (early-arriving fact). These facts are fixed at a later run.
select
    '-1', 'UNKNOWN', 'UNKNOWN', 'Unknown product', 'Unknown', 'Unknown', 'Unknown', null,
    null, null, true, 0,
    cast('1900-01-01' as timestamp), cast('9999-12-31' as timestamp), true

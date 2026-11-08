-- Every catalog row ever received, typed. This full history is the input of the
-- type 2 product dimension (see intermediate/int_product_versions.sql).
with typed as (
    select
        trim(product_id)                          as product_id,
        sku, product_name, category, subcategory, brand,
        trim(supplier_id)                         as supplier_id,
        {{ try_cast('unit_cost', 'numeric') }}    as unit_cost,
        {{ try_cast('unit_price', 'numeric') }}   as unit_price,
        lower(is_active) = 'true'                 as is_active,
        {{ try_cast('updated_at', 'timestamp') }} as updated_at,
        _batch_date, _loaded_at, _row_number
    from {{ source('raw', 'products') }}
    where product_id is not null
)
select *
from typed
where updated_at is not null
  and unit_price >= 0
  and unit_cost >= 0

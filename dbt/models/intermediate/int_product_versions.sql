-- Builds the history of each product (slowly changing dimension TYPE 2).
--
-- Input: every catalog row ever received (stg_products), in any order, even late.
-- Output: one row per *version* of a product with its validity period
--         [valid_from, valid_to). A new version starts only when a tracked
--         attribute really changes (price, cost, category, supplier...).
--
-- Because the whole history is rebuilt from the raw rows at every run, a catalog
-- update that arrives two days late is placed at the right moment in the history.
with one_row_per_timestamp as (
    -- if the same (product, updated_at) is received twice, keep the last loaded
    select *
    from (
        select
            *,
            row_number() over (partition by product_id, updated_at order by _loaded_at desc, _row_number desc) as rn
        from {{ ref('stg_products') }}
    ) x
    where rn = 1
),

hashed as (
    select
        *,
        md5(
            coalesce(product_name, '') || '|' || coalesce(category, '') || '|' ||
            coalesce(subcategory, '') || '|' || coalesce(brand, '') || '|' ||
            coalesce(supplier_id, '') || '|' || cast(unit_cost as varchar) || '|' ||
            cast(unit_price as varchar) || '|' || cast(is_active as varchar)
        ) as attributes_hash
    from one_row_per_timestamp
),

changes_only as (
    -- drop rows that repeat the previous version without any change
    select *
    from (
        select
            *,
            lag(attributes_hash) over (partition by product_id order by updated_at) as previous_hash
        from hashed
    ) x
    where previous_hash is null or previous_hash <> attributes_hash
),

versions as (
    select
        *,
        row_number() over (partition by product_id order by updated_at) as version_number,
        lead(updated_at) over (partition by product_id order by updated_at) as next_change_at
    from changes_only
)

select
    product_id, sku, product_name, category, subcategory, brand, supplier_id,
    unit_cost, unit_price, is_active, version_number,
    -- the first version also covers the time before the product was first seen,
    -- so a sale that arrives before its catalog row can still find a version
    case when version_number = 1 then cast('1900-01-01' as timestamp) else updated_at end as valid_from,
    coalesce(next_change_at, cast('9999-12-31' as timestamp)) as valid_to,
    next_change_at is null as is_current,
    updated_at as source_updated_at
from versions

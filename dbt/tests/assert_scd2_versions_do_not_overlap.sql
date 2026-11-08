-- SCD2 rule: for one product, two versions must never be valid at the same time.
-- The test returns the overlapping pairs; zero rows means the test passes.
select a.product_id, a.product_key, b.product_key as overlapping_key
from {{ ref('dim_product') }} a
join {{ ref('dim_product') }} b
    on  a.product_id = b.product_id
    and a.product_key <> b.product_key
    and a.valid_from < b.valid_to
    and b.valid_from < a.valid_to

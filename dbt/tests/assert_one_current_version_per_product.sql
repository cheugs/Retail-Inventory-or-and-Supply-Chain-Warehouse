-- SCD2 rule: each product has exactly one current version.
select product_id, count(*) as current_versions
from {{ ref('dim_product') }}
where is_current
group by product_id
having count(*) <> 1

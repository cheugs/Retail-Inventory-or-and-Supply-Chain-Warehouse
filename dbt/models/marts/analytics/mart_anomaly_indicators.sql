-- Simulated, rule-based anomaly INDICATORS. They point at rows worth a look;
-- they do NOT prove theft, fraud or any wrongdoing. Each rule is simple and
-- written in the "rule" column so anyone can understand why a row is here.
--
-- 1. unexplained_stock_drop: stock went down more than sales can explain
--      expected = previous stock + units received - units sold
--      flagged when actual stock < expected - threshold
--    Note: a rejected (invalid) sales line can also create a small gap, which is
--    exactly why this is an indicator and not a conclusion.
-- 2. price_deviation: a till price far from the catalog price of that day.
with stock_drops as (
    select
        'unexplained_stock_drop'            as indicator,
        snapshot_date                       as event_date,
        store_id,
        product_id,
        (previous_on_hand_qty + units_received - units_sold) - on_hand_qty as gap_value,
        'stock below (previous stock + received - sold) by more than '
            || cast({{ var('shrinkage_threshold_units') }} as varchar) || ' units' as rule
    from {{ ref('int_store_product_daily') }}
    where previous_on_hand_qty is not null
      and previous_snapshot_date = {{ dbt.dateadd('day', -1, 'snapshot_date') }}
      and on_hand_qty < previous_on_hand_qty + units_received - units_sold - {{ var('shrinkage_threshold_units') }}
),

price_deviations as (
    select
        'price_deviation'                   as indicator,
        cast(sold_at as date)               as event_date,
        store_id,
        product_id,
        round(unit_price_local * rate_to_eur / catalog_price_eur - 1, 3) as gap_value,
        'till price differs from catalog price by more than '
            || cast(cast({{ var('price_deviation_threshold') }} * 100 as integer) as varchar) || '%' as rule
    from {{ ref('fct_sales') }}
    where catalog_price_eur > 0
      and abs(unit_price_local * rate_to_eur / catalog_price_eur - 1) > {{ var('price_deviation_threshold') }}
)

select * from stock_drops
union all
select * from price_deviations

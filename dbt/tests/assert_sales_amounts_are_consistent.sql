-- Integrity of each sales line: positive quantity, net = gross - discount,
-- and a discount never bigger than the line itself.
select sale_line_id
from {{ ref('fct_sales') }}
where quantity <= 0
   or abs(net_amount_local - (gross_amount_local - discount_amount_local)) > 0.001
   or discount_amount_local > gross_amount_local
   or net_amount_eur < 0

{#- Small macros that hide the differences between PostgreSQL and Snowflake.
    Each one has a default (Snowflake-style) version and a postgres__ version;
    dbt picks the right one with adapter.dispatch. -#}

{#- try_cast: returns NULL instead of failing when a text value cannot be converted.
    This is how bad source values are detected without breaking the run. -#}
{% macro try_cast(column, data_type) -%}
    {{ return(adapter.dispatch('try_cast')(column, data_type)) }}
{%- endmacro %}

{% macro default__try_cast(column, data_type) -%}
    try_cast({{ column }} as {{ data_type }})
{%- endmacro %}

{% macro postgres__try_cast(column, data_type) -%}
    {#- pg_input_is_valid exists since PostgreSQL 16 -#}
    case when pg_input_is_valid({{ column }}, '{{ data_type }}') then ({{ column }})::{{ data_type }} end
{%- endmacro %}

{#- surrogate_key: a stable hash of the business columns (same input -> same key). -#}
{% macro surrogate_key(columns) -%}
    md5(
    {%- for col in columns -%}
        coalesce(cast({{ col }} as varchar), '_null_'){% if not loop.last %} || '|' || {% endif %}
    {%- endfor -%}
    )
{%- endmacro %}

{#- date_key: integer YYYYMMDD, the usual key of a date dimension. -#}
{% macro date_key(column) -%}
    cast(to_char({{ column }}, 'YYYYMMDD') as integer)
{%- endmacro %}

{#- day_series: one row per day between two dates (column "date_day"). -#}
{% macro day_series(start_date, end_date) -%}
    {{ return(adapter.dispatch('day_series')(start_date, end_date)) }}
{%- endmacro %}

{% macro default__day_series(start_date, end_date) -%}
    select dateadd(day, seq4(), '{{ start_date }}'::date) as date_day
    from table(generator(rowcount => 5000))
    qualify date_day <= '{{ end_date }}'::date
{%- endmacro %}

{% macro postgres__day_series(start_date, end_date) -%}
    select cast(d as date) as date_day
    from generate_series('{{ start_date }}'::date, '{{ end_date }}'::date, interval '1 day') as d
{%- endmacro %}

{#- iso_day_of_week: 1 = Monday ... 7 = Sunday -#}
{% macro iso_day_of_week(column) -%}
    {{ return(adapter.dispatch('iso_day_of_week')(column)) }}
{%- endmacro %}
{% macro default__iso_day_of_week(column) -%}dayofweekiso({{ column }}){%- endmacro %}
{% macro postgres__iso_day_of_week(column) -%}cast(extract(isodow from {{ column }}) as integer){%- endmacro %}

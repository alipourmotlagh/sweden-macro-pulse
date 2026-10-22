-- One row per series with coverage and freshness. Feeds the public data catalogue and freshness tests.
with riksbank as (
    select
        'riksbank' as source,
        series_key,
        series_id as source_id,
        min(obs_date) as first_obs,
        max(obs_date) as last_obs,
        count(*) as n_obs
    from {{ ref('stg_riksbank_observations') }}
    group by series_key, series_id
),
scb as (
    select 'scb' as source, series_key, table_id as source_id,
           min(month) as first_obs, max(month) as last_obs, count(*) as n_obs
    from {{ ref('mart_cpif_monthly') }}
    group by series_key, table_id
    union all
    select 'scb' as source, series_key, table_id as source_id,
           min(month) as first_obs, max(month) as last_obs, count(*) as n_obs
    from {{ ref('mart_mortgage_monthly') }}
    group by series_key, table_id
),
all_series as (
    select * from riksbank
    union all
    select * from scb
)
select
    source, series_key, source_id, first_obs, last_obs, n_obs,
    date_diff('day', last_obs, current_date) as days_since_last_obs
from all_series

-- One row per series with coverage and freshness. Feeds the public data catalogue and freshness tests.
select
    'riksbank' as source,
    series_key,
    series_id as source_id,
    min(obs_date) as first_obs,
    max(obs_date) as last_obs,
    count(*) as n_obs,
    date_diff('day', max(obs_date), current_date) as days_since_last_obs
from {{ ref('stg_riksbank_observations') }}
group by series_key, series_id

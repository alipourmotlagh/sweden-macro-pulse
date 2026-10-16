select
    series_id,
    series_key,
    unit,
    cast(obs_date as date) as obs_date,
    cast(value as double) as value,
    snapshot_file
from {{ source('raw', 'riksbank_observations') }}
where value is not null

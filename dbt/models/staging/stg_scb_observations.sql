select
    series_key,
    table_id,
    dims,
    cast(value as double) as value,
    snapshot_file
from {{ source('raw', 'scb_observations') }}
where value is not null

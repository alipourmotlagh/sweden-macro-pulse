-- KI statistics and forecast vintages. `dims` is JSON of the table's dimensions (e.g. variabel, enhet, period).
select
    series_key,
    kind,
    vintage,
    json_extract_string(dims, '$.variabel') as variable,
    coalesce(json_extract_string(dims, '$.period_label'), json_extract_string(dims, '$.period')) as period_code,
    dims,
    cast(value as double) as value,
    snapshot_file
from {{ source('raw', 'ki_observations') }}
where value is not null

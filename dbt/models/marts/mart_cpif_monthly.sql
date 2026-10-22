-- CPIF annual change (percent), monthly, from SCB table TAB6590 (ContentsCode 000007ZM). Values as published.
select
    'cpif_annual' as series_key,
    'TAB6590' as table_id,
    make_date(cast(substr(json_extract_string(dims, '$.Tid'), 1, 4) as integer),
              cast(substr(json_extract_string(dims, '$.Tid'), 6, 2) as integer), 1) as month,
    value
from {{ ref('stg_scb_observations') }}
where series_key = 'cpif'
  and json_extract_string(dims, '$.ContentsCode') = '000007ZM'
  and json_extract_string(dims, '$.Tid') like '____M__'

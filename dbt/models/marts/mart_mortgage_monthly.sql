-- Households' housing-loan interest rates (percent), monthly, from SCB table TAB5783 (data source: the Riksbank).
-- Average rate at the end of the month. new = new and renegotiated agreements, outstanding = all existing loans.
with base as (
    select
        make_date(cast(substr(json_extract_string(dims, '$.Tid'), 1, 4) as integer),
                  cast(substr(json_extract_string(dims, '$.Tid'), 6, 2) as integer), 1) as month,
        json_extract_string(dims, '$.Avtal') as agreement,
        json_extract_string(dims, '$.Rantebindningstid') as fixation,
        value
    from {{ ref('stg_scb_observations') }}
    where series_key = 'mortgage_rates'
      and json_extract_string(dims, '$.Tid') like '____M__'
)
select
    'mortgage_'
        || case agreement when '0100' then 'new' when '0200' then 'outstanding' end
        || '_'
        || case fixation
               when '1.1'     then 'total'
               when '1.1.1'   then 'floating'
               when '1.1.2.1' then '3m_1y'
               when '1.1.2.2' then '1_5y'
               when '1.1.2.3' then '5y_plus'
           end as series_key,
    'TAB5783' as table_id,
    month,
    value
from base
where agreement in ('0100', '0200')
  and fixation in ('1.1', '1.1.1', '1.1.2.1', '1.1.2.2', '1.1.2.3')

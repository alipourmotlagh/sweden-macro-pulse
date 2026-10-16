-- Every KI release (vintage) of the monthly interest-rate table, one row per vintage x variable x month.
-- Whether a month is outcome or forecast is decided later, relative to the vintage's release month.
select
    vintage,
    strptime(vintage, '%Y%m%d')::date as release_date,
    variable,
    make_date(cast(substr(period_code, 1, 4) as integer), cast(substr(period_code, 6, 2) as integer), 1) as period,
    value
from {{ ref('stg_ki_observations') }}
where series_key = 'ki_rates_monthly'
  and kind = 'forecast_vintage'
  and period_code like '____M__'

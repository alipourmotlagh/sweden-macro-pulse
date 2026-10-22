-- Plausibility bands (generous): a failure means a parsing or code-mapping problem, not a real market move.
select 'cpif_annual' as series_key, month, value from {{ ref('mart_cpif_monthly') }}
where value < -5 or value > 25
union all
select series_key, month, value from {{ ref('mart_mortgage_monthly') }}
where value < -1 or value > 15

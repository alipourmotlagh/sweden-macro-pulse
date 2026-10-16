-- Fails if any policy-rate observation is outside a plausible band (catches unit/parse errors).
select * from {{ ref('stg_riksbank_observations') }}
where series_key = 'policy_rate' and (value < -2 or value > 20)

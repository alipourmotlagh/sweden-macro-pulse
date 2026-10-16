select * from {{ ref('stg_riksbank_observations') }}
where obs_date > current_date + interval 1 day

-- Monthly averages of the three rate series. Spread is our own calculation (not a Riksbank series).
with monthly as (
    select
        date_trunc('month', obs_date)::date as month,
        series_key,
        avg(value) as avg_value,
        count(*) as n_obs
    from {{ ref('stg_riksbank_observations') }}
    group by 1, 2
),
pivoted as (
    select
        month,
        max(case when series_key = 'policy_rate'  then avg_value end) as policy_rate,
        max(case when series_key = 'stibor_3m'    then avg_value end) as stibor_3m,
        max(case when series_key = 'gov_bond_10y' then avg_value end) as gov_bond_10y
    from monthly
    group by 1
)
select
    month,
    round(policy_rate, 4)  as policy_rate,
    round(stibor_3m, 4)    as stibor_3m,
    round(gov_bond_10y, 4) as gov_bond_10y,
    round(gov_bond_10y - policy_rate, 4) as spread_10y_policy
from pivoted
order by month

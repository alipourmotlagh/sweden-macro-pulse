-- Freshness: warn (not fail) when a series has no observation within its expected lag.
-- Riksbank rates are daily (45 days); SCB monthly series are published with a lag of 1-2 months (100 days).
{{ config(severity='warn') }}
select * from {{ ref('mart_catalogue') }}
where days_since_last_obs > case when source = 'scb' then 100 else 45 end

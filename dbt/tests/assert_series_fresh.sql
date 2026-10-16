-- Freshness: warn (not fail) when a rate series has no observation in the last 45 days.
{{ config(severity='warn') }}
select * from {{ ref('mart_catalogue') }}
where days_since_last_obs > 45

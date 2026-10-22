# Data sources and status

Status: **verify** = written from documentation, not yet confirmed by a live data request. Update after the first successful Actions run.

| Source | What | Access | Status | Terms / attribution |
|---|---|---|---|---|
| Riksbank SWEA | Policy rate `SECBREPOEFF`, 3-month Treasury bill `SETB3MBENCH`, 10y govt yield `SEGVB10YC` | REST `api.riksbank.se/swea/v1`, key optional (header `Ocp-Apim-Subscription-Key`) | base URL, key header, limits confirmed from Riksbank FAQ 2026-10-15; interval-observations path and response shape verify | "Källa: Sveriges riksbank" required for unchanged data; must not be credited on data we processed; commercial reuse free, no agreement; must not be presented as an official partnership |
| Riksbank Monetary Policy Data v1 | The Riksbank's own forecasts per policy round (e.g. `2024:1`): `/forecasts/series_ids`, `/forecasts/policy_rounds`, `/forecasts?policy_round_name=` | REST, same key header as SWEA | raw landing built (`ingest/riksbank_mpd.py`); series ids and response shape verify on first run; not yet parsed or in the ledger | Same Riksbank terms as SWEA (credit only unchanged data); the Riksbank disclaims liability for changes |
| KI statistics | Barometer indicator (`KonjBar/indikatorer/Indikatorm.px`) | PxWeb v1 API | directory + metadata verified 2026-10-15; data request verify | Free reuse incl. commercial, manual or API (konj.se "Så fungerar databaserna"). No attribution wording stated; we credit KI |
| KI forecasts | Latest (`SenastePrognosen`) and every quarterly release since 2015 (`TidigarePrognoser/<YYYYMMDD>`), 11 topic folders; first table: `f06.../F0604.px` (monthly interest rates) | PxWeb v1 API | as above | As above |
| SCB PxWebApi 2 | CPIF annual change `TAB6590` (from 1988-01 after the first null), households' housing loan rates `TAB5783` (10 series, from 2005-09; source agency the Riksbank) | REST `statistikdatabasen.scb.se/api/v2`, JSON-stat2; 10 calls/10 s, 100,000 values/table | live, verified 2026-10-22 | API data CC0 ("Source: Statistics Sweden" recommended; no credit on processed data; data from other agencies credits that agency, so mortgage rates say "Sveriges riksbank (published via Statistics Sweden)") |

## Notes
- Riksbank limits: anonymous 5 calls/min and 1,000/day per IP; with a key 200/min (FAQ: 30,000/week; portal's Developer subscription page says 10,000/week). Use the portal's **Developer** subscription, not "External data reporter" (that is for authorised reporters to the Riksbank).
- KI forecast tables mix outcomes and forecast months in one series. Checked 2026-10-21 (`scripts/check_ki_outcomes.py`, 10-year yield vs the Riksbank's monthly averages, 2023-06 to 2026-06 releases): months before the release month equal the actual; the release month itself already differs, so `forecasts/ki_ledger.py` treats the release month onward as forecasts (release month = horizon 0, a nowcast).
- Releases before 2023-06 use numeric period codes (`0`, `1`, ...) with `1993M01` only in the labels; the parser keeps the label as `period_label` and staging prefers it.
- Sept 2026 KI release is in "latest" but not yet in "earlier forecasts"; we snapshot "latest" each run.
- KI stops publishing outcome data (CPI, labour force, national accounts) on 1 Jan 2027: take outcomes from SCB.
- KI download cap: 250,000 cells per request.

- STIBOR is not used: the Riksbank's STIBOR series are closed (last data 2020-07-03, checked 2026-10-21 in the `Series` list). SFBF publishes STIBOR now; its terms (swfbf.se/terms, /subscribe) prohibit redistribution and derived products without a paid licence, so a public chart is out. The 3-month Treasury bill is the substitute short rate and is labelled as such.

## Open items
1. First live run of the Monetary Policy Data adapter: read the landed `series_ids`, choose the repo-rate and CPIF series, then parse and map into the ledger. A 401 would mean the Developer subscription does not include this API.
2. Surface dbt freshness warnings in the job summary so a dead series cannot hide behind a green run.
3. Verify the TiRex-2 licence before use; 2019-06 and 2019-10 KI outcome deviations (~0.15) are not investigated.

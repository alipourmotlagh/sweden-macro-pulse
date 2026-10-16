# Data sources and status

Status: **verify** = written from documentation, not yet confirmed by a live data request. Update after the first successful Actions run.

| Source | What | Access | Status | Terms / attribution |
|---|---|---|---|---|
| Riksbank SWEA | Policy rate `SECBREPOEFF`, STIBOR 3M `SEDP3MSTIBORDELAYC`, 10y govt yield `SEGVB10YC` | REST `api.riksbank.se/swea/v1`, key optional (header `Ocp-Apim-Subscription-Key`) | base URL, key header, limits confirmed from Riksbank FAQ 2026-10-15; interval-observations path and response shape verify | "Källa: Sveriges riksbank" required for unchanged data; must not be credited on data we processed; commercial reuse free, no agreement; must not be presented as an official partnership |
| Riksbank forecasts | Repo-rate / CPIF forecast vintages (from 2020) | REST | not built | Variables and format unverified |
| KI statistics | Barometer indicator (`KonjBar/indikatorer/Indikatorm.px`) | PxWeb v1 API | directory + metadata verified 2026-10-15; data request verify | Free reuse incl. commercial, manual or API (konj.se "Så fungerar databaserna"). No attribution wording stated; we credit KI |
| KI forecasts | Latest (`SenastePrognosen`) and every quarterly release since 2015 (`TidigarePrognoser/<YYYYMMDD>`), 11 topic folders; first table: `f06.../F0604.px` (monthly interest rates) | PxWeb v1 API | as above | As above |
| SCB PxWebApi 2 | CPIF, mortgage/lending, FASTPI | REST, JSON-stat2 | tables not chosen | Licence terms to confirm |

## Notes
- Riksbank limits: anonymous 5 calls/min and 1,000/day per IP; with a key 200/min (FAQ: 30,000/week; portal's Developer subscription page says 10,000/week). Use the portal's **Developer** subscription, not "External data reporter" (that is for authorised reporters to the Riksbank).
- KI forecast tables mix outcomes and forecast months in one series; `forecasts/ki_ledger.py` treats months after the release month as forecasts (assumption, check against real data).
- Sept 2026 KI release is in "latest" but not yet in "earlier forecasts"; we snapshot "latest" each run.
- KI stops publishing outcome data (CPI, labour force, national accounts) on 1 Jan 2027: take outcomes from SCB.
- KI download cap: 250,000 cells per request.

## Open items
1. Run `scripts/discover_scb_tables.py`, pick table IDs, fill `config/series.yml`.
2. Confirm SCB licence wording.
3. Confirm Riksbank forecasts API variables and format.
4. First live run: confirm KI POST response (json-stat2) and Riksbank/SCB formats; set `status: ok`.

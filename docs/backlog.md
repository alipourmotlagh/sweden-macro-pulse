# Backlog: things we deliberately postponed

Rule: when a piece of work is finished, come back here, review, pick the next items. Add a line whenever we say "later".
Status: [ ] open, [x] done. Keep one line per item with the reason.

## Forecasts and scoring
- [ ] KI inflation forecasts (CPIF) as a second professional comparator: KI has them in another PxWeb table; currently only the Riksbank forecasts CPIF in the ledger.
- [ ] Outcome source for CPI (not CPIF) so `cpi_annual` can be scored: add an SCB CPI table.
- [x] Done 2026-10-25: scores split by era, benchmark given the forecast's own information date (backtest-2), bootstrap interval, per-round file.
- [ ] Rate baseline band: `naive` rate rows use h-step changes but the true distance is h+1 (last value is the previous month). CPIF already uses lead=1. Fix with a new model_version from a new month; never edit logged rows.
- [ ] Scoring covers horizons up to 12; the Riksbank CPIF goes to 38. Add longer horizons with their own sample sizes.
- [ ] Quarterly benchmark for `policy_rate_qmean` (no skill score today); KI monthly rate forecasts averaged into quarters for comparison.
- [ ] Quarterly mean of the policy rate is the mean of three monthly averages, the Riksbank may average daily values. Check the size of the difference.
- [ ] Models for month 2+: ETS/ARIMA, TimesFM 2.5, Chronos-2 (licences in `forecasts/model_register.yml`); TiRex-2 licence unverified.
- [x] Done 2026-10-26: KI interest-rate benchmark now uses the last daily value before KI's publication day (backtest-3).
- [ ] Show the real-time baseline in the scoreboard once its first target months have outcomes (from November 2026).
- [ ] Interval coverage for models other than the real-time naive (Riksbank and KI publish no intervals in our data).
- [ ] Investigate the small KI outcome deviations in 2019-06 and 2019-10 (~0.15); first two KI releases lack the policy rate.
- [ ] Riksbank series not used yet (GDP, unemployment, wages, KIX, ...) are already in the raw data; add if a pack needs them.

## Pipeline and data quality
- [ ] Make dbt freshness warnings visible in the job summary (a dead series must not hide behind a green run).
- [ ] Flip `status: verify` to `ok` in `config/series.yml` for sources now verified live (Riksbank SWEA, MPD, SCB, KI).
- [ ] Bump GitHub Actions versions (checkout, setup-python, upload-pages-artifact, deploy-pages) for the Node 20 deprecation warnings.
- [ ] Surface adapter warnings (`::warning::`) in the job summary too; the ledger step failing loudly is fine, a skipped source is not.
- [ ] Decide the licence for the published data files (code is MIT).
- [ ] Update `docs/sources.md` status column after the above.

## Docs and story
- [ ] Update the Claude Doc "The price of borrowing in Sweden: product brief and build plan" (T-bill instead of STIBOR, SCB tables, horizon-0 rule, Riksbank forecasts, scoring).
- [ ] Short write-up for LinkedIn/interviews: the silent-failure lessons (green run hides problems), the colon-encoding 404, the cutoff-date check against SCB.
- [ ] README refresh with the final pipeline picture.

## Site (dobedobedo repo, separate Claude Code session)
- [ ] Data page with ISR in the site's style; lightweight SVG charts (mortgage vs policy rate vs 10y/T-bill/CPIF); calculator; methodology page; forecast ledger note; preview image.
- [ ] Show the notes from `v1/forecast_conventions.json` next to every forecast or score (required, see `docs/forecast_conventions.md`).
- [ ] Hero.tsx uncommitted change; lint errors in Closing.tsx; Node pin (.nvmrc "22", engines); "About Hadi Motlagh" page title.
- [ ] Swedish version after month 1 (all text in one translation file per language).

## Tooling
- [ ] Install GitHub CLI so Claude Code can push (`brew install gh`, `gh auth login`); today pushes go through GitHub Desktop.

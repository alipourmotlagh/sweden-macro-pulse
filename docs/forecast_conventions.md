# Forecast conventions: how to read the ledger and what users must be told

Source of truth: `forecasts/conventions.yml` (maintainer definitions plus user-facing notes in English and Swedish).
It is published as `v1/forecast_conventions.json`. **Any page that shows a forecast or a score must show the relevant notes**
(global horizon note, scoring note, attribution note, plus the model and series notes for what is on the page).
`tests/test_conventions.py` fails if a model or series in the ledger has no entry, so this cannot be forgotten.

## The rules (and why)
1. **Horizon** = whole months from the month a forecast was *published* (`made_at`) to the target period, for every model.
   0 is the publication month (a nowcast, partly known); negative means the month was over but not yet published.
   *Why:* one rule for every model makes them comparable by "time elapsed" for a user. The cost: models use data up to
   different dates.
2. **Information date** is kept in `data_vintage` (KI: release date; Riksbank: `forecast_cutoff_date`, often 1-2 months
   before publication; naive: last month used). A cutoff-based horizon can be recomputed later without re-collecting.
3. **Headline accuracy uses horizon >= 1 only.** Horizon 0 and negative are reported separately. *Why:* they are partly
   known, and counting them would flatter every model.
4. **Sample size is always shown.** Long horizons have few observations; differences between models are indicative.
5. **Outcomes:** CPIF/CPI from SCB (KI stops publishing outcomes on 2027-01-01); interest rates from the Riksbank daily
   data averaged by month. *Why:* official outcome sources, not any model's own history.
6. **Quarterly series** (`policy_rate_qmean`, `policy_rate_forward_qmean`): the Riksbank forecasts the policy rate as a
   quarterly mean. `target_period` is the quarter-end month (2026-12 = Oct-Dec 2026). Scored against the quarterly mean of
   the actual rate, never mixed into the monthly `policy_rate` series. KI's monthly rate forecasts can be averaged into
   quarters for comparison.
7. **`market_forward` is not a Riksbank forecast.** It is the policy rate implied by forward pricing, published by the
   Riksbank. Label it as market expectation.
8. **Attribution:** Riksbank and KI forecasts are reproduced unchanged and credited to them; everything else (baselines,
   our models, scores) is our own calculation and is labelled so.
9. **Known gap:** Riksbank round 2020:2 has no single forecast (two scenarios); skipped on purpose.

10. **Benchmark.** `naive_backtest` (version `backtest-3`) is a random walk computed in hindsight for every date another
    model published (horizons 0-12). It gets the **same information date as the forecast it is compared with**: for Riksbank
    CPIF, the value for the round's own data cutoff month; for KI interest rates, the last *daily* Riksbank value strictly
    before the day KI published; otherwise the last value published/complete by the publication month. Version 1 always used two months back, which flattered the
    Riksbank (CPIF skill 0.37 vs 0.29 with the fair benchmark; the Riksbank's cutoff was only one month before publication
    in 38 of 59 rounds).
    It exists because the real-time `naive` baseline only started in 2026-10. It is computed when the scoreboard is built
    and is never written to the ledger (the ledger holds only forecasts made in real time). It is a backtest, so
    it is always labelled indicative.
11. **Skill** = 1 - MAE(model) / MAE(naive_backtest) on the same target months and horizons; always shown with n.
12. **Outcomes** for rates use *complete* months only; a quarter needs all three months. CPI (not CPIF) has no outcome
    source yet, so `cpi_annual` forecasts are logged but not scored (see backlog).
13. **Real-time CPIF baseline** uses the value two months before the run month, never a later one, so weekly re-runs in
    the same month produce identical rows (the ledger refuses changed rows under the same key).

14. **Eras** (scoreboard `by_era`): results are also split by *target month* into before 2021, 2021-2023 (the inflation
    surge), 2024 onward, and all periods except 2021-2023. The eras are fixed in advance in `forecasts/scoring.py` (`ERAS`)
    and `forecasts/conventions.yml`; moving them after seeing results would be cherry-picking.
15. **Honest sample size:** every row shows n (forecasts), `n_releases` (distinct rounds/releases) and `n_target_months`.
    Forecasts from one round overlap heavily, so the number of rounds is the sample that matters.
16. **Uncertainty:** `skill_ci90` is a 90% interval from a bootstrap over whole rounds/releases (2000 draws, fixed seed);
    absent when fewer than 8 rounds/releases are behind a row.
17. **Per-round view** (`cpif_forecast_rounds.json`): one entry per Riksbank CPIF round with publication date, data cutoff,
    horizon 1-12 summary and the forecast path for horizons -1..12 against outcomes (null while unpublished); 2020:2 is listed
    as a known gap. Paths stop at horizon 12 on purpose (size, and sample sizes beyond that are thin).
18. **YAML trap:** a bare key such as `2021_2023` is read as the number 20212023. Ids in `conventions.yml` must be strings
    (`tests/test_conventions.py` enforces this).

## Checks done on real data (2026-10-22)
- Riksbank round files: observations up to `forecast_cutoff_date` match SCB's CPIF to rounding (2 vs 1 decimal);
  observations after it are forecasts (e.g. round 2022:1 forecast March 2022 CPIF at 3.84%; the outcome was 6.1%).
- KI vintages: months before the release month equal outcomes; the release month already differs (see `docs/sources.md`).

## What the first splits showed (Riksbank CPIF, horizons 1-12, benchmark backtest-2/3, 2026-10-25; the CPIF benchmark is identical in both)
| Target months | n | rounds | skill | 90% interval | bias |
|---|---|---|---|---|---|
| All | 690 | 59 | 0.29 | 0.13 to 0.45 | -0.44 |
| Before 2021 | 379 | 34 | 0.12 | -0.02 to 0.24 | +0.21 |
| 2021-2023 | 177 | 19 | 0.21 | 0.00 to 0.43 | -2.07 |
| 2024 onward | 134 | 15 | 0.66 | 0.51 to 0.77 | -0.14 |
| Without 2021-2023 | 513 | 49 | 0.40 | 0.25 to 0.52 | +0.12 |
Reading: skill is not just the surge (it is higher without it); before 2021 the Riksbank was not clearly better than
"nothing changes"; the large negative bias (and "bias grows with horizon") is entirely the 2021-2023 surge.

## When you add a model or series
Add an entry to `forecasts/conventions.yml` (en + sv) *first*; the test will fail otherwise. Then update this page if a
new rule is needed.

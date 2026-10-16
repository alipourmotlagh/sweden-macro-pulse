# Methodology

## Pipeline
1. **Ingest** (`ingest/`): one adapter per API family. Each fetch is stored as an immutable, date-stamped snapshot in `data/raw/`. Identical content is not stored twice.
2. **Load**: the latest snapshot per series goes into DuckDB schema `raw`.
3. **Transform** (`dbt/`): staging views, mart tables, data tests (uniqueness, not-null, plausibility bands, no future dates, freshness warning).
4. **Export** (`export/`): JSON and CSV with English and Swedish labels from `config/i18n.yml`, schema version in `meta`.
5. **Publish**: GitHub Pages. The website reads the JSON; a monthly "as published" copy is kept in `published/archive/`.

## Rules
- Every chart shows source, period covered, and release date.
- Derived series (for example the 10-year minus policy-rate spread) are labelled own calculation.
- Monthly values are simple averages of daily observations.
- Raw snapshots are never edited; a failed data test blocks publishing.

## Forecasts (month 1: silent logging)
- Every forecast is a row in `forecasts/ledger.csv` (append-only).
- Scoring is relative to a naive baseline, reports interval coverage, and always shows sample size.
- Horizons match the official forecast being compared (KI: calendar-year figures).
- Backtests are labelled indicative (data revisions, possible leakage). Forecasts are experimental, not advice.
- KI's published forecasts (every release since 2015) enter the ledger as model `ki`, labelled as KI's own forecasts.
- Model licences are tracked in `forecasts/model_register.yml`.

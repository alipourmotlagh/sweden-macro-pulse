# sweden-macro-pulse

Open, tested pipeline for Swedish macro and finance data. Pack 1: **the price of borrowing in Sweden**. Data is published as JSON/CSV (English and Swedish labels) via GitHub Pages and consumed by a Next.js site.

**Status: week-1 scaffold.** Adapters are written from API documentation and tested on synthetic fixtures; live endpoints are confirmed on the first GitHub Actions run (see `docs/sources.md`).

## Layout
| Path | Purpose |
|---|---|
| `ingest/` | Adapters (Riksbank REST, SCB PxWebApi 2, KI PxWeb v1 incl. forecast vintages), raw snapshot landing, DuckDB loader |
| `config/` | `series.yml` source registry, `i18n.yml` labels |
| `dbt/` | Staging and marts on DuckDB, data tests |
| `export/` | Public data contract (JSON/CSV, monthly archive) |
| `forecasts/` | Append-only ledger, naive baseline, KI vintages to ledger, scoring, model register |
| `scripts/` | SCB table discovery |
| `docs/` | Methodology, sources and licence status |

## Run locally
```bash
pip install -e ".[dev]"
pytest -q                                   # unit + end-to-end on synthetic data
python -m ingest.run                        # fetch (needs network; Riksbank: optional RIKSBANK_API_KEY)
python -m ingest.load_duckdb
(cd dbt && dbt build --profiles-dir . --project-dir .)
python -m export.export --out site_out
```

## First-time setup on GitHub
1. Create a **public** repo and push this folder.
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Actions → General → Workflow permissions: allow read and write.
4. (Optional) add secret `RIKSBANK_API_KEY`.
5. Actions → "Refresh data and publish" → Run workflow. Expect the first run to surface response-format differences; fix adapters against the real output, then set `status: ok` in `config/series.yml`.
6. Run `python scripts/discover_scb_tables.py`, choose SCB tables, add them to `config/series.yml`.

## Data contract
`v1/rates_monthly.json`, `v1/rates_monthly.csv`, `v1/catalogue.json`, and `archive/YYYY-MM/`. Breaking changes bump the folder to `v2`.

## Licence
Code: choose one (MIT suggested) and add `LICENSE`. Data: follow each source's terms in `docs/sources.md`.

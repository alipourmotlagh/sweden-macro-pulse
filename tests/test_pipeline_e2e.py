"""End to end on synthetic data: raw snapshots -> DuckDB -> dbt build (incl. data tests) -> export."""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from export.export import export
from forecasts.ki_ledger import load_from_duckdb
from ingest.common import land_snapshot
from tests.conftest import ki_rates_payload
from ingest.load_duckdb import load

ROOT = Path(__file__).resolve().parents[1]


def test_end_to_end(tmp_path, riksbank_payloads):
    raw = tmp_path / "raw"
    for sid, payload in riksbank_payloads.items():
        land_snapshot("riksbank", sid, payload, raw_dir=raw)
    land_snapshot("ki_forecast", "ki_rates_monthly__20260325", ki_rates_payload(2.0), raw_dir=raw)
    land_snapshot("ki_forecast", "ki_rates_monthly__20260616", ki_rates_payload(2.4), raw_dir=raw)
    land_snapshot("ki_forecast", "ki_rates_monthly__latest", ki_rates_payload(2.5), raw_dir=raw)
    db = tmp_path / "smp.duckdb"
    counts = load(config_path=str(ROOT / "config" / "series.yml"), db_path=db, raw_dir=raw)
    assert counts["riksbank_observations"] > 1000
    assert counts["ki_observations"] == 3 * 24

    env = {**os.environ, "SMP_DB": str(db)}
    proc = subprocess.run(
        [sys.executable, "-m", "dbt.cli.main", "build", "--profiles-dir", ".", "--project-dir", ".",
         "--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "logs")],
        cwd=ROOT / "dbt", env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]

    import duckdb
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select count(*) from main.mart_ki_rates_vintages").fetchone()[0] == 48  # 'latest' excluded
    ledger = load_from_duckdb(con, "F0604Sek10y", "gov_bond_10y")
    con.close()
    assert {r["made_at"] for r in ledger} == {"2026-03-25", "2026-06-16"} and all(r["horizon"] >= 1 for r in ledger)

    out = tmp_path / "site"
    now = dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)
    export(out, db_path=db, i18n_path=str(ROOT / "config" / "i18n.yml"),
           archive_dir=tmp_path / "archive", now=now)
    data = json.loads((out / "v1" / "rates_monthly.json").read_text())
    assert {s["id"] for s in data["series"]} == {"policy_rate", "tbill_3m", "gov_bond_10y", "spread_10y_policy"}
    assert data["series"][0]["label"]["sv"] == "Styrränta"
    assert "Sveriges riksbank" in data["meta"]["attribution"]["en"]
    assert (out / "v1" / "rates_monthly.csv").read_text().startswith("month,policy_rate")
    assert (out / "archive" / "2026-10" / "rates_monthly.json").exists()
    # archive is not overwritten within the same month
    before = (tmp_path / "archive" / "2026-10" / "rates_monthly.json").read_text()
    export(out, db_path=db, i18n_path=str(ROOT / "config" / "i18n.yml"),
           archive_dir=tmp_path / "archive", now=now.replace(day=20))
    assert (tmp_path / "archive" / "2026-10" / "rates_monthly.json").read_text() == before

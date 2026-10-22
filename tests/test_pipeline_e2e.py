"""End to end on synthetic data: raw snapshots -> DuckDB -> dbt build (incl. data tests) -> export."""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from export.export import export
from forecasts import run_ledger
from forecasts.ledger import read_ledger
from forecasts.ki_ledger import load_from_duckdb
from ingest.common import land_snapshot
from tests.conftest import ki_rates_payload, ki_rates_payload_numeric, scb_cpif_payload, scb_mortgage_payload
from ingest.load_duckdb import load

ROOT = Path(__file__).resolve().parents[1]


def test_end_to_end(tmp_path, riksbank_payloads):
    raw = tmp_path / "raw"
    for sid, payload in riksbank_payloads.items():
        land_snapshot("riksbank", sid, payload, raw_dir=raw)
    land_snapshot("ki_forecast", "ki_rates_monthly__20260325", ki_rates_payload_numeric(2.0), raw_dir=raw)
    land_snapshot("ki_forecast", "ki_rates_monthly__20260616", ki_rates_payload(2.4), raw_dir=raw)
    land_snapshot("ki_forecast", "ki_rates_monthly__latest", ki_rates_payload(2.5), raw_dir=raw)
    land_snapshot("scb", "cpif", scb_cpif_payload(), raw_dir=raw)
    land_snapshot("scb", "mortgage_rates", scb_mortgage_payload(), raw_dir=raw)
    db = tmp_path / "smp.duckdb"
    counts = load(config_path=str(ROOT / "config" / "series.yml"), db_path=db, raw_dir=raw)
    assert counts["riksbank_observations"] > 1000
    assert counts["ki_observations"] == 3 * 24
    assert counts["scb_observations"] == 24 + 2 * 5 * 24

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
    assert {r["made_at"] for r in ledger} == {"2026-03-25", "2026-06-16"} and all(r["horizon"] >= 0 for r in ledger)
    assert any(r["horizon"] == 0 for r in ledger)  # release month itself is a forecast

    # silent forecast logging: naive baseline for all three series + KI vintages (only the variables present)
    ledger_path = tmp_path / "ledger.csv"
    today = dt.date(2026, 10, 21)
    added = run_ledger.run(db_path=db, ledger_path=ledger_path, today=today)
    assert added["naive"] == 3 * 12 and added["ki"] > 0
    led = read_ledger(ledger_path)
    naive = [r for r in led if r["model"] == "naive" and r["series"] == "policy_rate"]
    assert [r["target_period"] for r in naive][:2] == ["2026-11", "2026-12"] and naive[0]["made_at"] == "2026-10-01"
    assert {r["series"] for r in led if r["model"] == "ki"} == {"gov_bond_10y"}
    again = run_ledger.run(db_path=db, ledger_path=ledger_path, today=today)  # same month: nothing new, no error
    assert again == {"naive": 0, "ki": 0}

    out = tmp_path / "site"
    now = dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)
    export(out, db_path=db, i18n_path=str(ROOT / "config" / "i18n.yml"),
           archive_dir=tmp_path / "archive", now=now)
    data = json.loads((out / "v1" / "rates_monthly.json").read_text())
    assert {s["id"] for s in data["series"]} == {"policy_rate", "tbill_3m", "gov_bond_10y", "spread_10y_policy"}
    assert data["series"][0]["label"]["sv"] == "Styrränta"
    assert "Sveriges riksbank" in data["meta"]["attribution"]["en"]
    assert (out / "v1" / "rates_monthly.csv").read_text().startswith("month,policy_rate")
    mort = json.loads((out / "v1" / "mortgage_rates_monthly.json").read_text())
    assert len(mort["series"]) == 10 and all(len(s["points"]) == 24 for s in mort["series"])
    assert {s["id"] for s in mort["series"]} >= {"mortgage_new_floating", "mortgage_outstanding_5y_plus"}
    assert mort["series"][0]["label"]["sv"].startswith("Bolåneränta") and "Sveriges riksbank" in mort["meta"]["attribution"]["en"]
    cpif = json.loads((out / "v1" / "cpif_monthly.json").read_text())
    assert [s["id"] for s in cpif["series"]] == ["cpif_annual"] and cpif["series"][0]["points"][0] == ["2024-02-01", 1.1]  # null first month dropped
    cat = json.loads((out / "v1" / "catalogue.json").read_text())
    assert {s["series_key"] for s in cat["series"] if s["source"] == "scb"} >= {"cpif_annual", "mortgage_new_floating"}
    assert (out / "v1" / "cpif_monthly.csv").exists()
    assert (out / "archive" / "2026-10" / "rates_monthly.json").exists()
    # archive is not overwritten within the same month
    before = (tmp_path / "archive" / "2026-10" / "rates_monthly.json").read_text()
    export(out, db_path=db, i18n_path=str(ROOT / "config" / "i18n.yml"),
           archive_dir=tmp_path / "archive", now=now.replace(day=20))
    assert (tmp_path / "archive" / "2026-10" / "rates_monthly.json").read_text() == before

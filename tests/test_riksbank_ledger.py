import json

from forecasts import riksbank_ledger as rl
from forecasts import run_ledger
from forecasts.ledger import append_rows, read_ledger
from ingest.common import land_snapshot
from tests.conftest import mpd_round_snapshot


def by(rows, series, model=None):
    return {r["target_period"]: r for r in rows if r["series"] == series and (model is None or r["model"] == model)}


def test_only_forecast_periods_are_logged_and_fields_are_right():
    rows = rl.round_rows(mpd_round_snapshot())
    cpif = by(rows, "cpif_annual")
    assert sorted(cpif) == ["2026-09", "2026-10", "2027-09"]            # 2026-07/08 are outcomes (<= cutoff 2026-08-31)
    r = cpif["2026-09"]
    assert (r["model"], r["model_version"], r["made_at"], r["data_vintage"]) == ("riksbank", "2026:3", "2026-09-24", "2026-08-31")
    assert r["horizon"] == 0 and r["point"] == 1.5                     # publication month = nowcast
    assert cpif["2027-09"]["horizon"] == 12
    assert "gdp" not in {x["series"] for x in rows} and not any(x["series"] == "SEQGDPNAASA" for x in rows)


def test_quarterly_series_use_quarter_end_month_and_own_series_names():
    rows = rl.round_rows(mpd_round_snapshot())
    q = by(rows, "policy_rate_qmean")
    assert sorted(q) == ["2026-09", "2026-12"] and q["2026-09"]["horizon"] == 0 and q["2026-12"]["horizon"] == 3
    assert {r["model"] for r in rows if r["series"] == "policy_rate_qmean"} == {"riksbank"}
    fwd = by(rows, "policy_rate_forward_qmean")
    assert sorted(fwd) and {r["model"] for r in rows if r["series"] == "policy_rate_forward_qmean"} == {"market_forward"}
    assert not any(r["series"] == "policy_rate" for r in rows)         # never mixed into the monthly series


def test_negative_horizon_kept_when_cutoff_is_before_publication_month():
    # like real round 2022:1: cutoff 2021-12, published 2022-02-10 -> January 2022 has horizon -1
    snap = mpd_round_snapshot("2022:1", cutoff_month="2021-12-31", end="2022-02-10", cutoff_q="2021-12-31")
    for resp in snap["responses"].values():
        resp["data"][0]["vintages"]["observations"] = [{"dt": "2021-12-31", "value": 4.1}, {"dt": "2022-01-31", "value": 3.75},
                                                      {"dt": "2022-03-31", "value": 3.84}]
    cpif = by(rl.round_rows(snap), "cpif_annual")
    assert cpif["2022-01"]["horizon"] == -1 and cpif["2022-03"]["horizon"] == 1


def test_load_rows_from_landed_snapshots_and_ledger_is_idempotent(tmp_path):
    land_snapshot("riksbank_mpd", "forecasts__2026-3", mpd_round_snapshot(), raw_dir=tmp_path)
    land_snapshot("riksbank_mpd", "series_ids", {"data": []}, raw_dir=tmp_path)          # ignored: not a round folder
    rows = rl.load_rows(tmp_path)
    ledger = tmp_path / "ledger.csv"
    assert append_rows(ledger, rows) == len(rows) > 0 and append_rows(ledger, rows) == 0
    assert {r["model"] for r in read_ledger(ledger)} == {"riksbank", "market_forward"}


def test_run_ledger_reports_riksbank_rows(tmp_path):
    import duckdb
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create table mart_rates_monthly(month date, policy_rate double, tbill_3m double, gov_bond_10y double)")
    con.execute("create table mart_ki_rates_vintages(vintage varchar, variable varchar, period date, value double)")
    for m in range(1, 19):
        con.execute("insert into mart_rates_monthly values (?, 1.5, 1.5, 2.5)", [f"{2025 + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}-01"])
    con.close()
    import datetime as dt
    land_snapshot("riksbank_mpd", "forecasts__2026-3", mpd_round_snapshot(), raw_dir=tmp_path / "raw")
    added = run_ledger.run(db_path=db, ledger_path=tmp_path / "l.csv", today=dt.date(2026, 10, 1), raw_dir=tmp_path / "raw")
    assert added["riksbank"] > 0 and added["naive"] > 0

import datetime as dt

import duckdb

from forecasts import run_ledger, scoring
from forecasts.ledger import append_rows, read_ledger


def months(start, n):
    return [scoring.add_months(start, i) for i in range(n)]


def outcomes_cpif():
    # CPIF outcomes 2024-01..2026-06: a steady rise of 0.1 per month
    return {("cpif_annual", m): round(1.0 + 0.1 * i, 1) for i, m in enumerate(months("2024-01", 30))}


def row(series, model, made_at, target, horizon, point):
    return {"series": series, "model": model, "model_version": "x", "made_at": made_at, "target_period": target,
            "horizon": str(horizon), "point": str(point), "p10": "", "p90": "", "data_vintage": made_at}


def test_backtest_uses_only_values_published_by_then():
    o = outcomes_cpif()
    rows = scoring.backtest_rows(o, {"cpif_annual": {"2025-03-12"}})
    r0 = [r for r in rows if r["horizon"] == 0][0]
    assert r0["target_period"] == "2025-03" and r0["point"] == o[("cpif_annual", "2025-01")]   # made in March -> last = January
    assert {r["horizon"] for r in rows} == set(range(0, 13)) and all(r["model"] == "naive_backtest" for r in rows)
    assert scoring.backtest_rows(o, {"cpif_annual": {"2010-03-12"}}) == []                      # no outcome yet -> no baseline


def test_headline_excludes_h0_and_negative_and_reports_n_and_skill():
    o = outcomes_cpif()
    ledger = [row("cpif_annual", "riksbank", "2025-03-12", "2025-04", 1, o[("cpif_annual", "2025-04")]),      # perfect
              row("cpif_annual", "riksbank", "2025-03-12", "2025-03", 0, 9.0),                                # h0: bad, must not hit headline
              row("cpif_annual", "riksbank", "2025-03-12", "2025-02", -1, 9.0)]                              # negative: ditto
    res = scoring.score_all(ledger, o)
    head = [r for r in res["headline"] if r["model"] == "riksbank"][0]
    assert head["n"] == 1 and head["mae"] == 0 and head["n_matched"] == 1
    assert head["mae_naive_matched"] > 0 and head["skill"] == 1.0              # perfect vs a lagging random walk
    other = {r["group"]: r for r in res["other_horizons"] if r["model"] == "riksbank"}
    assert other["h0"]["n"] == 1 and other["h_negative"]["n"] == 1 and other["h0"]["mae"] > 5
    nb = [r for r in res["headline"] if r["model"] == "naive_backtest"][0]
    assert "skill" not in nb and nb["n"] > 0


def test_unscored_until_outcome_exists():
    o = outcomes_cpif()
    res = scoring.score_all([row("cpif_annual", "riksbank", "2026-06-10", "2027-01", 7, 2.0)], o)
    assert not [r for r in res["headline"] if r["model"] == "riksbank"]            # target month has no outcome yet


def test_outcomes_complete_months_and_quarterly_mean(tmp_path):
    con = duckdb.connect()
    con.execute("create table mart_cpif_monthly(series_key varchar, table_id varchar, month date, value double)")
    con.execute("insert into mart_cpif_monthly values ('cpif_annual','T',date '2026-08-01',0.7)")
    con.execute("create table mart_rates_monthly(month date, policy_rate double, tbill_3m double, gov_bond_10y double)")
    for m, v in (("2026-04-01", 2.0), ("2026-05-01", 2.0), ("2026-06-01", 1.5), ("2026-07-01", 1.5), ("2026-10-01", 9.9)):
        con.execute("insert into mart_rates_monthly values (?, ?, 1.0, 2.0)", [m, v])
    o = scoring.load_outcomes(con, today=dt.date(2026, 10, 24))
    assert ("policy_rate", "2026-10") not in o                                  # current month is incomplete: excluded
    assert o[("policy_rate_qmean", "2026-06")] == round((2.0 + 2.0 + 1.5) / 3, 4)
    assert ("policy_rate_qmean", "2026-09") not in o                            # needs all three months


def test_forward_path_is_scored_against_actual_policy_rate():
    o = {("policy_rate_qmean", "2026-06"): 1.75}
    res = scoring.score_all([row("policy_rate_forward_qmean", "market_forward", "2026-03-10", "2026-06", 3, 2.25)], o)
    assert res["headline"][0]["bias"] == 0.5 and res["headline"][0]["series"] == "policy_rate_forward_qmean"


def test_cpif_naive_is_stable_when_new_data_is_published_within_the_month(tmp_path):
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create table mart_cpif_monthly(series_key varchar, table_id varchar, month date, value double)")
    wobble = lambda i: round(2.0 + ((i * 7) % 5) * 0.1, 1)                      # goes up and down, so the band straddles the point
    for i, m in enumerate(months("2024-01", 30)):                              # 2024-01 .. 2026-06
        con.execute("insert into mart_cpif_monthly values ('cpif_annual','T',?,?)", [m + "-01", wobble(i)])
    con.close()
    con = duckdb.connect(str(db), read_only=True)
    rows = run_ledger.cpif_naive_rows(con, dt.date(2026, 8, 3))                  # made in August -> last published = June
    con.close()
    assert len(rows) == 12 and rows[0]["data_vintage"] == "2026-06-01" and rows[0]["target_period"] == "2026-09"
    assert rows[0]["point"] == wobble(29) and rows[0]["p10"] <= rows[0]["point"] <= rows[0]["p90"]
    ledger = tmp_path / "l.csv"
    assert append_rows(ledger, rows) == 12
    con = duckdb.connect(str(db))
    con.execute("insert into mart_cpif_monthly values ('cpif_annual','T',date '2026-07-01',4.0)")   # July published on the 10th
    con.close()
    con = duckdb.connect(str(db), read_only=True)
    again = run_ledger.cpif_naive_rows(con, dt.date(2026, 8, 17))                # a later weekly run, same month
    con.close()
    assert append_rows(ledger, again) == 0                                       # identical: no conflict, nothing new
    assert len(read_ledger(ledger)) == 12

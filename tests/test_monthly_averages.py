"""How monthly averages of the daily Riksbank series are formed (the rule the methodology page describes)."""
from pathlib import Path

import duckdb

SQL = (Path(__file__).resolve().parents[1] / "dbt" / "models" / "marts" / "mart_rates_monthly.sql").read_text()


def run_mart(rows):
    con = duckdb.connect()
    con.execute("create table stg_riksbank_observations(series_key varchar, obs_date date, value double)")
    for key, day, value in rows:
        con.execute("insert into stg_riksbank_observations values (?, ?, ?)", [key, day, value])
    sql = SQL.replace("{{ ref('stg_riksbank_observations') }}", "stg_riksbank_observations")
    assert "{{" not in sql
    return {r[0].isoformat(): r[1:] for r in con.execute(sql).fetchall()}


def test_monthly_average_is_a_simple_mean_of_the_days_that_have_a_value():
    # 3 January days only (gaps for weekend, holiday and a missing day): mean of those three, no filling, no weighting
    rows = [("policy_rate", "2026-01-02", 2.0), ("policy_rate", "2026-01-05", 2.0), ("policy_rate", "2026-01-09", 3.0),
            ("gov_bond_10y", "2026-01-02", 3.0), ("gov_bond_10y", "2026-01-05", 3.5)]
    jan = run_mart(rows)["2026-01-01"]            # columns: policy_rate, tbill_3m, gov_bond_10y, spread
    assert jan[0] == round((2.0 + 2.0 + 3.0) / 3, 4) and jan[2] == 3.25 and jan[1] is None


def test_month_without_a_series_has_no_value_for_it_and_no_spread():
    rows = [("policy_rate", "2026-01-02", 2.0), ("gov_bond_10y", "2026-02-02", 3.0)]
    mart = run_mart(rows)
    assert mart["2026-02-01"][0] is None and mart["2026-02-01"][3] is None      # no policy-rate day in February
    assert mart["2026-01-01"][2] is None and mart["2026-01-01"][3] is None


def test_spread_is_computed_from_unrounded_averages_then_rounded_to_four_decimals():
    rows = [("policy_rate", "2026-03-02", 2.0), ("policy_rate", "2026-03-03", 2.0), ("policy_rate", "2026-03-04", 2.5),
            ("gov_bond_10y", "2026-03-02", 3.1), ("gov_bond_10y", "2026-03-03", 3.1), ("gov_bond_10y", "2026-03-04", 3.2)]
    mar = run_mart(rows)["2026-03-01"]
    pol, bond = (2.0 + 2.0 + 2.5) / 3, (3.1 + 3.1 + 3.2) / 3
    assert mar[0] == round(pol, 4) and mar[2] == round(bond, 4) and mar[3] == round(bond - pol, 4)

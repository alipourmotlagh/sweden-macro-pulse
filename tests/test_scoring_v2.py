"""Benchmark fairness (backtest-2), eras, bootstrap and the per-round view."""
from forecasts import scoring
from tests.test_scoring import months, outcomes_cpif, row


def rb(made_at, target, horizon, point, cutoff, rnd="x"):
    r = row("cpif_annual", "riksbank", made_at, target, horizon, point)
    r["data_vintage"], r["model_version"] = cutoff, rnd
    return r


def test_benchmark_gets_the_riksbank_round_cutoff_not_a_fixed_lag():
    o = {("cpif_annual", m): v for m, v in zip(months("2025-01", 4), (1.0, 2.0, 3.0, 4.0))}   # Jan..Apr
    # round made 2025-03-24 with data up to February: the benchmark must use February (2.0), not January (1.0)
    r = rb("2025-03-24", "2025-04", 1, 4.0, "2025-02-28")
    assert scoring.info_month(r) == "2025-02"
    s = [x for x in scoring._scored([r], o) if x["model"] == "riksbank"][0]
    assert s["naive"] == 2.0 and s["error"] == 0.0
    # a model without a cutoff keeps the lag rule
    k = row("policy_rate", "ki", "2025-03-12", "2025-04", 1, 1.0)
    assert scoring.info_month(k) == "2025-02"
    c = row("cpif_annual", "naive", "2025-03-01", "2025-04", 1, 1.0)
    assert scoring.info_month(c) == "2025-01"


def test_eras_partition_by_target_month_and_count_rounds():
    o = {("cpif_annual", m): 2.0 for m in months("2019-01", 80)}
    rows = []
    for made, tgt in (("2019-06-10", "2019-07"), ("2021-06-10", "2021-07"), ("2022-06-10", "2022-07"), ("2025-06-10", "2025-07")):
        rows.append(rb(made, tgt, 1, 3.0, made[:7] + "-01", rnd=made))
    res = scoring.score_all(rows, o)
    era = {(r["era"], r["model"]): r for r in res["by_era"]}
    assert era[("before_2021", "riksbank")]["n"] == 1 and era[("surge_2021_2023", "riksbank")]["n"] == 2
    assert era[("surge_2021_2023", "riksbank")]["n_releases"] == 2 and era[("from_2024", "riksbank")]["n"] == 1
    assert era[("excl_surge_2021_2023", "riksbank")]["n"] == 2
    assert {e for e, _ in era} == {e for e, _ in scoring.ERAS}


def test_bootstrap_is_deterministic_and_resamples_rounds():
    items = [{"made_at": f"r{i}", "error": 0.5, "naive": 3.0, "actual": 2.0} for i in range(10)]    # every round: model 0.5, naive 1.0
    a, b = scoring.bootstrap_skill_ci(items), scoring.bootstrap_skill_ci(items)
    assert a == b == [0.5, 0.5]                                                                      # identical rounds: skill 0.5 always
    assert scoring.bootstrap_skill_ci(items[:3]) is None                                              # too few rounds: no interval
    mixed = [{"made_at": f"r{i}", "error": 0.1 if i % 2 else 2.0, "naive": 3.0, "actual": 2.0} for i in range(20)]
    lo, hi = scoring.bootstrap_skill_ci(mixed)
    assert lo < hi and -1 < lo < 1 and hi < 1.0


def test_headline_rows_carry_release_counts_and_interval():
    o = outcomes_cpif()
    rows = [rb(f"2025-{m:02d}-12", scoring.add_months(f"2025-{m:02d}", h), h, 1.0, f"2025-{m:02d}-01", rnd=f"2025:{m}")
            for m in range(1, 11) for h in (1, 2)]
    res = scoring.score_all(rows, o)
    head = [r for r in res["headline"] if r["model"] == "riksbank"][0]
    assert head["n_releases"] == 10 and head["n_target_months"] >= 10 and "skill_ci90" in head


def test_rounds_view_paths_summary_and_pending_outcomes():
    o = {("cpif_annual", m): 2.0 for m in months("2024-01", 12)}                      # outcomes through 2024-12
    rows = [rb("2024-11-20", scoring.add_months("2024-11", h), h, 2.5, "2024-10-31", rnd="2024:5") for h in range(-1, 5)]
    rows.append(rb("2024-11-20", "2026-12", 25, 9.9, "2024-10-31", rnd="2024:5"))       # beyond the path limit: left out
    view = scoring.rounds_view(rows, o)
    assert len(view) == 1 and view[0]["round"] == "2024:5" and view[0]["published"] == "2024-11-20"
    assert view[0]["data_cutoff"] == "2024-10-31" and len(view[0]["points"]) == 6
    pts = {p[0]: p for p in view[0]["points"]}
    assert pts["2024-12"][3] == 2.0 and pts["2025-03"][3] is None                       # outcome null while unpublished
    assert view[0]["n_scored_h1_12"] == 1 and view[0]["n_pending_h1_12"] == 3
    assert view[0]["mae_h1_12"] == 0.5 and view[0]["bias_h1_12"] == 0.5
    assert view[0]["benchmark_mae_h1_12"] == 0.0                                          # cutoff October = 2.0 = outcome

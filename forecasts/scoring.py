"""Score the ledger against outcomes. Pure functions plus one DuckDB loader.

Rules (documented in forecasts/conventions.yml and docs/forecast_conventions.md; shown to users):
  * Headline = horizon 1..12 only. Horizon 0 (nowcast, partly known) and negative horizons are reported separately.
  * Every row carries its sample size n, the number of distinct releases/rounds behind it, and the number of target months.
    n counts forecasts, but forecasts from one round overlap heavily, so the number of rounds is the honest sample size.
  * Outcomes: CPIF from SCB; interest rates = our monthly averages of the Riksbank's daily data, COMPLETE months only;
    quarterly series = mean of the three monthly averages (all three must exist).
  * Benchmark `naive_backtest` (version backtest-2) is a random walk computed here in hindsight, never written to the
    ledger. It gets the SAME information date as the forecast it is compared with:
      - Riksbank CPIF: the value for the round's own data cutoff month (the round saw that month, so must the benchmark);
      - everything else: the last month that is complete/published by the publication month (INFO_LAG).
    (backtest-1 always used the value two months back and flattered the Riksbank: skill 0.37 became 0.29.)
  * skill = 1 - MAE(model) / MAE(benchmark) on the SAME target months and horizons. Its uncertainty is a bootstrap that
    resamples whole rounds/releases (clusters), seed fixed so the numbers do not change between runs.
  * Eras are fixed in advance, by target month (see ERAS). Do not add or move them after looking at results.
"""
from __future__ import annotations

import datetime as dt
import math
import random
import statistics

HEADLINE = range(1, 13)
BACKTEST_HORIZONS = range(0, 13)
BACKTEST_MODEL = "naive_backtest"
BACKTEST_VERSION = "backtest-2"
# series -> months between the made_at month and the last value that would have been published/complete by then
INFO_LAG = {"cpif_annual": 2, "policy_rate": 1, "tbill_3m": 1, "gov_bond_10y": 1}
CUTOFF_MODELS = {("cpif_annual", "riksbank")}                      # rows whose data_vintage is the data cutoff date
OUTCOME_OF = {"policy_rate_forward_qmean": "policy_rate_qmean"}     # market path is judged against the actual policy rate
ERAS = [   # (id, test on the target month 'YYYY-MM'); labels and wording live in forecasts/conventions.yml
    ("before_2021", lambda t: t < "2021-01"),
    ("surge_2021_2023", lambda t: "2021-01" <= t < "2024-01"),
    ("from_2024", lambda t: t >= "2024-01"),
    ("excl_surge_2021_2023", lambda t: not ("2021-01" <= t < "2024-01")),
]
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 1
MIN_CLUSTERS_FOR_INTERVAL = 8


def add_months(period: str, n: int) -> str:
    y, m = int(period[:4]), int(period[5:7])
    k = y * 12 + (m - 1) + n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def load_outcomes(con, today: dt.date | None = None) -> dict[tuple[str, str], float]:
    """{(series, 'YYYY-MM'): outcome}. Complete months only for rates; quarterly = mean of 3 monthly averages."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    this_month = today.replace(day=1)
    out: dict[tuple[str, str], float] = {}
    for month, value in con.execute("select month, value from main.mart_cpif_monthly").fetchall():
        out[("cpif_annual", month.strftime("%Y-%m"))] = float(value)
    for row in con.execute("select month, policy_rate, tbill_3m, gov_bond_10y from main.mart_rates_monthly").fetchall():
        if row[0] >= this_month:
            continue                                                  # month not finished: average not final
        for name, v in zip(("policy_rate", "tbill_3m", "gov_bond_10y"), row[1:]):
            if v is not None:
                out[(name, row[0].strftime("%Y-%m"))] = float(v)
    for (series, period) in list(out):
        if series == "policy_rate" and period[5:7] in ("03", "06", "09", "12"):
            parts = [out.get(("policy_rate", add_months(period, -k))) for k in (0, 1, 2)]
            if all(p is not None for p in parts):
                out[("policy_rate_qmean", period)] = round(statistics.mean(parts), 4)
    return out


def info_month(row: dict) -> str | None:
    """The last month whose value the forecaster could use: the benchmark gets exactly this value."""
    series = row["series"]
    if (series, row["model"]) in CUTOFF_MODELS and row.get("data_vintage"):
        return str(row["data_vintage"])[:7]
    lag = INFO_LAG.get(series)
    return None if lag is None else add_months(row["made_at"][:7], -lag)


def backtest_rows(outcomes: dict, requests: dict[str, set[tuple[str, str]]]) -> list[dict]:
    """Hindsight random-walk baseline for each (series, made_at, info_month) that some model needed."""
    rows = []
    for series, pairs in requests.items():
        for made_at, info in sorted(pairs):
            last = outcomes.get((series, info))
            if last is None:
                continue
            month = made_at[:7]
            for h in BACKTEST_HORIZONS:
                rows.append({"series": series, "model": BACKTEST_MODEL, "model_version": BACKTEST_VERSION,
                             "made_at": made_at, "target_period": add_months(month, h), "horizon": h, "point": last,
                             "p10": "", "p90": "", "data_vintage": info + "-01", "info_month": info})
    return rows


def _stats(errors: list[float]) -> dict:
    n = len(errors)
    return {"n": n, "mae": round(statistics.mean(abs(e) for e in errors), 3),
            "rmse": round(math.sqrt(statistics.mean(e * e for e in errors)), 3), "bias": round(statistics.mean(errors), 3)}


def bootstrap_skill_ci(matched: list[dict]) -> list[float] | None:
    """90% interval for skill, resampling whole rounds/releases (clusters keyed by made_at).

    With equal n on both sides, skill = 1 - sum|model error| / sum|benchmark error|, so only per-cluster sums are needed.
    """
    clusters: dict[str, list[float]] = {}
    for i in matched:
        c = clusters.setdefault(i["made_at"], [0.0, 0.0])
        c[0] += abs(i["error"])
        c[1] += abs(i["naive"] - i["actual"])
    sums = list(clusters.values())
    if len(sums) < MIN_CLUSTERS_FOR_INTERVAL:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        pick = [sums[rng.randrange(len(sums))] for _ in sums]
        denom = sum(p[1] for p in pick)
        if denom > 0:
            draws.append(1 - sum(p[0] for p in pick) / denom)
    if not draws:
        return None
    draws.sort()
    return [round(draws[int(0.05 * (len(draws) - 1))], 3), round(draws[int(0.95 * (len(draws) - 1))], 3)]


def _summarise(items: list[dict]) -> dict:
    out = _stats([i["error"] for i in items])
    out["n_releases"] = len({i["made_at"] for i in items})
    out["n_target_months"] = len({i["target"] for i in items})
    out["first_target"], out["last_target"] = min(i["target"] for i in items), max(i["target"] for i in items)
    matched = [i for i in items if i["naive"] is not None]
    if items[0]["model"] != BACKTEST_MODEL and matched:
        mae_m = statistics.mean(abs(i["error"]) for i in matched)
        mae_n = statistics.mean(abs(i["naive"] - i["actual"]) for i in matched)
        out.update({"n_matched": len(matched), "mae_matched": round(mae_m, 3), "mae_naive_matched": round(mae_n, 3),
                    "skill": round(1 - mae_m / mae_n, 3) if mae_n > 0 else None,
                    "skill_ci90": bootstrap_skill_ci(matched) if mae_n > 0 else None})
    cov = [float(i["p10"]) <= i["actual"] <= float(i["p90"]) for i in items if i["p10"] not in ("", None)]
    if cov:
        out["coverage_80"] = round(sum(cov) / len(cov), 3)
    return out


def _scored(ledger: list[dict], outcomes: dict) -> list[dict]:
    requests: dict[str, set[tuple[str, str]]] = {}
    for r in ledger:
        im = info_month(r)
        if im is not None:
            requests.setdefault(r["series"], set()).add((r["made_at"], im))
    bench = backtest_rows(outcomes, requests)
    baseline = {(r["series"], r["target_period"], int(r["horizon"]), r["info_month"]): float(r["point"]) for r in bench}
    scored = []
    for r in list(ledger) + bench:
        series, target, h = r["series"], r["target_period"], int(r["horizon"])
        actual = outcomes.get((OUTCOME_OF.get(series, series), target))
        if actual is None:
            continue
        im = r.get("info_month") or info_month(r)
        scored.append({"series": series, "model": r["model"], "version": r.get("model_version"), "h": h, "target": target,
                       "made_at": r["made_at"], "error": float(r["point"]) - actual, "actual": actual,
                       "naive": baseline.get((series, target, h, im)), "p10": r.get("p10"), "p90": r.get("p90")})
    return scored


def score_all(ledger: list[dict], outcomes: dict) -> dict:
    """Returns {"headline", "other_horizons", "by_horizon", "by_era"}; every row carries n and release counts."""
    scored = _scored(ledger, outcomes)

    def group(pred, label: str, items=scored) -> list[dict]:
        buckets: dict[tuple, list[dict]] = {}
        for s in items:
            if pred(s["h"]):
                buckets.setdefault((s["series"], s["model"]), []).append(s)
        return [{"series": k[0], "model": k[1], "group": label, **_summarise(v)} for k, v in sorted(buckets.items())]

    by_h: dict[tuple, list[dict]] = {}
    for s in scored:
        if s["h"] <= 12:
            by_h.setdefault((s["series"], s["model"], s["h"]), []).append(s)
    by_era = []
    headline_items = [s for s in scored if s["h"] in HEADLINE]
    for era_id, test in ERAS:
        for row in group(lambda h: True, "headline_h1_12", [s for s in headline_items if test(s["target"])]):
            by_era.append({"era": era_id, **row})
    return {
        "headline": group(lambda h: h in HEADLINE, "headline_h1_12"),
        "other_horizons": group(lambda h: h == 0, "h0") + group(lambda h: h < 0, "h_negative"),
        "by_horizon": [{"series": k[0], "model": k[1], "horizon": k[2], **_stats([i["error"] for i in v])}
                       for k, v in sorted(by_h.items())],
        "by_era": by_era,
    }


ROUND_POINT_FIELDS = ["target", "horizon", "forecast", "outcome", "benchmark"]
ROUND_MAX_HORIZON = 12


def rounds_view(ledger: list[dict], outcomes: dict, *, series: str = "cpif_annual", model: str = "riksbank") -> list[dict]:
    """One entry per round: dates, summary of horizons 1..12 against outcomes, and the forecast path (-1..12)."""
    rows = [r for r in ledger if r["series"] == series and r["model"] == model]
    requests = {series: {(r["made_at"], info_month(r)) for r in rows}}
    bench = {(r["target_period"], int(r["horizon"]), r["info_month"]): float(r["point"])
             for r in backtest_rows(outcomes, requests)}
    by_round: dict[str, list[dict]] = {}
    for r in rows:
        by_round.setdefault(r["model_version"], []).append(r)
    out = []
    for rnd, items in sorted(by_round.items(), key=lambda kv: kv[1][0]["made_at"]):
        items = sorted((i for i in items if int(i["horizon"]) <= ROUND_MAX_HORIZON), key=lambda i: i["target_period"])
        if not items:
            continue
        im = info_month(items[0])
        points, errs, nerrs, pending = [], [], [], 0
        for i in items:
            h, t = int(i["horizon"]), i["target_period"]
            actual = outcomes.get((series, t))
            b = bench.get((t, h, im))
            points.append([t, h, float(i["point"]), actual, b])
            if 1 <= h <= ROUND_MAX_HORIZON:
                if actual is None:
                    pending += 1
                else:
                    errs.append(float(i["point"]) - actual)
                    if b is not None:
                        nerrs.append(b - actual)
        entry = {"round": rnd, "published": items[0]["made_at"], "data_cutoff": items[0]["data_vintage"],
                 "n_scored_h1_12": len(errs), "n_pending_h1_12": pending,
                 "mae_h1_12": round(statistics.mean(abs(e) for e in errs), 3) if errs else None,
                 "bias_h1_12": round(statistics.mean(errs), 3) if errs else None,
                 "benchmark_mae_h1_12": round(statistics.mean(abs(e) for e in nerrs), 3) if nerrs else None,
                 "points": points}
        out.append(entry)
    return out

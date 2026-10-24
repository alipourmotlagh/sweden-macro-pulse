"""Score the ledger against outcomes. Pure functions plus one DuckDB loader.

Rules (documented in forecasts/conventions.yml and docs/forecast_conventions.md; shown to users):
  * Headline = horizon 1..12 only. Horizon 0 (nowcast, partly known) and negative horizons are reported separately.
  * Every row carries its sample size n. Months without a published outcome are simply not scored yet.
  * Outcomes: CPIF from SCB; interest rates = our monthly averages of the Riksbank's daily data, COMPLETE months only;
    quarterly series = mean of the three monthly averages (all three must exist).
  * Benchmark `naive_backtest` is computed here in hindsight for every date a model published (random walk from the
    last value that was published by then), because the real-time `naive` only started in 2026-10. It is labelled a
    backtest and never written to the ledger. skill = 1 - MAE(model) / MAE(naive_backtest) on the SAME target months
    and horizons; positive = better than the baseline.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics

HEADLINE = range(1, 13)
BACKTEST_HORIZONS = range(0, 13)
BACKTEST_MODEL = "naive_backtest"
# series -> months between the made_at month and the last value that would have been published/complete by then
INFO_LAG = {"cpif_annual": 2, "policy_rate": 1, "tbill_3m": 1, "gov_bond_10y": 1}
OUTCOME_OF = {"policy_rate_forward_qmean": "policy_rate_qmean"}     # market path is judged against the actual policy rate
MIN_COMPLETE = {"policy_rate", "tbill_3m", "gov_bond_10y"}


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


def backtest_rows(outcomes: dict, made_ats: dict[str, set[str]]) -> list[dict]:
    """Hindsight random-walk baseline for each (series, made_at) that some model published."""
    rows = []
    for series, dates in made_ats.items():
        lag = INFO_LAG.get(series)
        if lag is None:
            continue
        for made_at in sorted(dates):
            month = made_at[:7]
            last = outcomes.get((series, add_months(month, -lag)))
            if last is None:
                continue
            for h in BACKTEST_HORIZONS:
                rows.append({"series": series, "model": BACKTEST_MODEL, "model_version": "backtest-1", "made_at": made_at,
                             "target_period": add_months(month, h), "horizon": h, "point": last, "p10": "", "p90": ""})
    return rows


def _stats(errors: list[float]) -> dict:
    n = len(errors)
    return {"n": n, "mae": round(statistics.mean(abs(e) for e in errors), 3),
            "rmse": round(math.sqrt(statistics.mean(e * e for e in errors)), 3), "bias": round(statistics.mean(errors), 3)}


def score_all(ledger: list[dict], outcomes: dict) -> dict:
    """Returns {"headline": [...], "other_horizons": [...], "by_horizon": [...]}; all rows carry n."""
    made_ats: dict[str, set[str]] = {}
    for r in ledger:
        made_ats.setdefault(r["series"], set()).add(r["made_at"])
    rows = [dict(r) for r in ledger] + backtest_rows(outcomes, made_ats)

    scored = []                      # (series, model, horizon, target, error, baseline_point, p10, p90, actual)
    baseline = {(r["series"], r["target_period"], int(r["horizon"])): float(r["point"]) for r in rows if r["model"] == BACKTEST_MODEL}
    for r in rows:
        series, target, h = r["series"], r["target_period"], int(r["horizon"])
        actual = outcomes.get((OUTCOME_OF.get(series, series), target))
        if actual is None:
            continue
        scored.append({"series": series, "model": r["model"], "h": h, "target": target, "made_at": r["made_at"],
                       "error": float(r["point"]) - actual, "actual": actual,
                       "naive": baseline.get((series, target, h)), "p10": r.get("p10"), "p90": r.get("p90")})

    def summarise(items: list[dict]) -> dict:
        out = _stats([i["error"] for i in items])
        out["first_target"], out["last_target"] = min(i["target"] for i in items), max(i["target"] for i in items)
        matched = [i for i in items if i["naive"] is not None]
        if items[0]["model"] != BACKTEST_MODEL and matched:
            mae_m = statistics.mean(abs(i["error"]) for i in matched)
            mae_n = statistics.mean(abs(i["naive"] - i["actual"]) for i in matched)
            out.update({"n_matched": len(matched), "mae_matched": round(mae_m, 3), "mae_naive_matched": round(mae_n, 3),
                        "skill": round(1 - mae_m / mae_n, 3) if mae_n > 0 else None})
        cov = [float(i["p10"]) <= i["actual"] <= float(i["p90"]) for i in items if i["p10"] not in ("", None)]
        if cov:
            out["coverage_80"] = round(sum(cov) / len(cov), 3)
        return out

    def group(pred, label: str) -> list[dict]:
        buckets: dict[tuple, list[dict]] = {}
        for s in scored:
            if pred(s["h"]):
                buckets.setdefault((s["series"], s["model"]), []).append(s)
        return [{"series": k[0], "model": k[1], "group": label, **summarise(v)} for k, v in sorted(buckets.items())]

    by_h: dict[tuple, list[dict]] = {}
    for s in scored:
        if s["h"] <= 12:
            by_h.setdefault((s["series"], s["model"], s["h"]), []).append(s)
    return {
        "headline": group(lambda h: h in HEADLINE, "headline_h1_12"),
        "other_horizons": group(lambda h: h == 0, "h0") + group(lambda h: h < 0, "h_negative"),
        "by_horizon": [{"series": k[0], "model": k[1], "horizon": k[2], **_stats([i["error"] for i in v])}
                       for k, v in sorted(by_h.items())],
    }

"""Forecast ledger: append-only record of every forecast we make, scored later against actuals.

Rule: a row is never edited or deleted. A forecast is identified by (series, model, made_at, target_period).
Month 1 = silent logging. Month 2 = public scoreboard.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

LEDGER_COLUMNS = ["series", "model", "model_version", "made_at", "target_period", "horizon",
                  "point", "p10", "p90", "data_vintage"]
KEY = ("series", "model", "made_at", "target_period")


class LedgerError(ValueError):
    pass


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def append_rows(path: Path, rows: list[dict]) -> int:
    """Append new forecasts. Exact duplicates (same key) are skipped, conflicting ones raise."""
    existing = {tuple(r[k] for k in KEY): r for r in read_ledger(path)}
    fresh = []
    for row in rows:
        missing = [c for c in LEDGER_COLUMNS if c not in row]
        if missing:
            raise LedgerError(f"missing columns: {missing}")
        key = tuple(str(row[k]) for k in KEY)
        if key in existing:
            if any(str(existing[key][c]) != str(row[c]) for c in LEDGER_COLUMNS):
                raise LedgerError(f"ledger is append-only; conflicting row for {key}")
            continue
        existing[key] = row
        fresh.append({c: row[c] for c in LEDGER_COLUMNS})
    if fresh:
        new_file = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS)
            if new_file:
                w.writeheader()
            w.writerows(fresh)
    return len(fresh)


def naive_forecast(history: list[float], horizons: int, *, series: str, made_at: str,
                   target_periods: list[str], data_vintage: str, lead: int = 0) -> list[dict]:
    """Random-walk baseline: last value, with empirical 10/90% band from (h + lead)-step changes in history.

    `lead` = extra months between the last observation and the month before the first target. Default 0 keeps the
    rate baselines exactly as logged so far (their band is slightly narrow: true distance is h+1; see docs/backlog.md).
    """
    if len(history) < 12:
        raise LedgerError("need at least 12 observations for a baseline band")
    last = history[-1]
    rows = []
    for h in range(1, horizons + 1):
        step = h + lead
        diffs = sorted(history[i + step] - history[i] for i in range(len(history) - step))
        lo = diffs[int(0.1 * (len(diffs) - 1))]
        hi = diffs[int(0.9 * (len(diffs) - 1))]
        rows.append({"series": series, "model": "naive", "model_version": "1", "made_at": made_at,
                     "target_period": target_periods[h - 1], "horizon": h,
                     "point": round(last, 4), "p10": round(last + lo, 4), "p90": round(last + hi, 4),
                     "data_vintage": data_vintage})
    return rows


def score(ledger: list[dict], actuals: dict[tuple[str, str], float]) -> list[dict]:
    """Per (series, model, horizon): n, MAE, interval coverage. Sample size is always reported."""
    groups: dict[tuple, list[dict]] = {}
    for r in ledger:
        a = actuals.get((r["series"], r["target_period"]))
        if a is None:
            continue
        groups.setdefault((r["series"], r["model"], int(r["horizon"])), []).append({**r, "actual": a})
    out = []
    for (series, model, h), items in sorted(groups.items()):
        errs = [abs(float(i["point"]) - i["actual"]) for i in items]
        cov = [float(i["p10"]) <= i["actual"] <= float(i["p90"]) for i in items]
        out.append({"series": series, "model": model, "horizon": h, "n": len(items),
                    "mae": round(statistics.mean(errs), 4), "coverage_80": round(sum(cov) / len(cov), 3)})
    return out

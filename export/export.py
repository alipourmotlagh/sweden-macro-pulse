"""Export dbt marts to the public data contract (JSON + CSV, en/sv labels).

Layout written under --out (default site_out/):
    v1/rates_monthly.json   {meta, series:[{id,label:{en,sv},unit,points:[[YYYY-MM-DD,value],...]}]}
    v1/rates_monthly.csv
    v1/mortgage_rates_monthly.json / .csv   households' housing-loan rates (SCB TAB5783)
    v1/cpif_monthly.json / .csv             CPIF annual change (SCB TAB6590)
    v1/catalogue.json       coverage + freshness per series
    archive/<YYYY-MM>/...   monthly "as published" copy (kept in repo under published/archive)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shutil
from pathlib import Path

import duckdb
import yaml

DB_PATH = Path(os.environ.get("SMP_DB", "data/smp.duckdb"))
SCHEMA_VERSION = "1.0"
RATE_COLUMNS = ["policy_rate", "tbill_3m", "gov_bond_10y", "spread_10y_policy"]


def build_rates_payload(con, i18n: dict, generated_at: str) -> dict:
    rows = con.execute("select month, " + ", ".join(RATE_COLUMNS) + " from main.mart_rates_monthly order by month").fetchall()
    series = []
    for idx, col in enumerate(RATE_COLUMNS, start=1):
        points = [[r[0].isoformat(), r[idx]] for r in rows if r[idx] is not None]
        series.append({
            "id": col,
            "label": i18n["series"][col],
            "unit": "%",
            "unit_label": i18n["units"]["%"],
            "derived": col == "spread_10y_policy",
            "points": points,
        })
    return {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "frequency": "monthly average",
            "attribution": i18n["attribution"]["riksbank"],
            "disclaimer": i18n["disclaimer"],
            "last_period": rows[-1][0].isoformat() if rows else None,
        },
        "series": series,
    }


def build_long_payload(con, mart: str, i18n: dict, generated_at: str, *, attribution_key: str) -> dict:
    """Payload for a long mart (month, series_key, value) in the same shape as the rates payload."""
    rows = con.execute(f"select month, series_key, value from main.{mart} order by series_key, month").fetchall()
    by_key: dict[str, list] = {}
    for month, key, value in rows:
        by_key.setdefault(key, []).append([month.isoformat(), value])
    series = [{"id": key, "label": i18n["series"][key], "unit": "%", "unit_label": i18n["units"]["%"],
               "derived": False, "points": points} for key, points in by_key.items()]
    last = max((p[-1][0] for p in by_key.values()), default=None)
    return {"meta": {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "frequency": "monthly",
                     "attribution": i18n["attribution"][attribution_key], "disclaimer": i18n["disclaimer"],
                     "last_period": last}, "series": series}


def build_catalogue(con, generated_at: str) -> dict:
    cols = ["source", "series_key", "source_id", "first_obs", "last_obs", "n_obs", "days_since_last_obs"]
    rows = con.execute("select " + ", ".join(cols) + " from main.mart_catalogue order by 1, 2").fetchall()
    items = [{c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)} for r in rows]
    return {"meta": {"schema_version": SCHEMA_VERSION, "generated_at": generated_at}, "series": items}


def write_csv(payload: dict, path: Path) -> None:
    months = sorted({p[0] for s in payload["series"] for p in s["points"]})
    lookup = {s["id"]: dict(map(tuple, s["points"])) for s in payload["series"]}
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["month"] + [s["id"] for s in payload["series"]])
        for m in months:
            w.writerow([m] + [lookup[s["id"]].get(m, "") for s in payload["series"]])


def export(out: Path, db_path: Path = DB_PATH, i18n_path: str = "config/i18n.yml",
           archive_dir: Path = Path("published/archive"), now: dt.datetime | None = None) -> list[Path]:
    now = now or dt.datetime.now(dt.timezone.utc)
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    i18n = yaml.safe_load(Path(i18n_path).read_text())
    con = duckdb.connect(str(db_path), read_only=True)
    rates = build_rates_payload(con, i18n, generated_at)
    mortgage = build_long_payload(con, "mart_mortgage_monthly", i18n, generated_at, attribution_key="scb_riksbank")
    cpif = build_long_payload(con, "mart_cpif_monthly", i18n, generated_at, attribution_key="scb")
    catalogue = build_catalogue(con, generated_at)
    con.close()

    v1 = out / "v1"
    v1.mkdir(parents=True, exist_ok=True)
    written = []
    (v1 / "rates_monthly.json").write_text(json.dumps(rates, ensure_ascii=False, indent=1))
    write_csv(rates, v1 / "rates_monthly.csv")
    for name, payload in (("mortgage_rates_monthly", mortgage), ("cpif_monthly", cpif)):
        (v1 / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        write_csv(payload, v1 / f"{name}.csv")
        written += [v1 / f"{name}.json", v1 / f"{name}.csv"]
    (v1 / "catalogue.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=1))
    written += [v1 / "rates_monthly.json", v1 / "rates_monthly.csv", v1 / "catalogue.json"]

    # Monthly "as published" archive: created once per calendar month, never overwritten.
    month_dir = archive_dir / now.strftime("%Y-%m")
    if not month_dir.exists():
        shutil.copytree(v1, month_dir)
    if archive_dir.exists():
        shutil.copytree(archive_dir, out / "archive", dirs_exist_ok=True)
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site_out")
    args = ap.parse_args()
    for p in export(Path(args.out)):
        print("wrote", p)

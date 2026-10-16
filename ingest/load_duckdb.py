"""Load the latest raw snapshot of every series into DuckDB schema `raw` (input to dbt)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import yaml

from . import riksbank_api, scb_api
from .common import DEFAULT_RAW_DIR, latest_snapshot

DB_PATH = Path(os.environ.get("SMP_DB", "data/smp.duckdb"))


def load(config_path: str = "config/series.yml", db_path: Path = DB_PATH, raw_dir: Path | None = None) -> dict:
    cfg = yaml.safe_load(Path(config_path).read_text())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("create schema if not exists raw")
    counts = {}

    rb = []
    for s in cfg["riksbank"]["series"]:
        snap = latest_snapshot("riksbank", s["id"], raw_dir=raw_dir)
        if snap:
            for r in riksbank_api.parse_observations(s["id"], json.loads(snap.read_text())):
                rb.append({**r, "series_key": s["key"], "unit": s.get("unit"), "snapshot_file": snap.name})
    _replace(con, "riksbank_observations", rb,
             "series_id varchar, series_key varchar, unit varchar, obs_date varchar, value double, snapshot_file varchar")
    counts["riksbank_observations"] = len(rb)

    scb = []
    for t in cfg["scb"].get("tables", []):
        snap = latest_snapshot("scb", t["key"], raw_dir=raw_dir)
        if snap:
            for r in scb_api.parse_jsonstat2(t["table_id"], json.loads(snap.read_text())):
                scb.append({"series_key": t["key"], "table_id": r.pop("table_id"), "value": r.pop("value"),
                            "dims": json.dumps(r, sort_keys=True), "snapshot_file": snap.name})
    _replace(con, "scb_observations", scb,
             "series_key varchar, table_id varchar, dims varchar, value double, snapshot_file varchar")
    counts["scb_observations"] = len(scb)

    ki = []
    for t in cfg["ki"].get("stats_tables", []):
        snap = latest_snapshot("ki", t["key"], raw_dir=raw_dir)
        if snap:
            ki += _ki_rows(t["key"], "stats", None, snap)
    raw_root = Path(raw_dir or DEFAULT_RAW_DIR) / "ki_forecast"
    for t in cfg["ki"].get("forecast_tables", []):
        for folder in sorted(raw_root.glob(f"{t['key']}__*")):
            snap = latest_snapshot("ki_forecast", folder.name, raw_dir=raw_dir)
            if snap:
                vintage = folder.name.split("__", 1)[1]  # 'latest' or YYYYMMDD
                ki += _ki_rows(t["key"], "forecast_latest" if vintage == "latest" else "forecast_vintage", vintage, snap)
    _replace(con, "ki_observations", ki,
             "series_key varchar, kind varchar, vintage varchar, dims varchar, value double, snapshot_file varchar")
    counts["ki_observations"] = len(ki)
    con.close()
    return counts


def _ki_rows(series_key: str, kind: str, vintage: str | None, snap: Path) -> list[dict]:
    out = []
    for r in scb_api.parse_jsonstat2(series_key, json.loads(snap.read_text())):
        value = r.pop("value")
        r.pop("table_id")
        out.append({"series_key": series_key, "kind": kind, "vintage": vintage,
                    "dims": json.dumps(r, sort_keys=True), "value": value, "snapshot_file": snap.name})
    return out


def _replace(con, table: str, rows: list[dict], ddl: str) -> None:
    con.execute(f"drop table if exists raw.{table}")
    con.execute(f"create table raw.{table} ({ddl})")
    if rows:
        cols = [c.split()[0] for c in ddl.split(", ")]
        con.executemany(f"insert into raw.{table} values ({', '.join('?' * len(cols))})",
                        [[r.get(c) for c in cols] for r in rows])


if __name__ == "__main__":
    print(load())

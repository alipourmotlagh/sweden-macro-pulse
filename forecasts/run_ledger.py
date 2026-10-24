"""Write this run's forecasts to the append-only ledger (silent logging, month 1).

Sources that go in, with the same columns:
  * model "naive": random-walk baseline made from our own monthly averages (one forecast set per calendar month)
  * model "ki":    every Konjunkturinstitutet release (vintage), forecast months only
  * models "riksbank" / "market_forward": every Riksbank policy round (raw snapshots), forecast periods only

Run after `dbt build` (reads the mart tables from DuckDB):  python -m forecasts.run_ledger
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import duckdb

from . import riksbank_ledger
from .ki_ledger import load_from_duckdb
from .ledger import append_rows, naive_forecast

DB_PATH = Path(os.environ.get("SMP_DB", "data/smp.duckdb"))
LEDGER_PATH = Path("forecasts/ledger.csv")
HORIZONS = 12
# Our series key -> column in mart_rates_monthly, and the KI variable that forecasts the same thing.
SERIES = {
    "policy_rate": "F0604Repo",       # KI: policy rate, monthly average
    "tbill_3m": "F0604Ssvx3m",        # KI: 3-month Treasury bill, Sweden
    "gov_bond_10y": "F0604Sek10y",    # KI: 10-year government bond, Sweden
}


def _add_months(d: dt.date, n: int) -> dt.date:
    m = d.year * 12 + (d.month - 1) + n
    return dt.date(m // 12, m % 12 + 1, 1)


def naive_rows(con, series: str, today: dt.date) -> list[dict]:
    """Baseline made on `today`'s month: last complete month's value carried forward 1..12 months.

    made_at is the first day of the run month, so the weekly run produces the same rows (skipped as duplicates).
    The baseline uses data up to the previous month, so it is a slightly longer-lead forecast than its horizon says.
    """
    month_start = today.replace(day=1)
    rows = con.execute(
        f"select month, {series} from main.mart_rates_monthly where month < ? and {series} is not null order by month",
        [month_start]).fetchall()
    history = [float(v) for _, v in rows]
    targets = [_add_months(month_start, h).strftime("%Y-%m") for h in range(1, HORIZONS + 1)]
    return naive_forecast(history, HORIZONS, series=series, made_at=month_start.isoformat(),
                          target_periods=targets, data_vintage=rows[-1][0].isoformat())


def cpif_naive_rows(con, today: dt.date) -> list[dict]:
    """CPIF baseline made on `today`'s month: the value for two months earlier carried forward 1..12 months.

    CPIF for month M is published around the 10th of M+1, so on the 1st of a month the last PUBLISHED value is M-2.
    We always use M-2 even if a weekly run later in the month could see M-1: otherwise a re-run would produce different
    numbers under the same key and the append-only ledger would (rightly) refuse them.
    """
    month_start = today.replace(day=1)
    cutoff = _add_months(month_start, -2)
    rows = con.execute("select month, value from main.mart_cpif_monthly where month <= ? order by month", [cutoff]).fetchall()
    if not rows or rows[-1][0] != cutoff:
        return []                                   # last expected value not there yet: log nothing rather than guess
    targets = [_add_months(month_start, h).strftime("%Y-%m") for h in range(1, HORIZONS + 1)]
    return naive_forecast([float(v) for _, v in rows], HORIZONS, series="cpif_annual", made_at=month_start.isoformat(),
                          target_periods=targets, data_vintage=cutoff.isoformat(), lead=1)


def run(db_path: Path = DB_PATH, ledger_path: Path = LEDGER_PATH, today: dt.date | None = None,
        raw_dir: Path | None = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    con = duckdb.connect(str(db_path), read_only=True)
    added = {"naive": 0, "ki": 0, "riksbank": 0}
    for series, ki_variable in SERIES.items():
        added["naive"] += append_rows(ledger_path, naive_rows(con, series, today))
        added["ki"] += append_rows(ledger_path, load_from_duckdb(con, ki_variable, series))
    added["naive"] += append_rows(ledger_path, cpif_naive_rows(con, today))
    con.close()
    added["riksbank"] = append_rows(ledger_path, riksbank_ledger.load_rows(raw_dir))
    return added


if __name__ == "__main__":
    print("ledger rows added:", run())

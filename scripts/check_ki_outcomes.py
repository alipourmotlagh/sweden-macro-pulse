"""One-off check of the KI forecast vintages in data/raw (no network needed). Run from the repo root:

    python scripts/check_ki_outcomes.py

Part 1: do the variable codes we rely on exist in every release? (older releases may use other codes/layouts)
Part 2: for the 10-year yield (moves daily, so it is a clean test), compare KI's monthly values with the Riksbank's
        own monthly averages around each release month. Offset 0 = the release month, -1 = the month before.
        A difference near 0 means KI shows an outcome for that month; a larger difference means a forecast
        (or a month-to-date average).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest import riksbank_api, scb_api  # noqa: E402
from ingest.common import latest_snapshot  # noqa: E402

WANTED = {"F0604Repo": "policy_rate", "F0604Ssvx3m": "tbill_3m", "F0604Sek10y": "gov_bond_10y"}
TEST_VARIABLE, TEST_RIKSBANK = "F0604Sek10y", "SEGVB10YC"
OFFSETS = (-3, -2, -1, 0, 1)


def monthly_actuals(raw_dir: Path, series_id: str) -> dict[str, float]:
    snap = latest_snapshot("riksbank", series_id, raw_dir=raw_dir)
    rows = riksbank_api.parse_observations(series_id, json.loads(snap.read_text()))
    by_month = collections.defaultdict(list)
    for r in rows:
        if r["value"] is not None:
            by_month[str(r["obs_date"])[:7]].append(float(r["value"]))
    return {m: sum(v) / len(v) for m, v in by_month.items()}


def load_vintage(snap: Path):
    payload = json.loads(snap.read_text())
    rows = scb_api.parse_jsonstat2("ki", payload)
    dims = payload.get("id", [])
    values: dict[str, dict[str, float]] = collections.defaultdict(dict)
    for r in rows:
        var, per = r.get("variabel"), r.get("period_label") or r.get("period", "")  # old releases: numeric code + label
        if var is not None and r["value"] is not None and "M" in per:
            values[var][f"{per[:4]}-{per[5:7]}"] = r["value"]
    return dims, values


def shift(month: str, n: int) -> str:
    y, m = int(month[:4]), int(month[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12}-{t % 12 + 1:02d}"


def main(raw_dir: Path = Path("data/raw")) -> None:
    actual = monthly_actuals(raw_dir, TEST_RIKSBANK)
    folders = sorted((raw_dir / "ki_forecast").glob("ki_rates_monthly__2*"))
    print("PART 1 - which variables exist per release (counts of monthly values; '-' = variable missing)")
    print(f"{'release':<11}{'dimensions':<28}" + "".join(f"{v:<14}" for v in WANTED))
    for folder in folders:
        release = folder.name.split("__")[1]
        dims, values = load_vintage(latest_snapshot("ki_forecast", folder.name, raw_dir=raw_dir))
        print(f"{release:<11}{'/'.join(dims):<28}" + "".join(f"{len(values[v]) if v in values else '-':<14}" for v in WANTED))
    print(f"\nPART 2 - {TEST_VARIABLE} (KI) minus Riksbank monthly average, by month offset from the release month")
    print(f"{'release':<11}" + "".join(f"{('offset ' + format(o, '+d')):<14}" for o in OFFSETS))
    for folder in folders:
        release = dt.datetime.strptime(folder.name.split("__")[1], "%Y%m%d").date()
        _, values = load_vintage(latest_snapshot("ki_forecast", folder.name, raw_dir=raw_dir))
        rm, cells = release.strftime("%Y-%m"), []
        for o in OFFSETS:
            m = shift(rm, o)
            ki = values.get(TEST_VARIABLE, {}).get(m)
            cells.append(f"{ki - actual[m]:+.2f}" if ki is not None and m in actual else "n/a")
        print(f"{release!s:<11}" + "".join(f"{c:<14}" for c in cells))
    print("\nHow to read PART 2: values around +0.00 = KI equals the actual (an outcome). The first offset where the "
          "difference becomes clearly non-zero is where KI's forecast starts. 'n/a' = we have no actual yet or KI has no value.")


if __name__ == "__main__":
    main()

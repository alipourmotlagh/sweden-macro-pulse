"""Turn the Riksbank's own forecasts (Monetary Policy Data API) into ledger rows.

Reads the raw round snapshots written by `ingest/riksbank_mpd.py` (data/raw/riksbank_mpd/forecasts__<round>/).

What a round snapshot holds (checked against rounds 2026:3 and 2022:1 on 2026-10-22):
  * per series: the whole history *as known at that round* followed by the forecast, in one list of observations;
  * `forecast_cutoff_date` = last month/quarter of actual data. Observations up to it match SCB's outcomes (to rounding),
    observations after it are the forecast. Only the latter go in the ledger.
  * `policy_round_end_dtm` = publication date of the round -> `made_at`.

Conventions (documented in forecasts/conventions.yml and docs/forecast_conventions.md; shown to users):
  * horizon = whole months from the publication month to the target period, exactly as for KI. It can be 0 (nowcast)
    or NEGATIVE (a month already over but not yet published when the round came out). Headline scoring uses horizon >= 1.
  * the cutoff date goes in `data_vintage`, so scoring by information date can be done later.
  * policy rate series are QUARTERLY MEANS: target_period is the quarter-end month (e.g. 2026-12).
  * the forward-implied policy rate is market pricing published by the Riksbank, not a Riksbank forecast: model
    'market_forward'.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from ingest.common import DEFAULT_RAW_DIR, latest_snapshot

SOURCE = "riksbank_mpd"
# Riksbank series id -> (ledger series, ledger model)
SERIES_MAP = {
    "SEMCPIFNAYNA": ("cpif_annual", "riksbank"),
    "SEMCPINAYNA": ("cpi_annual", "riksbank"),
    "SEQRATENAYNA": ("policy_rate_qmean", "riksbank"),
    "SEDMENAYNA": ("policy_rate_forward_qmean", "market_forward"),
}


def _months_between(made_at: dt.date, target: dt.date) -> int:
    return (target.year - made_at.year) * 12 + (target.month - made_at.month)


def round_rows(snapshot: dict) -> list[dict]:
    """Ledger rows for one landed round snapshot ({"policy_round_name", "responses": {series_id: response}})."""
    out = []
    for sid, resp in snapshot["responses"].items():
        if sid not in SERIES_MAP:
            continue
        series, model = SERIES_MAP[sid]
        for item in resp["data"]:
            vint = item["vintages"]
            vint = vint[0] if isinstance(vint, list) else vint        # the API returns an object when a round is given
            meta = vint["metadata"]
            cutoff = dt.date.fromisoformat(meta["forecast_cutoff_date"])
            made_at = dt.date.fromisoformat(meta["policy_round_end_dtm"])
            for obs in vint["observations"]:
                tgt = dt.date.fromisoformat(obs["dt"])
                if tgt <= cutoff or obs["value"] is None:
                    continue                                           # history/outcomes are not forecasts
                out.append({"series": series, "model": model, "model_version": meta["policy_round"],
                            "made_at": made_at.isoformat(), "target_period": tgt.strftime("%Y-%m"),
                            "horizon": _months_between(made_at, tgt), "point": round(float(obs["value"]), 4),
                            "p10": "", "p90": "", "data_vintage": cutoff.isoformat()})
    return out


def load_rows(raw_dir: Path | None = None) -> list[dict]:
    """Rows from the latest snapshot of every landed round."""
    root = Path(raw_dir or DEFAULT_RAW_DIR) / SOURCE
    rows = []
    for folder in sorted(root.glob("forecasts__*")):
        snap = latest_snapshot(SOURCE, folder.name, raw_dir=raw_dir)
        if snap:
            rows += round_rows(json.loads(snap.read_text()))
    return rows

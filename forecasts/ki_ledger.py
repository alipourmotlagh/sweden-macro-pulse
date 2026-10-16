"""Turn KI forecast vintages into ledger rows (model = 'ki').

Assumption (to verify against real data): in a vintage released on date R, months strictly after R's month are
forecasts; earlier months are outcomes. Horizon = months ahead of the release month.
"""
from __future__ import annotations

import datetime as dt


def ki_vintage_rows(rows: list[tuple[str, str, str, float]], *, series: str) -> list[dict]:
    """rows: (vintage 'YYYYMMDD', variable, period 'YYYY-MM-DD', value). Returns ledger rows."""
    out = []
    for vintage, _variable, period, value in rows:
        rel = dt.datetime.strptime(vintage, "%Y%m%d").date()
        tgt = dt.date.fromisoformat(period)
        horizon = (tgt.year - rel.year) * 12 + (tgt.month - rel.month)
        if horizon < 1:
            continue
        out.append({"series": series, "model": "ki", "model_version": "konjunkturlaget", "made_at": rel.isoformat(),
                    "target_period": tgt.strftime("%Y-%m"), "horizon": horizon, "point": round(float(value), 4),
                    "p10": "", "p90": "", "data_vintage": vintage})
    return out


def load_from_duckdb(con, variable: str, series: str) -> list[dict]:
    rows = con.execute(
        "select vintage, variable, period, value from main.mart_ki_rates_vintages where variable = ? order by 1, 3",
        [variable]).fetchall()
    return ki_vintage_rows([(v, var, p.isoformat(), val) for v, var, p, val in rows], series=series)

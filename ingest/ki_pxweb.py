"""Konjunkturinstitutet (KI) PxWeb v1 adapter: barometer statistics and forecast vintages.

Verified by reading KI's pages and live directory/metadata listings (2026-10-15):
  stats:      https://statistik.konj.se/PxWeb/api/v1/sv/KonjBar/<folder>/<TABLE>.px
  forecasts:  https://prognos.konj.se/PxWeb/api/v1/sv/SenastePrognosen/<folder>/<TABLE>.px
  vintages:   https://prognos.konj.se/PxWeb/api/v1/sv/TidigarePrognoser/<YYYYMMDD>/<folder>/<TABLE>.px
NOT yet verified: the POST data request/response (first Actions run). Terms: KI allows free reuse, including
commercial, manual or via API (konj.se/statistik-och-data/sa-fungerar-databaserna.html). Download cap: 250,000 cells.

To avoid hard-coding variable codes, we GET the table metadata and request every value of every variable.
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

from .common import http_get, http_post, land_snapshot

STATS_BASE = "https://statistik.konj.se/PxWeb/api/v1/sv/KonjBar"
FORECAST_BASE = "https://prognos.konj.se/PxWeb/api/v1/sv"
RELEASE_RE = re.compile(r"^\d{8}$")


def build_all_query(metadata: dict, fmt: str = "json-stat2") -> dict:
    """POST body selecting every value of every variable in a table."""
    return {
        "query": [{"code": v["code"], "selection": {"filter": "all", "values": ["*"]}}
                  for v in metadata["variables"]],
        "response": {"format": fmt},
    }


def fetch_table(table_url: str, session: requests.Session | None = None, fmt: str = "json-stat2") -> dict:
    meta = http_get(table_url, session=session).json()
    return http_post(table_url, json_body=build_all_query(meta, fmt), session=session).json()


def list_releases(forecast_base: str, session: requests.Session | None = None) -> list[str]:
    """Release dates (YYYYMMDD) available under TidigarePrognoser, oldest first."""
    items = http_get(f"{forecast_base}/TidigarePrognoser", session=session).json()
    return sorted(i["id"] for i in items if RELEASE_RE.match(i["id"]))


def ingest(cfg: dict, raw_dir: Path | None = None, session: requests.Session | None = None,
           log=print) -> list[tuple[Path, bool]]:
    session = session or requests.Session()
    stats_base = cfg.get("stats_base", STATS_BASE)
    forecast_base = cfg.get("forecast_base", FORECAST_BASE)
    root = Path(raw_dir) if raw_dir else None
    landed = []

    for t in cfg.get("stats_tables", []):
        payload = fetch_table(f"{stats_base}/{t['path']}", session)
        landed.append(land_snapshot("ki", t["key"], payload, raw_dir=raw_dir))

    tables = cfg.get("forecast_tables", [])
    if not tables:
        return landed
    releases = list_releases(forecast_base, session)
    for t in tables:
        payload = fetch_table(f"{forecast_base}/SenastePrognosen/{t['path']}", session)
        landed.append(land_snapshot("ki_forecast", f"{t['key']}__latest", payload, raw_dir=raw_dir))
        for rel in releases:
            name = f"{t['key']}__{rel}"
            if _already_landed(name, root):
                continue  # vintages are immutable: fetch once
            try:
                payload = fetch_table(f"{forecast_base}/TidigarePrognoser/{rel}/{t['path']}", session)
            except requests.HTTPError as exc:  # older releases may use a different table layout
                log(f"ki vintage {rel} {t['key']}: skipped ({exc})")
                continue
            landed.append(land_snapshot("ki_forecast", name, payload, raw_dir=raw_dir))
    return landed


def _already_landed(name: str, raw_dir: Path | None) -> bool:
    from .common import DEFAULT_RAW_DIR
    folder = Path(raw_dir or DEFAULT_RAW_DIR) / "ki_forecast" / name
    return folder.exists() and any(folder.glob("*.json"))

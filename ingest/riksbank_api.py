"""Riksbank SWEA REST adapter (interest rates, bond yields).

Endpoint shape (from Riksbank documentation, NOT yet verified by a live run):
    GET {base}/Observations/{seriesId}/{from}/{to}   ->   [{"date": "2024-01-02", "value": 3.75}, ...]
Optional header Ocp-Apim-Subscription-Key. Attribution rule: credit Riksbank only on unchanged data.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import Path

import requests

from .common import http_get, land_snapshot


def fetch_observations(series_id: str, start: str, end: str | None, base_url: str,
                       api_key: str | None = None, session: requests.Session | None = None) -> list[dict]:
    end = end or dt.date.today().isoformat()
    url = f"{base_url}/Observations/{series_id}/{start}/{end}"
    headers = {"Ocp-Apim-Subscription-Key": api_key} if api_key else {}
    return http_get(url, headers=headers, session=session).json()


def parse_observations(series_id: str, payload: list[dict]) -> list[dict]:
    """Normalise to rows {series_id, obs_date, value}. Tolerates a null value (missing day)."""
    rows = []
    for item in payload:
        value = item.get("value")
        rows.append({
            "series_id": series_id,
            "obs_date": item["date"][:10],
            "value": None if value is None else float(value),
        })
    return rows


def ingest(cfg: dict, raw_dir: Path | None = None, sleep=time.sleep) -> list[tuple[Path, bool]]:
    api_key = os.environ.get("RIKSBANK_API_KEY") or None
    pause = 0 if api_key else cfg.get("min_seconds_between_calls", 13)
    session = requests.Session()
    landed = []
    for i, s in enumerate(cfg["series"]):
        if i and pause:
            sleep(pause)
        payload = fetch_observations(s["id"], cfg["start"], None, cfg["base_url"], api_key, session)
        landed.append(land_snapshot("riksbank", s["id"], payload, raw_dir=raw_dir))
    return landed

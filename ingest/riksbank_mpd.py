"""Riksbank Monetary Policy Data API v1 adapter (RAW LANDING ONLY, for now).

Endpoints:
  GET {base}/forecasts/series_ids                          -> {"data": [{"series_id", "metadata": {...}}]}   (verified live)
  GET {base}/forecasts/policy_rounds                       -> {"data": ["2024:1", ...]}                       (verified live)
  GET {base}/forecasts?policy_round_name=<round>&series=<ONE series id>   -> forecasts for that round and series
Auth: the same `Ocp-Apim-Subscription-Key` header as SWEA.

What the first two live runs taught us (2026-10-22):
  * `/forecasts?policy_round_name=<round>` and every multi-series form got an empty-bodied 404.
  * An open-source client for this API (aerugo/swemo-mcp) sends ONE series per request and keeps the colon in the round
    name literal (`2024:1`, not `2024%3A1`). Python `requests` percent-encodes ':' when given params, so we build the
    query string ourselves. The newest round is probed with the literal colon first, then the encoded form; the one
    that works is logged and used for all rounds.

Raw snapshot per round: {"policy_round_name": ..., "responses": {series_id: <raw response>}}.
A past round is immutable, so it is fetched once. The newest round is re-fetched every run (it can be revised).
Failures are printed as warnings and do NOT stop the other sources (this source is optional until wired into the
ledger); a warning nobody reads is not monitoring, so the first run output must be read.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from .common import DEFAULT_RAW_DIR, http_get, land_snapshot

SOURCE = "riksbank_mpd"


def round_slug(name: str) -> str:
    """'2024:1' -> '2024-1' (a safe folder name)."""
    return name.replace(":", "-").replace("/", "-")


def _get(base: str, path: str, headers: dict, session) -> object:
    return http_get(f"{base}{path}", headers=headers, session=session).json()


def forecast_url(base: str, round_name: str, series_id: str, literal_colon: bool) -> str:
    rnd = round_name if literal_colon else round_name.replace(":", "%3A")
    return f"{base}/forecasts?policy_round_name={rnd}&series={series_id}"


def _fetch_round(base, name, series, literal_colon, headers, session, pause, sleep):
    responses = {}
    for i, sid in enumerate(series):
        if i and pause:
            sleep(pause)
        responses[sid] = http_get(forecast_url(base, name, sid, literal_colon), headers=headers, session=session).json()
    return {"policy_round_name": name, "responses": responses}


def ingest(cfg: dict, raw_dir: Path | None = None, session: requests.Session | None = None,
           log=print, sleep=time.sleep) -> list[tuple[Path, bool]]:
    if not cfg:
        return []
    base = cfg["base_url"].rstrip("/")
    series_wanted = list(cfg.get("series", []))
    pause = cfg.get("pause_seconds", 0.4)          # ~150 requests/min, under the 200/min limit
    api_key = os.environ.get("RIKSBANK_API_KEY") or None
    headers = {"Ocp-Apim-Subscription-Key": api_key} if api_key else {}
    session = session or requests.Session()
    root = Path(raw_dir or DEFAULT_RAW_DIR)
    landed: list[tuple[Path, bool]] = []

    try:
        series = _get(base, "/forecasts/series_ids", headers, session)
        landed.append(land_snapshot(SOURCE, "series_ids", series, raw_dir=raw_dir))
        rounds_payload = _get(base, "/forecasts/policy_rounds", headers, session)
        landed.append(land_snapshot(SOURCE, "policy_rounds", rounds_payload, raw_dir=raw_dir))
        rounds = list(rounds_payload["data"]) if isinstance(rounds_payload, dict) else list(rounds_payload)
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        log(f"::warning::riksbank_mpd: could not list series/rounds ({exc}); source skipped")
        return landed

    gaps = set(cfg.get("known_gaps", []))      # rounds the Riksbank published without a single forecast (e.g. 2020:2)
    rounds = sorted(r for r in rounds if r not in gaps)   # labels like '2024:1' sort chronologically
    if not rounds or not series_wanted:
        return landed
    newest = rounds[-1]

    chosen, probe_payload = None, None
    for literal in (True, False):
        try:
            probe_payload = _fetch_round(base, newest, series_wanted, literal, headers, session, pause, sleep)
            chosen = literal
            break
        except requests.RequestException as exc:
            log(f"::warning::riksbank_mpd probe {newest} ({'literal' if literal else 'encoded'} colon) failed ({exc})")
    if chosen is None:
        log("::warning::riksbank_mpd: no request form worked; per-round forecasts skipped")
        return landed
    log(f"riksbank_mpd: {'literal' if chosen else 'encoded'} colon works")
    landed.append(land_snapshot(SOURCE, f"forecasts__{round_slug(newest)}", probe_payload, raw_dir=raw_dir))

    for name in rounds[:-1]:
        folder = root / SOURCE / f"forecasts__{round_slug(name)}"
        if folder.exists() and any(folder.glob("*.json")):
            continue                 # past rounds are immutable: fetch once
        try:
            payload = _fetch_round(base, name, series_wanted, chosen, headers, session, pause, sleep)
        except requests.RequestException as exc:
            log(f"::warning::riksbank_mpd round {name}: skipped ({exc})")
            continue
        landed.append(land_snapshot(SOURCE, f"forecasts__{round_slug(name)}", payload, raw_dir=raw_dir))
    return landed

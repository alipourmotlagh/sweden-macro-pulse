"""Riksbank Monetary Policy Data API v1 adapter (RAW LANDING ONLY, for now).

Endpoints (from the Riksbank's API documentation, read 2026-10-22; response shapes NOT yet seen live):
  GET {base}/forecasts/series_ids                      -> {"data": [{"series_id", "metadata": {...}}]}
  GET {base}/forecasts/policy_rounds                   -> {"data": ["2024:1", ...]}
  GET {base}/forecasts?policy_round_name=<round>       -> {"data": [{"external_id", "vintages": [...]}]}
Auth: the same `Ocp-Apim-Subscription-Key` header as SWEA.

Why raw-only: we do not yet know the series ids (e.g. which one is the repo-rate path, which is CPIF). The first
live run lands `series_ids` and `policy_rounds`; we read them, choose series, then add parsing and ledger mapping.

Policy: a past round is immutable, so it is fetched once. The newest round is re-fetched every run (it can be revised).
Failures are logged as GitHub warnings and do NOT stop the other sources: this source is unverified and optional
until it is wired into the ledger. (Lesson from STIBOR: a warning nobody sees is not monitoring; the log line is
printed with `::warning::` so it shows on the run summary.)
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

from .common import DEFAULT_RAW_DIR, http_get, land_snapshot

SOURCE = "riksbank_mpd"


def round_slug(name: str) -> str:
    """'2024:1' -> '2024-1' (a safe folder name)."""
    return name.replace(":", "-").replace("/", "-")


def _get(base: str, path: str, params: dict | None, headers: dict, session) -> object:
    return http_get(f"{base}{path}", params=params, headers=headers, session=session).json()


def ingest(cfg: dict, raw_dir: Path | None = None, session: requests.Session | None = None,
           log=print) -> list[tuple[Path, bool]]:
    if not cfg:
        return []
    base = cfg["base_url"].rstrip("/")
    api_key = os.environ.get("RIKSBANK_API_KEY") or None
    headers = {"Ocp-Apim-Subscription-Key": api_key} if api_key else {}
    session = session or requests.Session()
    root = Path(raw_dir or DEFAULT_RAW_DIR)
    landed: list[tuple[Path, bool]] = []

    try:
        series = _get(base, "/forecasts/series_ids", None, headers, session)
        landed.append(land_snapshot(SOURCE, "series_ids", series, raw_dir=raw_dir))
        rounds_payload = _get(base, "/forecasts/policy_rounds", None, headers, session)
        landed.append(land_snapshot(SOURCE, "policy_rounds", rounds_payload, raw_dir=raw_dir))
        rounds = list(rounds_payload["data"]) if isinstance(rounds_payload, dict) else list(rounds_payload)
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        log(f"::warning::riksbank_mpd: could not list series/rounds ({exc}); source skipped")
        return landed

    rounds = sorted(rounds)          # labels like '2024:1' sort chronologically
    newest = rounds[-1] if rounds else None
    for name in rounds:
        folder = root / SOURCE / f"forecasts__{round_slug(name)}"
        if name != newest and folder.exists() and any(folder.glob("*.json")):
            continue                 # past rounds are immutable: fetch once
        try:
            payload = _get(base, "/forecasts", {"policy_round_name": name}, headers, session)
        except requests.RequestException as exc:
            log(f"::warning::riksbank_mpd round {name}: skipped ({exc})")
            continue
        landed.append(land_snapshot(SOURCE, f"forecasts__{round_slug(name)}", payload, raw_dir=raw_dir))
    return landed

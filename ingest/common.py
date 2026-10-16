"""Shared helpers: immutable raw snapshots and HTTP with retries."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path

import requests

DEFAULT_RAW_DIR = Path(os.environ.get("SMP_RAW_DIR", "data/raw"))
USER_AGENT = "sweden-macro-pulse/0.1 (+https://github.com/; open data project)"


def land_snapshot(source: str, name: str, payload: bytes | str | object, ext: str = "json",
                  raw_dir: Path | None = None, today: dt.date | None = None) -> tuple[Path, bool]:
    """Store a raw payload as data/raw/<source>/<name>/<YYYY-MM-DD>_<sha8>.<ext>.

    Snapshots are immutable: an existing file is never overwritten. If a snapshot with identical
    content already exists, nothing is written and (existing_path, False) is returned.
    """
    raw_dir = Path(raw_dir or DEFAULT_RAW_DIR)
    if isinstance(payload, (dict, list)):
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    elif isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = bytes(payload)
    sha8 = hashlib.sha256(data).hexdigest()[:8]
    folder = raw_dir / source / name
    folder.mkdir(parents=True, exist_ok=True)
    for existing in folder.glob(f"*_{sha8}.{ext}"):
        return existing, False
    day = (today or dt.datetime.now(dt.timezone.utc).date()).isoformat()
    path = folder / f"{day}_{sha8}.{ext}"
    path.write_bytes(data)
    return path, True


def latest_snapshot(source: str, name: str, ext: str = "json", raw_dir: Path | None = None) -> Path | None:
    folder = Path(raw_dir or DEFAULT_RAW_DIR) / source / name
    files = sorted(folder.glob(f"*.{ext}"))  # filename starts with the ISO date
    return files[-1] if files else None


def http_get(url: str, *, params: dict | None = None, headers: dict | None = None,
             session: requests.Session | None = None, retries: int = 4, timeout: int = 60) -> requests.Response:
    """GET with retry on 429/5xx, honouring Retry-After. Raises on final failure."""
    return _request("get", url, params=params, headers=headers, session=session, retries=retries, timeout=timeout)


def http_post(url: str, *, json_body: dict, headers: dict | None = None,
              session: requests.Session | None = None, retries: int = 4, timeout: int = 120) -> requests.Response:
    """POST (JSON body) with the same retry policy as http_get."""
    return _request("post", url, json_body=json_body, headers=headers, session=session, retries=retries, timeout=timeout)


def _request(method: str, url: str, *, params: dict | None = None, json_body: dict | None = None,
             headers: dict | None = None, session: requests.Session | None = None,
             retries: int = 4, timeout: int = 60) -> requests.Response:
    s = session or requests.Session()
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    last: requests.Response | None = None
    for attempt in range(retries + 1):
        if method == "get":
            last = s.get(url, params=params, headers=hdrs, timeout=timeout)
        else:
            last = s.post(url, json=json_body, headers=hdrs, timeout=timeout)
        if last.status_code == 429 or last.status_code >= 500:
            wait = last.headers.get("Retry-After")
            time.sleep(float(wait) if wait and wait.isdigit() else 2 ** attempt * 2)
            continue
        _raise_with_body(last, url)
        return last
    assert last is not None
    _raise_with_body(last, url)
    return last


def _raise_with_body(resp: requests.Response, url: str) -> None:
    """Like raise_for_status, but keeps the server's error text (e.g. Riksbank ProblemDetails) in the message."""
    if resp.status_code >= 400:
        body = (getattr(resp, "text", "") or "")[:300]
        raise requests.HTTPError(f"{resp.status_code} for {url}: {body}", response=resp)

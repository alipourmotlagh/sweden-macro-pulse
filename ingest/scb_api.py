"""Statistics Sweden (SCB) PxWebApi 2 adapter, JSON-stat2 output.

Request shape (from documentation, NOT yet verified by a live run):
    GET {base}/tables/{id}/data?lang=en&outputFormat=json-stat2&valuecodes[Var]=a,b
Limits: 150,000 cells per call, 30 calls / 10 s per IP.
"""
from __future__ import annotations

import itertools
from pathlib import Path

import requests

from .common import http_get, land_snapshot


def build_params(selection: dict[str, list[str]], lang: str = "en") -> dict[str, str]:
    params = {"lang": lang, "outputFormat": "json-stat2"}
    for var, codes in selection.items():
        params[f"valuecodes[{var}]"] = ",".join(codes)
    return params


def fetch_table(table_id: str, selection: dict[str, list[str]], base_url: str,
                session: requests.Session | None = None) -> dict:
    return http_get(f"{base_url}/tables/{table_id}/data", params=build_params(selection), session=session).json()


def parse_jsonstat2(table_id: str, payload: dict) -> list[dict]:
    """Flatten a JSON-stat2 dataset into long rows: {table_id, <dim>: code ..., value}.

    Values are stored row-major over `id` order with sizes from `size`; `value` may be a list or a
    sparse dict keyed by flat index.
    """
    dim_ids: list[str] = payload["id"]
    sizes: list[int] = payload["size"]
    codes_per_dim = []
    for d in dim_ids:
        index = payload["dimension"][d]["category"]["index"]
        if isinstance(index, dict):
            codes = [c for c, _ in sorted(index.items(), key=lambda kv: kv[1])]
        else:
            codes = list(index)
        codes_per_dim.append(codes)
    values = payload["value"]
    get = (lambda i: values.get(str(i))) if isinstance(values, dict) else (lambda i: values[i])
    rows = []
    for flat, combo in enumerate(itertools.product(*[range(n) for n in sizes])):
        v = get(flat)
        row = {"table_id": table_id}
        for d, codes, pos in zip(dim_ids, codes_per_dim, combo):
            row[d] = codes[pos]
        row["value"] = None if v is None else float(v)
        rows.append(row)
    return rows


def ingest(cfg: dict, raw_dir: Path | None = None) -> list[tuple[Path, bool]]:
    session = requests.Session()
    landed = []
    for t in cfg.get("tables", []):
        payload = fetch_table(t["table_id"], t["selection"], cfg["base_url"], session)
        landed.append(land_snapshot("scb", t["key"], payload, raw_dir=raw_dir))
    return landed

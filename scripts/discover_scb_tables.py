"""Find candidate SCB tables for the series we need. Run from your machine or CI (not from restricted sandboxes).

    python scripts/discover_scb_tables.py            # runs the default term list
    python scripts/discover_scb_tables.py CPIF FASTPI

Uses SINGLE-word queries on purpose (multi-word queries behaved unpredictably in earlier probing).
Prints table id, label, and period range so you can copy chosen ids into config/series.yml.
Request/response shape follows PxWebApi 2 documentation and is not yet verified live: if the JSON keys
differ, adjust the `tables` extraction below.
"""
from __future__ import annotations

import sys

import requests

BASE = "https://statistikdatabasen.scb.se/api/v2"
DEFAULT_TERMS = ["CPIF", "KPI", "inflation", "bostadslån", "mortgage", "FASTPI", "fastighetsprisindex",
                 "utlåning", "hushåll", "arbetslöshet", "BNP"]


def search(term: str, lang: str = "en", page_size: int = 20) -> list[dict]:
    r = requests.get(f"{BASE}/tables", params={"query": term, "lang": lang, "pageSize": page_size}, timeout=60,
                     headers={"User-Agent": "sweden-macro-pulse discovery"})
    r.raise_for_status()
    return r.json().get("tables", [])


def main(terms: list[str]) -> None:
    for term in terms:
        print(f"\n=== {term} ===")
        try:
            tables = search(term)
        except requests.RequestException as exc:
            print(f"  request failed: {exc}")
            continue
        for t in tables:
            print(f"  {t.get('id'):<12} {t.get('firstPeriod', '?')}..{t.get('lastPeriod', '?')}  {t.get('label', '')[:90]}")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_TERMS)

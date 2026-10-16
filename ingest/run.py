"""Run all adapters: `python -m ingest.run`. Prints a summary and writes `new_data=true|false` to GITHUB_OUTPUT."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

from . import ki_pxweb, riksbank_api, scb_api


def main(config_path: str = "config/series.yml") -> int:
    cfg = yaml.safe_load(Path(config_path).read_text())
    results = {
        "riksbank": riksbank_api.ingest(cfg["riksbank"]),
        "scb": scb_api.ingest(cfg["scb"]),
        "ki": ki_pxweb.ingest(cfg["ki"]),
    }
    new_any = False
    for source, landed in results.items():
        new = sum(1 for _, is_new in landed if is_new)
        new_any |= new > 0
        print(f"{source}: {len(landed)} series fetched, {new} with new content")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"new_data={'true' if new_any else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

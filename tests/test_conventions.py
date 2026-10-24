"""Guard: every model and series that can be logged has user-facing documentation in en + sv."""
import json
from pathlib import Path

import yaml

from export.export import build_conventions_payload
from forecasts import riksbank_ledger, run_ledger, scoring
from forecasts.ledger import read_ledger

CONV = Path("forecasts/conventions.yml")


def conv():
    return yaml.safe_load(CONV.read_text())


def has_text(node):
    return bool(node["en"].strip()) and bool(node["sv"].strip())


def test_every_possible_model_and_series_is_documented():
    c = conv()
    models = {"naive", "ki", scoring.BACKTEST_MODEL} | {m for _, m in riksbank_ledger.SERIES_MAP.values()}
    series = set(run_ledger.SERIES) | {s for s, _ in riksbank_ledger.SERIES_MAP.values()} | {"cpif_annual"}
    assert models <= set(c["models"]), models - set(c["models"])
    assert series <= set(c["series"]), series - set(c["series"])


def test_real_ledger_has_no_undocumented_model_or_series():
    path = Path("forecasts/ledger.csv")
    if not path.exists():
        return
    rows = read_ledger(path)
    c = conv()
    assert {r["model"] for r in rows} <= set(c["models"])
    assert {r["series"] for r in rows} <= set(c["series"])


def test_all_user_facing_text_exists_in_both_languages():
    c = conv()
    for key in ("horizon", "scoring", "skill", "attribution"):
        assert has_text(c["global"][key]["note"]), key
    for kind in ("models", "series"):
        for name, entry in c[kind].items():
            assert has_text(entry["note"]) and has_text(entry["label"]), (kind, name)
    assert all(entry["frequency"] in ("monthly", "quarterly") for entry in c["series"].values())


def test_payload_is_publishable_json():
    i18n = yaml.safe_load(Path("config/i18n.yml").read_text())
    payload = build_conventions_payload(CONV, i18n, "2026-10-22T00:00:00Z")
    assert payload["meta"]["schema_version"] == "1.0" and "disclaimer" in payload["meta"]
    json.dumps(payload, ensure_ascii=False)

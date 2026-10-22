import json

from ingest import riksbank_mpd
from tests.conftest import FakeMpdSession

CFG = {"base_url": "https://x/monetary_policy_data/v1", "series": ["SEQRATENAYNA", "SEMCPIFNAYNA"], "pause_seconds": 0}


def names(landed):
    return sorted(p.parent.name for p, _ in landed)


def run(tmp, session, cfg=CFG, logs=None):
    return riksbank_mpd.ingest(cfg, raw_dir=tmp, session=session, log=(logs.append if logs is not None else (lambda m: None)),
                               sleep=lambda s: None)


def test_url_keeps_colon_literal_by_default():
    u = riksbank_mpd.forecast_url("https://b", "2024:1", "S1", literal_colon=True)
    assert u == "https://b/forecasts?policy_round_name=2024:1&series=S1"
    assert "%3A" in riksbank_mpd.forecast_url("https://b", "2024:1", "S1", literal_colon=False)


def test_lands_series_rounds_and_each_round_one_series_per_request(tmp_path, monkeypatch):
    monkeypatch.setenv("RIKSBANK_API_KEY", "k")
    s = FakeMpdSession()
    landed = run(tmp_path, s)
    assert names(landed) == ["forecasts__2023-4", "forecasts__2024-1", "forecasts__2024-2", "policy_rounds", "series_ids"]
    assert all(h.get("Ocp-Apim-Subscription-Key") == "k" for _, _, h in s.calls)   # key in header, never in URL
    assert not any("key" in u.lower() for u, _, _ in s.calls)
    snap = json.loads(next(p for p, _ in landed if p.parent.name == "forecasts__2024-1").read_text())
    assert snap["policy_round_name"] == "2024:1" and set(snap["responses"]) == {"SEQRATENAYNA", "SEMCPIFNAYNA"}
    assert len([c for c in s.calls if "policy_round_name=2024:1&" in c[0]]) == 2   # 2 series -> 2 requests


def test_probe_falls_back_to_encoded_colon(tmp_path):
    logs = []
    landed = run(tmp_path, FakeMpdSession(accept="encoded"), logs=logs)
    assert len(names(landed)) == 5 and any("encoded colon works" in m for m in logs)


def test_past_rounds_fetched_once_newest_refetched(tmp_path):
    s = FakeMpdSession()
    run(tmp_path, s)
    n = len(s.calls)
    run(tmp_path, s)
    refetched = [c for c in s.calls[n:] if "policy_round_name" in c[0]]
    assert len(refetched) == 2 and all("2024:2" in c[0] for c in refetched)   # newest round only, both series


def test_failure_is_a_visible_warning_not_a_crash(tmp_path):
    logs = []
    assert run(tmp_path, FakeMpdSession(auth_error=True), logs=logs) == []
    assert logs and logs[0].startswith("::warning::")
    logs.clear()
    landed = run(tmp_path / "b", FakeMpdSession(accept="none"), logs=logs)
    assert names(landed) == ["policy_rounds", "series_ids"] and any("no request form" in m for m in logs)
    assert not [m for m in logs if m.startswith("::warning::riksbank_mpd round")]
    logs.clear()
    landed = run(tmp_path / "c", FakeMpdSession(fail_rounds=["2024:1"]), logs=logs)
    assert "forecasts__2024-1" not in names(landed) and any("2024:1" in m for m in logs)


def test_empty_config_is_a_noop(tmp_path):
    assert riksbank_mpd.ingest({}, raw_dir=tmp_path) == []


def test_known_gap_round_is_not_requested_and_not_warned(tmp_path):
    s, logs = FakeMpdSession(), []
    run(tmp_path, s, cfg={**CFG, "known_gaps": ["2024:1"]}, logs=logs)
    assert not any("policy_round_name=2024:1&" in c[0] for c in s.calls) and not [m for m in logs if m.startswith("::warning::")]

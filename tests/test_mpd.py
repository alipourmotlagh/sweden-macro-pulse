from ingest import riksbank_mpd
from tests.conftest import FakeMpdSession

CFG = {"base_url": "https://x/monetary_policy_data/v1"}


def names(landed):
    return sorted(p.parent.name for p, _ in landed)


def test_lands_series_rounds_and_each_round(tmp_path, monkeypatch):
    monkeypatch.setenv("RIKSBANK_API_KEY", "k")
    s = FakeMpdSession()
    landed = riksbank_mpd.ingest(CFG, raw_dir=tmp_path, session=s, log=lambda m: None)
    assert names(landed) == ["forecasts__2023-4", "forecasts__2024-1", "forecasts__2024-2", "policy_rounds", "series_ids"]
    assert all(h.get("Ocp-Apim-Subscription-Key") == "k" for _, _, h in s.calls)   # key sent as header, never in URL


def test_past_rounds_fetched_once_newest_refetched(tmp_path):
    s = FakeMpdSession()
    riksbank_mpd.ingest(CFG, raw_dir=tmp_path, session=s, log=lambda m: None)
    n = len([c for c in s.calls if c[1]])
    riksbank_mpd.ingest(CFG, raw_dir=tmp_path, session=s, log=lambda m: None)
    assert len([c for c in s.calls if c[1]]) - n == 1       # only the newest round (2024:2)


def test_failure_is_a_visible_warning_not_a_crash(tmp_path):
    logs = []
    assert riksbank_mpd.ingest(CFG, raw_dir=tmp_path, session=FakeMpdSession(auth_error=True), log=logs.append) == []
    assert logs and logs[0].startswith("::warning::")
    logs.clear()
    landed = riksbank_mpd.ingest(CFG, raw_dir=tmp_path / "b", session=FakeMpdSession(fail_rounds=["2024:1"]), log=logs.append)
    assert "forecasts__2024-1" not in names(landed) and any("2024:1" in m for m in logs)


def test_empty_config_is_a_noop(tmp_path):
    assert riksbank_mpd.ingest({}, raw_dir=tmp_path) == []

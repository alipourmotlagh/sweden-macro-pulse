from ingest import riksbank_mpd
from tests.conftest import FakeMpdSession

CFG = {"base_url": "https://x/monetary_policy_data/v1", "series": ["SEQRATENAYNA", "SEMCPIFNAYNA"]}


def names(landed):
    return sorted(p.parent.name for p, _ in landed)


def test_lands_series_rounds_and_each_round(tmp_path, monkeypatch):
    monkeypatch.setenv("RIKSBANK_API_KEY", "k")
    s = FakeMpdSession()
    landed = riksbank_mpd.ingest(CFG, raw_dir=tmp_path, session=s, log=lambda m: None)
    assert names(landed) == ["forecasts__2023-4", "forecasts__2024-1", "forecasts__2024-2", "policy_rounds", "series_ids"]
    assert all(h.get("Ocp-Apim-Subscription-Key") == "k" for _, _, h in s.calls)   # key sent as header, never in URL


def test_probe_finds_the_accepted_series_format(tmp_path):
    for accept in ("comma", "repeated", "one"):
        logs = []
        landed = riksbank_mpd.ingest(CFG, raw_dir=tmp_path / accept, session=FakeMpdSession(accept=accept), log=logs.append)
        assert any(f"'{'one_per_series' if accept == 'one' else accept}' works" in m for m in logs), (accept, logs)
        assert len(names(landed)) == 5


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
    logs.clear()   # a format the API never accepts: one probe pass, then stop (no per-round warning flood)
    s = FakeMpdSession(accept="none")
    landed = riksbank_mpd.ingest(CFG, raw_dir=tmp_path / "b", session=s, log=logs.append)
    assert names(landed) == ["policy_rounds", "series_ids"] and any("no request variant" in m for m in logs)
    assert not [m for m in logs if m.startswith("::warning::riksbank_mpd round")]
    logs.clear()
    landed = riksbank_mpd.ingest(CFG, raw_dir=tmp_path / "c", session=FakeMpdSession(fail_rounds=["2024:1"]), log=logs.append)
    assert "forecasts__2024-1" not in names(landed) and any("2024:1" in m for m in logs)


def test_empty_config_is_a_noop(tmp_path):
    assert riksbank_mpd.ingest({}, raw_dir=tmp_path) == []

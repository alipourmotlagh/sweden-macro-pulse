import datetime as dt

from forecasts.ledger import append_rows, read_ledger
from forecasts.ki_ledger import ki_vintage_rows
from ingest import ki_pxweb
from tests.conftest import FakeKiSession

CFG = {"stats_tables": [{"key": "ki_barometer", "path": "indikatorer/Indikatorm.px"}],
       "forecast_tables": [{"key": "ki_rates_monthly", "path": "f06_rantorochvaxelkurser/F0604.px"}]}


def test_query_selects_everything():
    q = ki_pxweb.build_all_query(FakeKiSession.META)
    assert [x["code"] for x in q["query"]] == ["variabel", "enhet", "period"]
    assert all(x["selection"] == {"filter": "all", "values": ["*"]} for x in q["query"])
    assert q["response"]["format"] == "json-stat2"


def test_releases_filtered_and_sorted():
    assert ki_pxweb.list_releases("https://x", FakeKiSession()) == ["20150101", "20260325", "20260616"]


def test_ingest_lands_vintages_skips_missing_and_is_idempotent(tmp_path):
    s, logs = FakeKiSession(), []
    landed = ki_pxweb.ingest(CFG, raw_dir=tmp_path, session=s, log=logs.append)
    assert any("20150101" in m for m in logs)                       # 404 vintage skipped, not fatal
    names = sorted(p.parent.name for p, _ in landed)
    assert names == ["ki_barometer", "ki_rates_monthly__20260325", "ki_rates_monthly__20260616",
                     "ki_rates_monthly__latest"]
    n_posts = len(s.posts)
    ki_pxweb.ingest(CFG, raw_dir=tmp_path, session=s, log=logs.append)
    # second run: only stats + latest + the still-missing 2015 vintage are retried; landed vintages are not refetched
    assert len(s.posts) - n_posts == 2


def test_ki_vintage_to_ledger(tmp_path):
    rows = [("20260616", "F0604Sek10y", "2026-05-01", 2.0),   # outcome month: skipped
            ("20260616", "F0604Sek10y", "2026-07-01", 2.3),   # horizon 1
            ("20260616", "F0604Sek10y", "2027-06-01", 2.9)]   # horizon 12
    out = ki_vintage_rows(rows, series="gov_bond_10y")
    assert [(r["target_period"], r["horizon"]) for r in out] == [("2026-07", 1), ("2027-06", 12)]
    path = tmp_path / "ledger.csv"
    assert append_rows(path, out) == 2 and append_rows(path, out) == 0
    assert len(read_ledger(path)) == 2

import datetime as dt

from ingest import riksbank_api, scb_api
from ingest.common import land_snapshot, latest_snapshot


def test_snapshot_is_immutable_and_deduplicated(tmp_path):
    p1, new1 = land_snapshot("riksbank", "X", [{"a": 1}], raw_dir=tmp_path, today=dt.date(2026, 1, 1))
    p2, new2 = land_snapshot("riksbank", "X", [{"a": 1}], raw_dir=tmp_path, today=dt.date(2026, 2, 1))
    assert new1 and not new2 and p1 == p2
    p3, new3 = land_snapshot("riksbank", "X", [{"a": 2}], raw_dir=tmp_path, today=dt.date(2026, 2, 1))
    assert new3 and p3 != p1 and p1.exists()
    assert latest_snapshot("riksbank", "X", raw_dir=tmp_path) == p3


def test_riksbank_parse_handles_null_and_floats():
    rows = riksbank_api.parse_observations("S", [{"date": "2024-01-02", "value": 3.75},
                                                  {"date": "2024-01-03T00:00:00", "value": None}])
    assert rows == [{"series_id": "S", "obs_date": "2024-01-02", "value": 3.75},
                    {"series_id": "S", "obs_date": "2024-01-03", "value": None}]


def test_scb_params_and_jsonstat_flatten(jsonstat2_payload):
    params = scb_api.build_params({"Tid": ["*"], "ContentsCode": ["A", "B"]})
    assert params["valuecodes[ContentsCode]"] == "A,B" and params["outputFormat"] == "json-stat2"
    rows = scb_api.parse_jsonstat2("TAB", jsonstat2_payload)
    assert [r["Tid"] for r in rows] == ["2024M01", "2024M02", "2024M03"]
    assert [r["value"] for r in rows] == [1.5, None, 2.5]


def test_scb_sparse_value_dict():
    payload = {"id": ["Tid"], "size": [2],
               "dimension": {"Tid": {"category": {"index": ["a", "b"]}}}, "value": {"1": 7}}
    rows = scb_api.parse_jsonstat2("T", payload)
    assert [r["value"] for r in rows] == [None, 7.0]


def test_jsonstat2_keeps_label_when_codes_are_numbers():
    payload = {"id": ["period"], "size": [2],
               "dimension": {"period": {"category": {"index": ["0", "1"], "label": {"0": "1993M01", "1": "1993M02"}}}},
               "value": [1.0, 2.0]}
    rows = scb_api.parse_jsonstat2("T", payload)
    assert [(r["period"], r["period_label"]) for r in rows] == [("0", "1993M01"), ("1", "1993M02")]
    same = {"id": ["period"], "size": [1], "dimension": {"period": {"category": {"index": ["1993M01"], "label": {"1993M01": "1993M01"}}}},
            "value": [1.0]}
    assert "period_label" not in scb_api.parse_jsonstat2("T", same)[0]  # no label noise when code is already readable

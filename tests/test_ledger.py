import pytest

from forecasts.ledger import LedgerError, append_rows, naive_forecast, read_ledger, score


def _rows():
    hist = [float(i % 5) for i in range(40)]
    return naive_forecast(hist, 3, series="cpif", made_at="2026-10-15",
                          target_periods=["2026-11", "2026-12", "2027-01"], data_vintage="2026-10-15")


def test_append_only_and_idempotent(tmp_path):
    path = tmp_path / "ledger.csv"
    rows = _rows()
    assert append_rows(path, rows) == 3
    assert append_rows(path, rows) == 0          # exact duplicates are skipped
    assert len(read_ledger(path)) == 3
    changed = [{**rows[0], "point": 99.0}]
    with pytest.raises(LedgerError):
        append_rows(path, changed)               # same key, different content: refused


def test_naive_band_contains_point():
    for r in _rows():
        assert r["p10"] <= r["point"] <= r["p90"]


def test_score_reports_sample_size():
    ledger = [{**r, "horizon": str(r["horizon"])} for r in _rows()]
    s = score(ledger, {("cpif", "2026-11"): 1.0})
    assert s[0]["n"] == 1 and "coverage_80" in s[0]

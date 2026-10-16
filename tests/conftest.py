"""Synthetic fixtures. All numbers are made up for testing; the real response format is verified on the first live run."""
import datetime as dt
import io

import openpyxl
import pytest


def synthetic_riksbank(start="2022-01-03", days=900, base=0.0, step_every=120, step=0.25):
    d0 = dt.date.fromisoformat(start)
    out = []
    for i in range(days):
        d = d0 + dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        out.append({"date": d.isoformat(), "value": round(base + (i // step_every) * step, 4)})
    return out


@pytest.fixture
def riksbank_payloads():
    return {
        "SECBREPOEFF": synthetic_riksbank(base=0.0),
        "SEDP3MSTIBORDELAYC": synthetic_riksbank(base=0.1),
        "SEGVB10YC": synthetic_riksbank(base=1.0, step_every=90, step=0.1),
    }


@pytest.fixture
def jsonstat2_payload():
    return {
        "version": "2.0", "class": "dataset",
        "id": ["ContentsCode", "Tid"], "size": [1, 3],
        "dimension": {
            "ContentsCode": {"category": {"index": {"X1": 0}}},
            "Tid": {"category": {"index": {"2024M01": 0, "2024M02": 1, "2024M03": 2}}},
        },
        "value": [1.5, None, 2.5],
    }


def ki_rates_payload(base=2.0):
    """Synthetic json-stat2 shaped like KI table F0604 (variabel x enhet x period)."""
    periods = [f"2026M{m:02d}" for m in range(1, 13)]
    return {
        "version": "2.0", "class": "dataset", "id": ["variabel", "enhet", "period"], "size": [2, 1, 12],
        "dimension": {
            "variabel": {"category": {"index": {"F0604Sek10y": 0, "F0604Sek5y": 1}}},
            "enhet": {"category": {"index": {"PCT": 0}}},
            "period": {"category": {"index": {p: i for i, p in enumerate(periods)}}},
        },
        "value": [base + 0.1 * i for i in range(12)] + [base - 0.5 + 0.1 * i for i in range(12)],
    }


class FakeResp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.headers = data, status, {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")


class FakeKiSession:
    """Mimics the KI PxWeb endpoints. Release 20150101 simulates an old table that no longer exists."""
    META = {"title": "Räntor", "variables": [{"code": "variabel"}, {"code": "enhet"}, {"code": "period"}]}

    def __init__(self):
        self.posts = []

    def get(self, url, params=None, headers=None, timeout=None):
        if url.endswith("/TidigarePrognoser"):
            return FakeResp([{"id": "20260325", "type": "l"}, {"id": "20260616", "type": "l"},
                             {"id": "20150101", "type": "l"}, {"id": "notadate", "type": "l"}])
        if "20150101" in url:
            return FakeResp({}, 404)
        return FakeResp(self.META)

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append((url, json))
        return FakeResp(ki_rates_payload())

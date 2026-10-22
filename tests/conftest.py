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
        "SETB3MBENCH": synthetic_riksbank(base=0.1),
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


def _jsonstat(dim_codes: dict[str, list[str]], values: list[float]) -> dict:
    return {"version": "2.0", "class": "dataset", "id": list(dim_codes), "size": [len(c) for c in dim_codes.values()],
            "dimension": {d: {"category": {"index": {c: i for i, c in enumerate(codes)}}} for d, codes in dim_codes.items()},
            "value": values}


def scb_cpif_payload():
    """Synthetic SCB TAB6590 selection: CPIF annual change, 24 months."""
    months = [f"{y}M{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
    values = [None] + [round(1.0 + 0.1 * i, 1) for i in range(1, 24)]   # first month null, like real 1987M01
    return _jsonstat({"ContentsCode": ["000007ZM"], "Tid": months}, values)


def scb_mortgage_payload():
    """Synthetic SCB TAB5783 selection: 2 agreement types x 5 fixation groups x 24 months."""
    months = [f"{y}M{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
    dims = {"Referenssektor": ["1"], "Motpartssektor": ["2c"], "Avtal": ["0100", "0200"],
            "Rantebindningstid": ["1.1", "1.1.1", "1.1.2.1", "1.1.2.2", "1.1.2.3"],
            "ContentsCode": ["000004ZW"], "Tid": months}
    values = [round(3.0 + 0.01 * i, 4) for i in range(2 * 5 * 24)]   # 3.00 .. 5.39, inside the plausibility band
    return _jsonstat(dims, values)


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


def ki_rates_payload_numeric(base=2.0):
    """Same table in the layout of older KI releases: numeric period codes, 'YYYYMmm' only in the labels."""
    payload = ki_rates_payload(base)
    periods = [f"2026M{m:02d}" for m in range(1, 13)]
    payload["dimension"]["period"]["category"] = {
        "index": [str(i) for i in range(12)], "label": {str(i): p for i, p in enumerate(periods)}}
    return payload


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


class FakeMpdSession:
    """Mimics the Riksbank Monetary Policy Data endpoints. `accept` is the series-format the fake API accepts:
    'comma', 'repeated' or 'one' (a single series per request). Requests without `series` get an empty 404, like the real API did."""
    def __init__(self, fail_rounds=(), auth_error=False, accept="comma"):
        self.calls, self.fail_rounds, self.auth_error, self.accept = [], set(fail_rounds), auth_error, accept

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        if self.auth_error:
            return FakeResp({}, 401)
        if url.endswith("/forecasts/series_ids"):
            return FakeResp({"data": [{"series_id": "SEQRATENAYNA", "metadata": {"decimals": 2, "unit": "Per cent"}}]})
        if url.endswith("/forecasts/policy_rounds"):
            return FakeResp({"data": ["2024:2", "2024:1", "2023:4"]})
        rnd, ser = params.get("policy_round_name"), params.get("series")
        ok = ((self.accept == "comma" and isinstance(ser, str) and "," in ser)
              or (self.accept == "repeated" and isinstance(ser, list))
              or (self.accept == "one" and isinstance(ser, str) and "," not in ser))
        if not ok or rnd in self.fail_rounds:
            return FakeResp({}, 404)
        ids = ser if isinstance(ser, list) else ser.split(",")
        return FakeResp({"data": [{"external_id": i, "vintages": [
            {"metadata": {"policy_round": rnd}, "observations": [{"dt": "2025-03-31", "value": 1.5}]}]} for i in ids]})

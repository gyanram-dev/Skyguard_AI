"""Phase 15 probe tests: POST /api/v1/demo/probe contract and honesty."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from src.api import schemas as S

NORMAL_DELHI = {"station_id": "DEL-01", "temperature": 9.3,
                "pressure": 971.3, "humidity": 100.0}
UNUSUAL_DELHI = {"station_id": "DEL-01", "temperature": 55.0,
                 "pressure": 1008.0, "humidity": 72.0}

_BAD_TEXT = re.compile(r"\bnan\b|\bNone\b|\binf\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (startup loads frozen artifacts once)."""
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


def _probe(client, payload):
    return client.post("/api/v1/demo/probe", json=payload)


# 1+10. Valid normal-looking observation validates against the schema.
def test_1_10_normal_probe_schema(client):
    response = _probe(client, NORMAL_DELHI)
    assert response.status_code == 200
    payload = S.ProbeResponse.model_validate(response.json())
    assert payload.data_mode == "historical_replay"
    assert payload.probe.station_id == "DEL-01"
    assert payload.context.station_available is True
    assert payload.context.historical_anchor
    assert payload.result.availability in ("FULL_EVIDENCE", "PARTIAL_EVIDENCE")
    assert isinstance(payload.result.is_anomalous, bool)
    assert payload.result.method == "ens_median"


# 2. Valid unusual observation returns a well-formed generated response.
def test_2_unusual_probe_schema(client):
    response = _probe(client, UNUSUAL_DELHI)
    assert response.status_code == 200
    payload = S.ProbeResponse.model_validate(response.json())
    assert payload.result.anomaly_score is not None
    assert payload.result.threshold is not None
    assert payload.result.is_anomalous == (
        payload.result.anomaly_score >= payload.result.threshold)
    # Frozen deterministic pipeline must discriminate the two inputs.
    normal = S.ProbeResponse.model_validate(
        _probe(client, NORMAL_DELHI).json())
    assert (payload.result.anomaly_score or 0.0) > (
        normal.result.anomaly_score or 0.0)


# 3+4. Humidity bounds are input errors, not anomalies.
def test_3_4_humidity_bounds(client):
    for humidity in (-5.0, 101.0):
        response = _probe(client, {"station_id": "DEL-01", "temperature": 20.0,
                                   "pressure": 1000.0, "humidity": humidity})
        assert response.status_code == 422
        body = S.ErrorResponse.model_validate(response.json())
        assert body.code == "invalid_input"


# 5+6. NaN / Infinity are rejected as invalid input.
def test_5_6_non_finite_rejected(client):
    for literal in ("NaN", "Infinity", "-Infinity"):
        response = client.post(
            "/api/v1/demo/probe",
            content='{"station_id": "DEL-01", "temperature": %s, '
                    '"pressure": 1000.0, "humidity": 50.0}' % literal,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_input"


# 7. Unknown stations (and mapped stations without backend data) 404.
def test_7_unknown_station(client):
    for station_id in ("NOPE-99", "AMD-06", "NOT-A-STATION"):
        response = _probe(client, {"station_id": station_id, "temperature": 20.0,
                                   "pressure": 1000.0, "humidity": 50.0})
        assert response.status_code == 404
        body = S.ErrorResponse.model_validate(response.json())
        assert body.code == "unknown_station"


# 8. Missing station is a structured validation response (no silent default).
def test_8_station_required(client):
    response = _probe(client, {"temperature": 20.0, "pressure": 1000.0,
                               "humidity": 50.0})
    assert response.status_code == 422
    body = S.ErrorResponse.model_validate(response.json())
    assert body.code == "station_required"


# 9. Stations without detector coverage report insufficient context.
def test_9_insufficient_context_noaa(client):
    for station_id in ("JAI-02", "HYD-07"):
        response = _probe(client, {"station_id": station_id, "temperature": 20.0,
                                   "pressure": 1000.0, "humidity": 50.0})
        assert response.status_code == 422
        body = S.ErrorResponse.model_validate(response.json())
        assert body.code == "insufficient_context"


# 11. No nan/None/inf literals leak into user-facing explanation text.
def test_11_no_bad_text(client):
    for payload in (NORMAL_DELHI, UNUSUAL_DELHI):
        body = S.ProbeResponse.model_validate(_probe(client, payload).json())
        assert body.explanation.text
        assert not _BAD_TEXT.search(body.explanation.text)
        for feature in body.explanation.features:
            assert feature.value is None or abs(feature.value) != float("inf")
            assert feature.contribution is None or abs(
                feature.contribution) != float("inf")


# 12. Jena is benchmark-internal and cannot be probed operationally.
def test_12_jena_is_not_probeable(client):
    response = _probe(client, {"station_id": "JENA-01", "temperature": 15.0,
                               "pressure": 1013.0, "humidity": 60.0})
    assert response.status_code == 404
    assert S.ErrorResponse.model_validate(response.json()).code == "unknown_station"

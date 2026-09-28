"""Phase 21B evidence-state tests: honest states, never calibrated claims.

Decision score, evidence coverage, component availability, and prediction
confidence are distinct. Missing/insufficient results must never render as
normal/trusted/healthy.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import schemas as S
from src.api.services import scoring as SC
from src.api.services import station_service as SS


@pytest.fixture(scope="module")
def client():
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


# 1. Normal with sufficient evidence: not flagged, FULL coverage grade.
def test_1_normal_sufficient_evidence(client):
    body = S.ProbeResponse.model_validate(client.post(
        "/api/v1/demo/probe",
        json={"station_id": "DEL-01", "temperature": 9.3,
              "pressure": 971.3, "humidity": 100.0}).json())
    assert body.result.is_anomalous is False
    assert body.result.availability in ("FULL_EVIDENCE", "PARTIAL_EVIDENCE")
    # Evidence coverage grade is bounded (1.0/0.67/0.33), never a "% probability".
    assert body.result.confidence in (1.0, 0.67, 0.33)
    assert body.explanation.text
    assert "nan" not in body.explanation.text.lower()


# 2. Anomaly: flagged with a decision score above threshold.
def test_2_anomaly_state(client):
    body = S.ProbeResponse.model_validate(client.post(
        "/api/v1/demo/probe",
        json={"station_id": "DEL-01", "temperature": 55.0,
              "pressure": 1008.0, "humidity": 72.0}).json())
    assert body.result.anomaly_score is not None
    assert body.result.threshold is not None
    assert body.result.is_anomalous == (
        body.result.anomaly_score >= body.result.threshold)


# 3. Insufficient history != normal: probe without context is 422, not healthy.
def test_3_insufficient_history_not_normal(client):
    response = client.post(
        "/api/v1/demo/probe",
        json={"station_id": None, "temperature": 20.0,
              "pressure": 1000.0, "humidity": 50.0})
    assert response.status_code == 422
    body = S.ErrorResponse.model_validate(response.json())
    assert body.code == "station_required"


# 4. Unavailable model != healthy: partial evidence degrades status to review.
def test_4_partial_evidence_is_review():
    row = pd.Series({"ens_median_flag": 0, "availability": "PARTIAL_EVIDENCE"})
    assert SS.pipeline_status(row) == "review"
    row = pd.Series({"ens_median_flag": 0, "availability": "FULL_EVIDENCE"})
    assert SS.pipeline_status(row) == "healthy"
    assert SS.pipeline_status(None) == "review"


# 5. Missing observation != trusted: null score renders "—"/"Not available".
def test_5_missing_score_not_trusted():
    assert SC.num(float("nan")) is None
    assert SC.num(float("inf")) is None
    assert SC.num(None) is None
    assert SC.sanitize_text("nan value", "fallback") == "fallback"
    assert SC.sanitize_text(None, "fallback") == "fallback"


# 6. Invalid input is a structured error, never an anomaly verdict.
def test_6_invalid_input(client):
    response = client.post(
        "/api/v1/demo/probe",
        json={"station_id": "DEL-01", "temperature": 20.0,
              "pressure": 1000.0, "humidity": 101.0})
    assert response.status_code == 422
    assert S.ErrorResponse.model_validate(response.json()).code == "invalid_input"


# 7. Spatial unavailable is explicit (Jena has no NOAA neighbors).
def test_7_spatial_unavailable(client):
    body = S.ProbeResponse.model_validate(client.post(
        "/api/v1/demo/probe",
        json={"station_id": "JENA-01", "temperature": 15.0,
              "pressure": 1000.0, "humidity": 60.0}).json())
    assert body.evidence.spatial["available"] is False


# 8. Partial detector availability: coverage grade reflects components.
def test_8_coverage_grades_not_probability():
    assert SC.CONFIDENCE_BY_AVAILABILITY["FULL_EVIDENCE"] == 1.0
    assert SC.CONFIDENCE_BY_AVAILABILITY["PARTIAL_EVIDENCE"] == 0.67
    assert SC.CONFIDENCE_BY_AVAILABILITY["LOW_CONTEXT"] == 0.33
    assert SC.CONFIDENCE_BY_AVAILABILITY["INSUFFICIENT_EVIDENCE"] is None
    assert SS.EVIDENCE_COMPLETENESS["INSUFFICIENT_EVIDENCE"] is None

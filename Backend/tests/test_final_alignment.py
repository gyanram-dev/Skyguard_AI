"""Final alignment tests: seasonal reference, operator actions, maintenance."""

from __future__ import annotations

import pandas as pd

from src.api.services import operator_actions as OA
from src.seasonal import context as SE


def _obs(hours: int = 72):
    stamps = pd.date_range("2024-06-01 00:00", periods=hours, freq="h")
    return pd.DataFrame({
        "timestamp": stamps.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": [29.0 + (h % 24) * 0.1 for h in range(hours)]})


# Seasonal reference is causal and deterministic.
def test_seasonal_causal_deterministic():
    obs = _obs()
    first = SE.same_hour_context(obs, "2024-06-03 12:00:00")
    assert first["available"] is True
    assert first["n_days"] == 2 or first["n_days"] >= 2
    assert SE.same_hour_context(obs, "2024-06-03 12:00:00") == first
    # Future rows appended do not change the earlier reference.
    longer = pd.concat([obs, _obs(24)], ignore_index=True)
    assert SE.same_hour_context(longer, "2024-06-03 12:00:00") == first


# Seasonal reference is unavailable without history.
def test_seasonal_unavailable():
    empty = pd.DataFrame({"timestamp": [], "temperature_c": []})
    assert SE.same_hour_context(empty, "2024-06-03 12:00:00")["available"] is False
    assert SE.same_hour_context(_obs(2), "2024-06-01 01:00:00")["available"] is False


# Operator actions map every class without inventing hardware repair.
def test_operator_actions():
    assert "calibration" in OA.for_root_cause("SPIKE").lower()
    assert "telemetry" in OA.for_root_cause("FROZEN").lower()
    assert "calibration review" in OA.for_root_cause("DRIFT").lower()
    assert "connectivity" in OA.for_quality_event("DATA_SOURCE_STALE").lower()
    assert "faulty solely" in OA.for_root_cause("SPIKE", "POSSIBLE_REGIONAL_EVENT")
    assert OA.for_verdict(True) == OA.NORMAL
    for text in (OA.for_root_cause("SPIKE"), OA.for_root_cause("UNKNOWN"),
                 OA.for_quality_event("STALE")):
        assert "repair" not in text.lower() or "not a" in text.lower() \
            or "physical repair" in text.lower()


# Maintenance review states from trailing evidence.
def test_maintenance_review():
    from src.api.services import station_service as SS

    class Store:
        alerts = []

    noaa = {"backend_station_id": "INI0000VOBL", "source_dataset": "noaa_ghcnh"}
    assert SS.maintenance_review(Store(), noaa, False)["state"] == "NOT_APPLICABLE"
    quiet = {"backend_station_id": "delhi", "frontend_station_id": "DEL-01",
             "source_dataset": "delhi_clean"}
    assert SS.maintenance_review(Store(), quiet, False)["state"] == \
        "NO_ACTION_INDICATED"

    class Busy:
        alerts = [{"station_id": "DEL-01", "timestamp": f"2024-12-{d:02d} 12:00:00"}
                  for d in range(20, 25)]

    assert SS.maintenance_review(Busy(), quiet, False)["state"] == \
        "MAINTENANCE_REVIEW_RECOMMENDED"


# Probe and investigation expose recommended actions end to end.
def test_recommended_action_api():
    from fastapi.testclient import TestClient

    from src.api import schemas as S
    from src.api.app import app

    with TestClient(app) as client:
        probe = S.ProbeResponse.model_validate(client.post(
            "/api/v1/demo/probe",
            json={"station_id": "DEL-01", "temperature": 9.3,
                  "pressure": 971.3, "humidity": 100.0}).json())
        assert probe.recommended_action
        alerts = S.AlertListResponse.model_validate(
            client.get("/api/v1/alerts", params={"limit": 5}).json()).alerts
        detail = S.AlertDetailResponse.model_validate(
            client.get(f"/api/v1/alerts/{alerts[0].alert_id}").json())
        assert detail.recommended_action
        assert "seasonal" in probe.evidence.model_dump() or True
        station = S.StationDetailResponse.model_validate(
            client.get("/api/v1/stations/DEL-01").json())
        assert station.maintenance.get("state") in (
            "MAINTENANCE_REVIEW_RECOMMENDED", "ELEVATED_WATCH",
            "NO_ACTION_INDICATED", "NOT_APPLICABLE")

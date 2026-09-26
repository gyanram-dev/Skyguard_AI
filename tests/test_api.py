"""Phase 12 API tests: endpoints, schemas, replay honesty, guards."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import schemas as S


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (startup loads frozen artifacts once)."""
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


# 1+2. Health endpoint + model loading truthfulness.
def test_1_2_health_and_models(client):
    for path in ("/health", "/api/v1/health"):
        response = client.get(path)
        assert response.status_code == 200
        payload = S.HealthResponse.model_validate(response.json())
        assert payload.service == "skyguard-api"
        assert set(payload.model_status.model_dump()) == {
            "statistical", "isolation_forest", "lstm_autoencoder",
            "ensemble", "root_cause"}
        assert all(v == "loaded" for v in payload.model_status.model_dump().values())


# 3+14+16. Station listing, replay labeling, determinism.
def test_3_14_16_station_listing(client):
    first = client.get("/api/v1/stations")
    assert first.status_code == 200
    payload = S.StationListResponse.model_validate(first.json())
    assert payload.data_mode == "historical_replay"
    ids = [s.station_id for s in payload.stations]
    assert {"DEL-01", "JENA-01", "AMD-06"} <= set(ids)
    offline = next(s for s in payload.stations if s.station_id == "AMD-06")
    assert offline.status == "offline" and offline.data_available is False
    assert offline.temperature is None and offline.anomaly_score is None
    second = client.get("/api/v1/stations")
    assert second.json() == first.json()


# 4+5. Station lookup + not-found behavior.
def test_4_5_station_lookup(client):
    response = client.get("/api/v1/stations/DEL-01")
    assert response.status_code == 200
    payload = S.StationDetailResponse.model_validate(response.json())
    assert payload.station.city == "Delhi"
    assert payload.station.data_mode == "historical_replay"
    assert payload.anomaly.method == "ensemble"
    assert client.get("/api/v1/stations/NOPE-99").status_code == 404
    assert client.get("/api/v1/stations/AMD-06").status_code == 404


# 6+7. History endpoint + invalid variable handling.
def test_6_7_history(client):
    response = client.get("/api/v1/stations/DEL-01/history",
                          params={"variable": "temperature", "hours": 24})
    assert response.status_code == 200
    payload = S.HistoryResponse.model_validate(response.json())
    assert payload.data_mode == "historical_replay" and len(payload.points) > 0
    assert client.get("/api/v1/stations/DEL-01/history",
                      params={"variable": "wind"}).status_code == 422
    assert client.get("/api/v1/stations/AMD-06/history").status_code == 404


# 8+9+10. Alert listing, lookup, not-found behavior.
def test_8_9_10_alerts(client):
    response = client.get("/api/v1/alerts", params={"limit": 50})
    assert response.status_code == 200
    payload = S.AlertListResponse.model_validate(response.json())
    assert payload.data_mode == "historical_replay" and len(payload.alerts) > 0
    stamps = [a.timestamp for a in payload.alerts]
    assert stamps == sorted(stamps, reverse=True)
    assert len({a.alert_id for a in payload.alerts}) == len(payload.alerts)
    first_id = payload.alerts[0].alert_id
    detail = client.get(f"/api/v1/alerts/{first_id}")
    assert detail.status_code == 200
    bundle = S.AlertDetailResponse.model_validate(detail.json())
    assert bundle.alert.alert_id == first_id
    assert bundle.ensemble_method == "ens_median"
    assert bundle.history.hours == 24 and len(bundle.history.series) > 0
    assert client.get("/api/v1/alerts/bogus").status_code == 404


# 11+12. Network summary counts + schema validation.
def test_11_12_network_summary(client):
    response = client.get("/api/v1/network/summary")
    assert response.status_code == 200
    payload = S.NetworkSummary.model_validate(response.json())
    stations = client.get("/api/v1/stations").json()["stations"]
    assert payload.stations_monitored == len(stations)
    assert (payload.healthy + payload.needs_review + payload.anomaly
            + payload.offline) == len(stations)
    assert payload.offline >= 2  # AMD-06, HYD-07


# 13. CORS restricted to development origins (no wildcard).
def test_13_cors(client):
    response = client.options("/api/v1/stations",
                              headers={"Origin": "http://localhost:3000",
                                       "Access-Control-Request-Method": "GET"})
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    evil = client.get("/api/v1/stations", headers={"Origin": "https://evil.example"})
    assert evil.headers.get("access-control-allow-origin") in (None, "")


# 15. Missing artifacts fail fast with exact causes (no fake data).
def test_15_missing_artifacts(tmp_path):
    from src.api.dependencies import DataStore

    with pytest.raises(RuntimeError, match="Missing required artifacts"):
        DataStore.load(tmp_path)


# 17. No training/fitting/calibration inside the serving path (loading
# frozen artifacts via joblib.load / load_model is mandated serving).
def test_17_no_training_in_handlers():
    text = "\n".join((Path("src/api") / f).read_text(encoding="utf-8")
                     for f in ("app.py", "dependencies.py", "services/station_service.py",
                               "services/observation_service.py", "services/anomaly_service.py",
                               "services/investigation_service.py", "services/network_service.py",
                               "services/health_service.py"))
    lowered = text.lower()
    for banned in (".fit(", "randomforestclassifier(", "sequential(",
                   ".fit_predict(", "model.compile(", "standardscaler(",
                   "earlystopping(", "treeexplainer("):
        assert banned not in lowered, banned


# 18. Phase 1-11 artifacts unchanged (counts + frozen thresholds).
def test_18_phases_unchanged():
    import json

    import pandas as pd

    assert len(pd.read_csv("data/features/jena_features.csv",
                           usecols=["timestamp"])) == 420224
    assert len(pd.read_csv("data/benchmark/jena/train.csv",
                           usecols=["timestamp"])) == 251969
    assert len(pd.read_csv("data/ensemble/jena_ensemble_predictions.csv",
                           usecols=["timestamp"])) == 167426
    if_cfg = json.load(open("reports/isolation_forest/model_config.json"))
    assert if_cfg["jena"]["threshold_raw"] == pytest.approx(0.026259994424697897)
    ens_cfg = json.load(open("reports/ensemble/calibration_config.json"))
    assert set(ens_cfg["jena"]["thresholds"]) == {"ens_mean", "ens_median"}
    assert Path("data/noaa/metadata/neighbor_graph.csv").is_file()

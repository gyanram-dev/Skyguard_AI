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
        # Intentional change (startup memory audit): inference artifacts are
        # no longer loaded at startup — they are reported as 'deferred' and
        # load lazily on first use through the scoring cache, so status is
        # 'ready' (artifacts present, nothing broken). The in-process
        # statistical rules need no artifact and stay 'loaded'.
        status = payload.model_status.model_dump()
        assert status["statistical"] == "loaded"
        assert all(v == "deferred" for k, v in status.items() if k != "statistical")
        assert payload.status == "ready"


# 3+14+16. Station listing, replay labeling, determinism.
def test_3_14_16_station_listing(client):
    first = client.get("/api/v1/stations")
    assert first.status_code == 200
    payload = S.StationListResponse.model_validate(first.json())
    assert payload.data_mode == "historical_replay"
    ids = [s.station_id for s in payload.stations]
    assert {"DEL-01", "CHD-09", "PUN-10", "HYD-07", "SAF-11", "GAU-12", "TRV-13"} <= set(ids)
    assert "JENA-01" not in ids
    assert len(ids) == 14
    assert all(station.data_available for station in payload.stations)
    delhi = next(station for station in payload.stations if station.station_id == "DEL-01")
    assert delhi.source_dataset == "delhi_clean"
    assert delhi.available_variables == ["temperature", "pressure", "relative_humidity"]
    assert delhi.probe_available is True
    context_station = next(station for station in payload.stations if station.station_id == "HYD-07")
    assert context_station.source_dataset == "noaa_ghcnh"
    assert context_station.available_variables == [
        "temperature", "pressure", "relative_humidity"]
    assert context_station.probe_available is False
    assert all(station.available_variables == [] for station in payload.stations if not station.data_available)
    second = client.get("/api/v1/stations")
    assert second.json() == first.json()


def test_jena_is_not_operational(client):
    stations = client.get("/api/v1/stations").json()["stations"]
    alerts = client.get("/api/v1/alerts", params={"limit": 1000}).json()["alerts"]
    assert all(station["station_id"] != "JENA-01" for station in stations)
    assert all("jena" not in alert["alert_id"].lower() for alert in alerts)
    assert client.get("/api/v1/stations/JENA-01").status_code == 404


def test_live_api_status_and_episode_detail_are_safe(client, caplog):
    import asyncio
    import json

    from src.api.services import live_service as LV
    from src.live import config as LC
    from src.live import manager as LM
    from src.live import obs as LO
    from src.live import sources as LS

    previous = LV.MANAGER
    try:
        missing_config = LC.LiveConfig()
        missing_config.mode = LC.LIVE_IMD
        missing_config.base_url = ""
        LV.MANAGER = LM.LiveManager(config=missing_config, db_path=":memory:")
        response = client.get("/api/v1/live/status")
        assert response.json()["status"] == "NOT_CONFIGURED"

        secret = "response-only-mock-secret"
        configured = LC.LiveConfig()
        configured.mode = LC.LIVE_IMD
        configured.base_url = "https://example.invalid/oapi"
        configured.request_headers = {"Authorization": f"Bearer {secret}"}
        manager = LM.LiveManager(config=configured, db_path=":memory:")

        class LeakySource(LS.ObservationSource):
            name = "IMD_WIS2"

            def fetch_new(self):
                raise LS.SourceError("http_error", f"rejected Bearer {secret}")

        manager.source = LeakySource()
        manager.source_name = manager.source.name
        asyncio.run(manager.poll_once())
        LV.MANAGER = manager
        response = client.get("/api/v1/live/status")
        assert response.status_code == 200
        assert response.json()["status"] == "CONNECTION_FAILED"
        assert secret not in json.dumps(response.json())
        assert secret not in caplog.text

        moment = LO.utcnow()
        observation = LO.CanonicalObservation(
            station_id="IMD-PATNA", timestamp=moment, temperature_c=31.0,
            source="IMD_WIS2", source_station_id="0-20000-0-42492",
            source_observation_id="api-detail-obs", received_at=moment)
        manager.store.save_observation(observation, LO.VALID, moment.isoformat())
        manager.store.upsert_episode(
            {"alert_id": "live-api-detail", "station_id": "IMD-PATNA",
             "episode_key": "IMD-PATNA|ANOMALY",
             "interpretation": "LOCAL_SENSOR_ANOMALY",
             "started_at": moment.isoformat(), "last_seen_at": moment.isoformat(),
             "detection_count": 1, "status": "OPEN", "resolved_at": None,
             "score": 0.997}, {"anomaly_score": 0.997, "root_cause": "SPIKE"})
        detail = client.get("/api/v1/live/alerts/live-api-detail")
        assert detail.status_code == 200
        assert detail.json()["source_mode"] == "LIVE_ALERT"
        assert detail.json()["evidence"]["root_cause"] == "SPIKE"
    finally:
        LV.MANAGER = previous


# 4+5. Station lookup + not-found behavior.
def test_4_5_station_lookup(client):
    response = client.get("/api/v1/stations/DEL-01")
    assert response.status_code == 200
    payload = S.StationDetailResponse.model_validate(response.json())
    assert payload.station.city == "Delhi"
    assert payload.station.data_mode == "historical_replay"
    assert payload.anomaly.method == "ensemble"
    assert client.get("/api/v1/stations/NOPE-99").status_code == 404
    assert client.get("/api/v1/stations/JENA-01").status_code == 404


# 6+7. History endpoint + invalid variable handling.
def test_6_7_history(client):
    response = client.get("/api/v1/stations/DEL-01/history",
                          params={"variable": "temperature", "hours": 24})
    assert response.status_code == 200
    payload = S.HistoryResponse.model_validate(response.json())
    assert payload.data_mode == "historical_replay" and len(payload.points) > 0
    assert client.get("/api/v1/stations/DEL-01/history",
                      params={"variable": "wind"}).status_code == 422
    assert client.get("/api/v1/stations/JENA-01/history").status_code == 404


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
    # Honest accounting: detector-covered verdicts, context-only stations and
    # offline stations partition the registry exactly.
    assert (payload.healthy + payload.needs_review + payload.anomaly
            + payload.offline + payload.context_only) == len(stations)
    assert (payload.detector_covered + payload.context_only
            + payload.offline) == len(stations)
    assert payload.offline == 0
    # Stations without detector coverage are never counted as healthy.
    assert payload.healthy <= payload.detector_covered
    assert payload.detector_covered == sum(
        1 for s in stations if s.get("probe_available"))


# 13. CORS: explicit allowlist plus rotating Vercel preview hostnames (no wildcard).
def test_13_cors(client):
    response = client.options("/api/v1/stations",
                              headers={"Origin": "http://localhost:3000",
                                       "Access-Control-Request-Method": "GET"})
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    vercel_origin = "https://skyguard-8dl6teuvp-gyan-rams-projects.vercel.app"
    vercel = client.options("/api/v1/stations",
                            headers={"Origin": vercel_origin,
                                     "Access-Control-Request-Method": "GET"})
    assert vercel.status_code in (200, 204)
    assert vercel.headers.get("access-control-allow-origin") == vercel_origin

    # A rotated Vercel deployment hostname must be covered by allow_origin_regex.
    preview_origin = "https://skyguard-abc123-gyan-rams-projects.vercel.app"
    preview = client.options("/api/v1/stations",
                             headers={"Origin": preview_origin,
                                      "Access-Control-Request-Method": "GET"})
    assert preview.status_code in (200, 204)
    assert preview.headers.get("access-control-allow-origin") == preview_origin

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

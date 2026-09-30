"""MVP integration tests: calibrated station detectors -> replay -> API.

Covers the serving path end to end on REAL GHCNh observations (plus controlled
fault injection for detection recall), the detector registry contract, the
unified detection result schema, replay WebSocket events, replay alert
persistence, and the station/alert/network API surface.

No thresholds are asserted as tuned values: the frozen z=3.0 / IQR=1.5 rules
and the frozen calibration artifacts are read, never weakened.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.replay import alerts as RA
from src.baseline.iqr_baseline import IQR_FACTOR
from src.baseline.zscore_baseline import Z_THRESHOLD
from src.detection import registry as REG
from src.detection.station_statistical import (
    CONFIDENCE_BASIS,
    StationStatisticalDetector,
    confidence_for,
    load_detector,
)

ROOT = Path(".")
PROCESSED = ROOT / "data" / "noaa" / "processed"
MUMBAI_CSV = PROCESSED / "INI0000VABB_2022_2024.csv"
HYDERABAD_CSV = PROCESSED / "INI0000VOHS_2022_2024.csv"

# Station IDs fixed by the calibration config; these must equal the audited
# GHCNh IDs already present in the station mapping.
MUMBAI = ("INI0000VABB", "MUM-03")
HYDERABAD = ("INI0000VOHS", "HYD-07")

REQUIRED_RESULT_FIELDS = {
    "station_id", "timestamp", "temperature", "relative_humidity", "pressure",
    "anomaly", "severity", "confidence", "detector", "primary_reason",
    "contributing_factors", "data_quality", "spatial_context",
}
SEVERITIES = {"NORMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
REQUIRED_EVENT_FIELDS = {
    "event_type", "station_id", "timestamp", "observation", "detection",
    "severity", "confidence", "reason",
}
ALERT_CONTRACT_FIELDS = {"station_id", "timestamp", "severity", "confidence",
                         "reason", "detector", "status"}


# ----------------------------------------------------------------- helpers


def detector_frame(path: Path) -> pd.DataFrame:
    """Detector input frame straight from a processed station file."""
    from src.detection.calibrate import detector_frame as build

    return build(path)


def slice_days(frame: pd.DataFrame, start: str, days: int) -> pd.DataFrame:
    rows = days * 48
    idx = frame.index[frame["timestamp"] >= start].min()
    return frame.iloc[int(idx):int(idx) + rows].reset_index(drop=True)


@pytest.fixture(scope="module")
def mumbai_frame() -> pd.DataFrame:
    return detector_frame(MUMBAI_CSV)


@pytest.fixture(scope="module")
def mumbai_demo() -> dict:
    """The real Mumbai CONTROLLED_DEMO, run end to end (writes its report)."""
    from src.detection.demo import run_demo

    return run_demo(ROOT, "INI0000VABB", days=30)


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (startup loads frozen artifacts once)."""
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


# --------------------------------------------------- 1. station calibration


def test_1_calibration_is_station_specific(mumbai_frame):
    """Two stations calibrated from real data hold different references."""
    cfg = {"station_id": MUMBAI[1], "backend_station_id": MUMBAI[0],
           "city": "Mumbai", "cadence_min": 30.0,
           "pressure_semantics": "altimeter_qnh_hpa",
           "pressure_column": "altimeter_setting_hpa",
           "rh_provenance": "REPORTED"}
    refs = {}
    for path, station in ((MUMBAI_CSV, cfg),
                          (HYDERABAD_CSV, {**cfg, "station_id": HYDERABAD[1],
                                           "backend_station_id": HYDERABAD[0],
                                           "city": "Hyderabad"})):
        frame = detector_frame(path)
        detector = StationStatisticalDetector.calibrate(
            station, frame, "2023-01-05 00:00:00", "2023-02-15 00:00:00")
        refs[station["station_id"]] = detector.artifact["reference_distribution"]
        assert detector.artifact["z_threshold"] == Z_THRESHOLD
        assert detector.artifact["iqr_factor"] == IQR_FACTOR
        assert detector.artifact["train_rows"] > 48
    assert refs[MUMBAI[1]]["temperature_c"]["median"] != \
        refs[HYDERABAD[1]]["temperature_c"]["median"]


def test_1b_calibration_rejects_insufficient_history(mumbai_frame):
    cfg = {"station_id": MUMBAI[1], "backend_station_id": MUMBAI[0],
           "city": "Mumbai", "cadence_min": 30.0,
           "pressure_semantics": "altimeter_qnh_hpa",
           "pressure_column": "altimeter_setting_hpa",
           "rh_provenance": "REPORTED"}
    with pytest.raises(ValueError):
        StationStatisticalDetector.calibrate(
            cfg, mumbai_frame.head(20), "2022-01-01 00:00:00",
            "2022-12-31 00:00:00")


# -------------------------------------------------------- 2-6. detection


@pytest.fixture(scope="module")
def scored(mumbai_frame):
    """Real Mumbai observations scored by the calibrated detector."""
    detector = load_detector(ROOT, MUMBAI[0])
    assert detector is not None
    frame = slice_days(mumbai_frame, "2023-05-01 00:00:00", 5)
    return detector, frame, detector.score_frame(frame, None)


def test_2_normal_observation_schema(scored):
    _, _, results = scored
    normals = [r for r in results if not r["anomaly"]]
    assert normals, "expected at least one unflagged real observation"
    for result in normals:
        assert result["severity"] == "NORMAL"
        assert result["confidence"] is None
        assert result["contributing_factors"] == []
        assert result["detector"] == "Statistical Baseline"


def test_3_4_5_6_faults_are_detected(mumbai_demo):
    """Controlled faults on real observations: measured, not manufactured."""
    per_fault = mumbai_demo["per_fault"]
    assert per_fault["spike"]["recall"] == 1.0          # abrupt, single row
    for fault in ("frozen", "drift", "cross_variable"):
        assert per_fault[fault]["injected"] >= 10
        assert per_fault[fault]["detected"] >= 1
        assert per_fault[fault]["recall"] is not None
    assert mumbai_demo["overall"]["recall"] > 0.0
    assert mumbai_demo["overall"]["tp"] > 0


def test_6b_missing_observation_is_not_flagged(mumbai_frame):
    detector = load_detector(ROOT, MUMBAI[0])
    frame = slice_days(mumbai_frame, "2023-05-01 00:00:00", 3).copy()
    frame.loc[72, "temperature_c"] = float("nan")
    results = detector.score_frame(frame, None)
    row = results[72]
    assert row["temperature"] is None
    assert row["anomaly"] is False
    assert row["severity"] == "NORMAL"
    assert row["relative_humidity"] is not None  # other channels still read
    assert row["data_quality"]["reason"]


# ---------------------------------------------------- 7-8. registry contract


def test_7_registry_contract():
    entries = REG.entries(ROOT)
    assert len(entries) == 10
    for entry in entries:
        for field in REG.ENTRY_FIELDS:
            assert entry.get(field) is not None, (entry["station_id"], field)
        assert entry["capability"] == "PARTIAL"
        assert entry["detector_available"] is True
        assert entry["cadence"] == 30.0
        assert entry["pressure_semantics"] == "altimeter_qnh_hpa"
        assert "REPORTED" in entry["rh_provenance"]
        assert entry["data_mode"] == "HISTORICAL"
    # Delhi's frozen detector is not part of this registry.
    assert REG.get(ROOT, "delhi") is None


def test_8_registry_ids_match_audited_station_mapping():
    mapping = json.loads((ROOT / "data" / "api" / "station_mapping.json")
                         .read_text(encoding="utf-8"))["stations"]
    by_backend = {m["backend_station_id"]: m for m in mapping}
    for entry in REG.entries(ROOT):
        mapped = by_backend.get(entry["backend_station_id"])
        assert mapped is not None, entry["backend_station_id"]
        assert mapped["frontend_station_id"] == entry["station_id"]
        assert mapped["city"] == entry["city"]


def test_8b_registry_artifacts_are_consistent():
    for entry in REG.entries(ROOT):
        artifact = json.loads(REG.artifact_path(ROOT, entry)
                              .read_text(encoding="utf-8"))
        assert artifact["station_id"] == entry["station_id"]
        assert artifact["backend_station_id"] == entry["backend_station_id"]
        assert artifact["cadence_min"] == entry["cadence"]
        assert artifact["detector_type"] == entry["detector_type"]
        assert artifact["pressure_semantics"] == entry["pressure_semantics"]


# ------------------------------------------------- 9. unified result schema


def test_9_unified_detection_result_schema(scored):
    _, frame, results = scored
    assert len(results) == len(frame)
    for result in results:
        assert REQUIRED_RESULT_FIELDS <= set(result)
        assert isinstance(result["anomaly"], bool)
        assert result["severity"] in SEVERITIES
        assert result["station_id"] == MUMBAI[1]
        assert result["timestamp"] == str(result["timestamp"])
        assert isinstance(result["contributing_factors"], list)
        assert set(result["data_quality"]) >= {"status", "ml_eligible", "reason"}
        assert "decision" in result["spatial_context"]
        # Human-readable values only: no enum representations leak out.
        for field in ("severity", "detector", "primary_reason"):
            assert "<" not in str(result[field])


def test_9b_confidence_comes_from_the_detector_rule(scored):
    _, _, results = scored
    for result in results:
        if not result["anomaly"]:
            assert result["confidence"] is None
            continue
        zmax = result["anomaly_score"]
        if zmax is None:
            assert result["confidence"] is None
            continue
        assert result["confidence"] == pytest.approx(
            confidence_for(zmax, True), abs=1e-3)
        assert 0.0 < result["confidence"] < 1.0
        assert result["confidence_basis"] == CONFIDENCE_BASIS


def test_9c_severity_never_says_normal_for_a_detected_anomaly(scored):
    _, _, results = scored
    for result in results:
        if result["anomaly"]:
            assert result["severity"] in SEVERITIES - {"NORMAL"}


# -------------------------------------------- 10. replay + WS + persistence


def test_10_replay_websocket_end_to_end(client):
    """Mumbai replay: OBSERVATION -> ANOMALY_DETECTED -> REPLAY_COMPLETE."""
    limit = 40
    events: list[dict] = []
    with client.websocket_connect("/api/v1/live") as ws:
        hello = ws.receive_json()
        assert hello["event_type"] == "CONNECTION"
        assert hello["data_mode"] == "historical_replay"
        ws.send_json({"action": "start", "station_id": MUMBAI[1],
                      "split": "OOD", "speed": 3600, "limit": limit})
        deadline = time.perf_counter() + 240.0
        while time.perf_counter() < deadline:
            message = ws.receive_json()
            events.append(message)
            if message["type"] == "complete":
                break
    for event in events:
        # Every message must be JSON-serializable (no enums, no NaN).
        assert isinstance(json.dumps(event), str)
    readings = [e for e in events if e["type"] == "reading"]
    alerts = [e for e in events if e["type"] == "alert"]
    complete = [e for e in events if e["type"] == "complete"]
    assert len(readings) == limit
    assert complete and complete[0]["event_type"] == "REPLAY_COMPLETE"
    assert complete[0]["split"] == "HISTORICAL"
    assert complete[0]["processed"] == limit
    assert complete[0]["anomalies"] == len(alerts)
    assert complete[0]["alerts_recorded"] == len(alerts)

    for reading in readings:
        assert REQUIRED_EVENT_FIELDS <= set(reading)
        assert reading["event_type"] == "OBSERVATION"
        assert reading["source_mode"] == "HISTORICAL_REPLAY"
        assert reading["data_mode"] == "historical_replay"
        assert reading["detection"]["anomaly"] is False or \
            reading["severity"] in SEVERITIES - {"NORMAL"}
    assert alerts, "real Mumbai replay must flag at least one observation"
    for alert in alerts:
        assert REQUIRED_EVENT_FIELDS <= set(alert)
        assert alert["event_type"] == "ANOMALY_DETECTED"
        assert alert["severity"] in SEVERITIES - {"NORMAL"}
        assert alert["reason"] == alert["detection"]["primary_reason"]
        assert alert["detector"] == "Statistical Baseline"

    # 11. Alert persistence: anomalous rows persisted, normal rows not.
    persisted = {record["alert_id"]: record
                 for record in RA.read_records(ROOT, MUMBAI[1])}
    for alert in alerts:
        assert alert["alert_id"] in persisted
        record = persisted[alert["alert_id"]]
        assert ALERT_CONTRACT_FIELDS <= set(record)
        assert record["severity"] == alert["severity"]
        assert record["status"] == RA.RECORD_STATUS
        assert record["data_mode"] == "HISTORICAL_REPLAY"
    normal_stamps = {r["timestamp"] for r in readings
                     if not r["detection"]["anomaly"]}
    for record in persisted.values():
        assert record["timestamp"] not in normal_stamps


def test_10b_replay_rejects_uncovered_station(client):
    """A GHCNh station with no calibrated detector stays unavailable."""
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "SAF-11",
                      "split": "OOD", "speed": 3600, "limit": 1})
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["code"] == "unknown_station"
        assert message["event_type"] == "ERROR"


# ------------------------------------------------- 12. replay alert storage


def test_12_alert_store_normal_vs_anomaly(tmp_path):
    store = RA.ReplayAlertStore(tmp_path)
    try:
        normal = {"station_id": "MUM-03", "timestamp": "2023-05-01 00:00:00",
                  "anomaly": False, "severity": "NORMAL", "confidence": None,
                  "primary_reason": "within station baseline bounds",
                  "detector": "Statistical Baseline", "anomaly_score": None}
        assert store.record(normal, backend_id=MUMBAI[0]) is None
        assert store.count("MUM-03") == 0

        anomaly = {**normal, "timestamp": "2023-05-01 00:30:00",
                   "anomaly": True, "severity": "MEDIUM", "confidence": 0.75,
                   "primary_reason": "SPIKE: abrupt deviation",
                   "anomaly_score": 9.0,
                   "data_quality": {"status": "PASS", "ml_eligible": True,
                                    "reason": "all_checks_passed"},
                   "temperature": 41.0, "pressure": 1005.0,
                   "relative_humidity": 60.0,
                   "contributing_factors": ["statistical flag"]}
        record = store.record(anomaly, backend_id=MUMBAI[0], city="Mumbai")
        assert record is not None
        assert ALERT_CONTRACT_FIELDS <= set(record)
        assert record["severity"] == "MEDIUM"
        assert record["confidence"] == 0.75
        assert record["detector"] == "Statistical Baseline"
        assert store.count("MUM-03") == 1
        # Idempotent: the same event never duplicates a record.
        store.record(anomaly, backend_id=MUMBAI[0], city="Mumbai")
        assert store.count("MUM-03") == 1
    finally:
        store.close()


# ------------------------------------------------------------ 13. API routes


def test_13_api_routes(client):
    stations = client.get("/api/v1/stations")
    assert stations.status_code == 200
    listing = stations.json()["stations"]
    mumbai = next(s for s in listing if s["station_id"] == MUMBAI[1])
    assert mumbai["capability"]["detector_capability"] == "PARTIAL"
    assert mumbai["capability"]["data_mode"] == "HISTORICAL"
    detector = mumbai["capability"]["detector"]
    assert detector["detector_available"] is True
    assert detector["cadence"] == 30.0
    assert detector["detector_type"] == "Statistical Baseline"
    assert detector["pressure_semantics"] == "altimeter_qnh_hpa"

    detail = client.get(f"/api/v1/stations/{MUMBAI[1]}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["station"]["station_id"] == MUMBAI[1]
    assert body["station"]["capability"]["detector_capability"] == "PARTIAL"
    assert body["observations"]["temperature_c"] is not None

    delhi = client.get("/api/v1/stations/DEL-01")
    assert delhi.status_code == 200
    assert delhi.json()["station"]["capability"]["detector_capability"] == \
        "FULL_TPR"

    alerts = client.get("/api/v1/alerts?limit=5")
    assert alerts.status_code == 200
    payload = alerts.json()
    assert payload["returned"] == len(payload["alerts"])
    assert payload["total"] >= payload["returned"]
    if payload["alerts"]:
        alert_id = payload["alerts"][0]["alert_id"]
        one = client.get(f"/api/v1/alerts/{alert_id}")
        assert one.status_code == 200
        assert one.json()["alert"]["alert_id"] == alert_id


def test_13b_network_summary_uses_measured_counts(client):
    response = client.get("/api/v1/network/summary")
    assert response.status_code == 200
    summary = response.json()
    for field in ("total_stations", "detector_covered", "historical_only",
                  "partial", "full_tpr", "live_capable", "total_observations"):
        assert field in summary, field
    assert summary["total_stations"] == len(
        json.loads((ROOT / "data" / "api" / "station_mapping.json")
                   .read_text(encoding="utf-8"))["stations"])
    assert summary["partial"] == 10
    assert summary["full_tpr"] == 1
    assert summary["detector_covered"] >= 1
    assert summary["total_observations"] > 0
    assert summary["live_capable"] > 0
    assert summary["historical_only"] == summary["context_only_stations"]
    # Uncovered GHCNh stations are contextual, never presented as healthy.
    assert summary["context_only_stations"] >= 1


def test_13c_uncovered_station_stays_context_only(monkeypatch):
    """Without a registry entry the same station must not claim coverage."""
    from src.api.services import station_service as SS

    mapping = json.loads((ROOT / "data" / "api" / "station_mapping.json")
                         .read_text(encoding="utf-8"))["stations"]
    entry = next(m for m in mapping if m["frontend_station_id"] == MUMBAI[1])
    monkeypatch.setattr(SS, "detector_registry_entry", lambda store, item: None)
    assert SS.detector_capability(None, entry, ["temperature", "pressure",
                                                "relative_humidity"]) == \
        "CONTEXT_ONLY"
    assert SS.detector_state(None, entry) is None


# --------------------------------------------------- 14. Delhi stays intact


def test_14_delhi_detector_untouched():
    assert REG.get(ROOT, "delhi") is None
    assert REG.get_by_frontend_id(ROOT, "DEL-01") is None
    assert not any(e["backend_station_id"] == "delhi"
                   for e in REG.entries(ROOT))


# ------------------------------------------------- 15. other city smoke tests


@pytest.mark.parametrize("backend_id,city", [
    ("INI0000VOBL", "Bengaluru"),
    ("INI0000VOHS", "Hyderabad"),
    ("INI0000VOMM", "Chennai"),
])
def test_15_city_smoke_detects_controlled_spike(backend_id, city):
    """The same detector architecture runs with each station's calibration."""
    from src.detection.demo import run_demo

    payload = run_demo(ROOT, backend_id, days=30)
    assert payload["city"] == city
    assert payload["label"] == "CONTROLLED_DEMO"
    assert payload["per_fault"]["spike"]["recall"] == 1.0
    assert payload["per_fault"]["frozen"]["detected"] >= 1
    assert payload["per_fault"]["drift"]["detected"] >= 1
    assert payload["per_fault"]["cross_variable"]["detected"] >= 1
    assert payload["overall"]["tp"] > 0
    assert payload["isolation"]

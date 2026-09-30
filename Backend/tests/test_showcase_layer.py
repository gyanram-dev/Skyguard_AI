"""Showcase layer: historical timeline, investigation hub, controlled demo.

These tests read the real frozen artifacts and are explicit about what is
asserted: existing detector output only (never a recomputed verdict at
request time), the existing Phase-22 spatial decision reused as-is, audited
neighbour edges, and a controlled demo that leaves the stored observations
unmodified.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.dependencies import DataStore
from src.api.services import fault_demo as FD
from src.api.services import investigation_hub as IH
from src.api.services import timeline_service as TL
from src.detection import registry as REG
from src.spatial import decision as SD


@pytest.fixture(scope="module")
def store() -> DataStore:
    """Real frozen artifacts, loaded once (same loader as the API)."""
    return DataStore.load(Path("."))


# ---------------------------------------------------------------------------
# Historical timeline
# ---------------------------------------------------------------------------

def test_timeline_artifact_carries_real_detector_provenance():
    # The loader needs only ``root``; keep this test independent of the
    # multi-second full store load.
    stub = type("Store", (), {"root": Path(".").resolve()})()
    artifact = TL.load_artifact(stub, "JAI-02")
    assert artifact is not None, "timeline artifact missing for JAI-02"

    period = artifact["period"]
    assert period["start"].startswith("2022-01-01")
    assert artifact["observations"] > 40000
    assert artifact["pressure_basis"] == "altimeter_qnh_hpa"

    detector = artifact["detector"]
    assert detector["available"] is True
    assert detector["coverage"] == "CALIBRATED_STATISTICAL"
    assert detector["threshold"] == 3.0
    assert detector["flags_total"] >= len(artifact["events"]) > 0

    series = artifact["series"]
    assert len(series["timestamps"]) <= 1100
    assert len(series["timestamps"]) == len(series["temperature"])
    assert any(value is not None for value in series["temperature"])

    event = artifact["events"][0]
    for field in ("timestamp", "score", "severity", "reason", "detector"):
        assert event.get(field) is not None
    assert event["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_timeline_reports_unavailable_verdict_for_context_only_station(store: DataStore):
    payload = TL.timeline(store, "TRV-13", max_points=200, max_events=5)
    assert payload["detector"]["available"] is False
    assert payload["events"] == []
    assert "no detector" in payload["detector"]["note"].lower()
    assert len(payload["series"]["timestamps"]) > 0  # observations still served


def test_timeline_uses_stored_ensemble_output_for_delhi(store: DataStore):
    payload = TL.timeline(store, "DEL-01", max_points=300, max_events=10)
    detector = payload["detector"]
    assert detector["available"] is True
    assert detector["coverage"] == "FROZEN_ENSEMBLE"
    # Injected benchmark rows must never be presented as history.
    assert detector["excluded_injection_rows"] > 0
    assert payload["events_total"] >= len(payload["events"])
    assert payload["series"]["timestamps"][0].startswith("2022-04-01")


# ---------------------------------------------------------------------------
# Investigation hub (existing spatial layer, audited neighbours)
# ---------------------------------------------------------------------------

def test_neighbours_come_from_the_audited_graph(store: DataStore):
    entry = IH.SS.get_mapping(store, "BLR-05")
    neighbours = IH.neighbour_entries(store, entry)
    resolved = {item["entry"]["frontend_station_id"] for item in neighbours}
    assert resolved == {"CHE-03", "TRV-13"}
    for item in neighbours:
        assert item["distance_km"] > 0
        assert item["rank"] >= 1


def test_investigation_reuses_phase22_spatial_decision(store: DataStore):
    payload = IH.build_investigation(store, "BLR-05", None)
    assert payload["interpretation"]["contextual_decision"] in (
        SD.LOCAL_SENSOR_ANOMALY, SD.POSSIBLE_REGIONAL_EVENT,
        SD.ANOMALY_WITHOUT_SPATIAL_CONFIRMATION, SD.INSUFFICIENT_EVIDENCE,
        SD.NORMAL)
    evidence = payload["comparison"]["temperature"]
    assert evidence["neighbor_count"] == 2
    assert evidence["status"] in (SD.SPATIAL_SUPPORTED, SD.SPATIAL_CONTRADICTED,
                                  SD.SPATIAL_INSUFFICIENT, SD.SPATIAL_UNAVAILABLE)
    assert payload["detector_verdict"]["available"] is True
    assert "never confirmation" in " ".join(payload["notes"])


def test_investigation_is_honest_without_neighbours(store: DataStore):
    payload = IH.build_investigation(store, "MUM-03", None)
    assert payload["nearby"] == []
    assert payload["expected_neighbors"] == 0
    assert payload["comparison"]["neighbor_median_temperature"] is None
    assert any("no neighbour values are invented" in note
               for note in payload["notes"])


def test_investigation_never_converts_pressure_basis(store: DataStore):
    """AWS station pressure vs GHCNh QNH altimeter: reported unavailable."""
    payload = IH.build_investigation(store, "DEL-01", None)
    pressure = payload["comparison"]["pressure"]
    assert pressure["status"] == SD.SPATIAL_UNAVAILABLE
    assert "pressure_basis_mismatch" in pressure["reason"]
    assert payload["pressure_basis"] == "station_level_hpa"
    assert payload["nearby"], "Delhi is served through audited Delhi-context edges"


def test_investigation_anchor_is_causal(store: DataStore):
    """Neighbour observations are never later than the anchored target row."""
    payload = IH.build_investigation(store, "BLR-05", "2024-06-01 12:00:00+00:00")
    anchor = payload["anchor"]["timestamp"]
    for neighbor in payload["nearby"]:
        if neighbor["aligned_timestamp"] is None:
            continue
        assert neighbor["aligned_timestamp"] <= anchor
        assert neighbor["age_minutes"] is not None and neighbor["age_minutes"] >= 0


def test_detector_registry_and_investigation_agree_on_coverage(store: DataStore):
    """A station with a registered detector gets a real verdict at the anchor."""
    entry = IH.SS.get_mapping(store, "CHE-03")
    assert REG.get(Path(".").resolve(), entry["backend_station_id"]) is not None
    payload = IH.build_investigation(store, "CHE-03", None)
    verdict = payload["detector_verdict"]
    assert verdict["available"] is True
    assert verdict["data_quality_status"] in ("PASS", "POSSIBLE_FREEZE", "FAIL", "NA")
    assert payload["interpretation"]["base_decision"] in (
        SD.BASE_NORMAL, SD.BASE_ANOMALOUS, SD.BASE_INSUFFICIENT)


# ---------------------------------------------------------------------------
# Controlled fault demo
# ---------------------------------------------------------------------------

def test_fault_demo_detects_every_fault_without_touching_stored_data(store: DataStore):
    payload = FD.build(store)

    assert payload["label"] == "CONTROLLED DEMO"
    assert "NOT LIVE IMD DATA" in payload["disclaimer"]
    assert payload["stored_data_modified"] is False
    assert payload["station_id"] == "DEL-01"

    summary = payload["summary"]
    assert summary["faults_total"] == 4
    assert summary["faults_detected"] == 4, summary["by_phase"]
    assert summary["normal_false_positives"] == 0

    rows = payload["rows"]
    assert len(rows) == summary["rows"] > 100
    phases = [row["phase"] for row in rows]
    assert phases[:1] == ["NORMAL"]
    assert {"SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE"} <= set(phases)

    # Determinism: the same call returns the same payload.
    assert FD.build(store) == payload

    # The freeze rule (deterministic, not trained) must own the frozen rows.
    frozen = [row for row in rows
              if row["phase"] == "FROZEN" and row["detection"]["anomaly"]]
    assert frozen, "frozen segment was never detected"
    assert any(row["detection"]["root_cause"] == "FROZEN" and
               row["detection"]["trigger"] == "freeze" for row in frozen)

    # The injected spike must be caught, with the reason text attached.
    spike = [row for row in rows if row["phase"] == "SPIKE"]
    assert spike and all(row["detection"]["anomaly"] for row in spike)
    assert all(row["detection"]["reason"] for row in spike)

    # Real NORMAL rows pass through unmodified: values equal the stored record.
    obs = store.pipeline["delhi"]["obs"]
    stored = {str(ts): value for ts, value in
              zip(obs["timestamp"].astype(str), obs["temperature_c"])}
    normal = [row for row in rows if row["phase"] == "NORMAL"]
    for row in normal[:40]:
        assert stored[row["timestamp"]] == pytest.approx(row["temperature_c"])

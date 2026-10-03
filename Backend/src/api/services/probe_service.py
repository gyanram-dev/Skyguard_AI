"""Judge-probe entry point: validation, station context, response assembly.

Scoring itself lives in src.api.services.scoring (shared with replay).
This module validates the judge's input, resolves the station, builds the
history+probe frame, and maps the scored position onto ProbeResponse.
"""

from __future__ import annotations

import math

import pandas as pd

from src.api.services import operator_actions as OA
from src.api.services import scoring as SC
from src.ensemble.aggregation import INSUFFICIENT_EVIDENCE
from src.features.feature_builder import CADENCE_HORIZONS

DATA_MODE = "historical_replay"

# Trailing real history rows scored alongside the probe (covers the 6h
# feature horizon on both cadences; the probe itself is the final row).
HISTORY_ROWS = 200

# API-input protection bounds (validation only, never anomaly thresholds).
TEMP_MIN, TEMP_MAX = -90.0, 70.0
PRESSURE_MIN, PRESSURE_MAX = 300.0, 1150.0
HUMIDITY_MIN, HUMIDITY_MAX = 0.0, 100.0

# Structured error codes returned to the frontend.
INVALID_INPUT = "invalid_input"
STATION_REQUIRED = "station_required"
UNKNOWN_STATION = "unknown_station"
INSUFFICIENT_CONTEXT = "insufficient_context"
MODELS_UNAVAILABLE = "models_unavailable"


class ProbeError(Exception):
    """Structured probe failure (status_code, code, detail)."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def _validate_inputs(temperature, pressure, humidity) -> tuple[float, float, float]:
    """API protection: finite numbers inside wide physical bounds."""
    for name, value, lo, hi in (("temperature", temperature, TEMP_MIN, TEMP_MAX),
                                ("pressure", pressure, PRESSURE_MIN, PRESSURE_MAX),
                                ("humidity", humidity, HUMIDITY_MIN, HUMIDITY_MAX)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProbeError(422, INVALID_INPUT, f"'{name}' must be a number.")
        if not math.isfinite(float(value)):
            raise ProbeError(422, INVALID_INPUT, f"'{name}' must be finite.")
        if not (lo <= float(value) <= hi):
            raise ProbeError(
                422, INVALID_INPUT,
                f"'{name}' {value} is outside acceptable input range [{lo}, {hi}].")
    return float(temperature), float(pressure), float(humidity)


def resolve_dataset(store, station_id: str | None) -> tuple[dict, str]:
    """Mapping entry + pipeline dataset, or a structured ProbeError."""
    if station_id is None:
        raise ProbeError(422, STATION_REQUIRED,
                         "A station is required: contextual inference needs "
                         "station history. No default station is assumed.")
    entry = next((m for m in store.mapping if m["frontend_station_id"] == station_id), None)
    if entry is None or not entry.get("backend_station_id"):
        raise ProbeError(404, UNKNOWN_STATION,
                         f"Station '{station_id}' is not available for probing.")
    if entry.get("source_dataset") == "noaa_ghcnh":
        from src.api.services import station_service as SS

        if SS.detector_registry_entry(store, entry) is not None:
            raise ProbeError(422, INSUFFICIENT_CONTEXT,
                             f"Station '{station_id}' is covered by a calibrated "
                             "station-specific detector, which runs during historical "
                             "replay; the interactive probe runs the frozen ensemble, "
                             "which does not cover this station.")
        raise ProbeError(422, INSUFFICIENT_CONTEXT,
                         f"Station '{station_id}' has contextual observations only; "
                         "no detector models cover it, so probe inference is unavailable.")
    ds = entry["backend_station_id"]
    if ds != "delhi":
        raise ProbeError(404, UNKNOWN_STATION,
                         f"Station '{station_id}' is not available for probing.")
    return entry, ds


def run_probe(store, station_id: str | None,
              temperature: float, pressure: float, humidity: float) -> dict:
    """Score one judge-supplied observation through the frozen pipeline."""
    temp_c, pres_hpa, hum_pct = _validate_inputs(temperature, pressure, humidity)
    _, ds = resolve_dataset(store, station_id)

    cadence_min = int(CADENCE_HORIZONS[ds]["expected_interval_min"])
    obs = store.pipeline[ds]["obs"]
    history = obs.tail(HISTORY_ROWS).reset_index(drop=True)
    anchor = str(history["timestamp"].iloc[-1])
    probe_ts = (pd.Timestamp(anchor) + pd.Timedelta(minutes=cadence_min)).strftime(
        "%Y-%m-%d %H:%M:%S")
    frame = pd.DataFrame({
        "timestamp": history["timestamp"].astype(str).tolist() + [probe_ts],
        "temperature_c": history["temperature_c"].tolist() + [temp_c],
        "pressure_hpa": history["pressure_hpa"].tolist() + [pres_hpa],
        "relative_humidity_pct": history["relative_humidity_pct"].tolist() + [hum_pct],
    })

    try:
        frames = SC.build_frames(store, ds, frame)
    except SC.ModelUnavailableError as exc:
        raise ProbeError(503, MODELS_UNAVAILABLE,
                         f"Probe inference is unavailable: {exc}") from exc
    pos = len(frame) - 1
    segment = frames["features"]["segment_id"].to_numpy()
    if segment[pos] != segment[pos - 1]:
        raise ProbeError(422, INSUFFICIENT_CONTEXT,
                         "Insufficient historical context for probe inference: "
                         "the probe does not continue the station's latest segment.")
    try:
        scored = SC.score_position(frames, ds, pos,
                                   spatial_ts=anchor, spatial_temp=temp_c)
    except SC.ModelUnavailableError as exc:
        raise ProbeError(503, MODELS_UNAVAILABLE,
                         f"Probe inference is unavailable: {exc}") from exc
    if scored["ensemble"]["availability"] == INSUFFICIENT_EVIDENCE:
        raise ProbeError(422, INSUFFICIENT_CONTEXT,
                         "Insufficient historical context for probe inference: "
                         "fewer than two detector components are available.")
    ens = scored["ensemble"]
    verdict = scored["verdict"]
    anomalous = bool(verdict["is_anomalous"])
    detector_label = None
    if anomalous:
        detector_label = {
            "freeze": "Freeze detector (deterministic stuck-signal rule)",
            "ensemble+freeze": "Frozen ensemble + freeze detector",
        }.get(verdict["trigger"],
              "Frozen ensemble (statistical + Isolation Forest + LSTM)")
    return {
        "data_mode": DATA_MODE,
        "probe": {"station_id": station_id, "temperature": temp_c,
                  "pressure": pres_hpa, "humidity": hum_pct},
        "context": {
            "station_available": True,
            "historical_anchor": anchor,
            "spatial_available": bool(scored["evidence"]["spatial"]["available"]),
            "neighbor_count": int(scored["evidence"]["spatial"].get("neighbor_count", 0)),
            "context_note": ("This probe evaluates the supplied observation against "
                             f"{station_id}'s available historical context anchored at "
                             f"{anchor}; replayed history, not live sensors."),
        },
        "result": {
            "is_anomalous": anomalous,
            "anomaly_score": ens["median"],
            "confidence": verdict["confidence"],
            "confidence_basis": verdict["confidence_basis"],
            "availability": ens["availability"],
            "threshold": ens["threshold"],
            "severity": verdict["severity"],
            "trigger": verdict["trigger"],
            "method": verdict["method"],
        },
        "evidence": {
            "statistical": scored["evidence"]["statistical"],
            "isolation_forest": scored["evidence"]["isolation_forest"],
            "lstm": scored["evidence"]["lstm"],
            "multivariate": scored["evidence"]["multivariate"],
            "spatial": scored["evidence"]["spatial"],
            "seasonal": scored["evidence"]["seasonal"],
            "data_quality": scored["data_quality"],
            "freeze": scored["freeze"],
        },
        "root_cause": scored["root_cause"],
        "explanation": scored["explanation"],
        "spatial_decision": scored["spatial_decision"],
        "detector": detector_label,
        "severity": verdict["severity"] if anomalous else None,
        "primary_reason": None,
        "contributing_factors": None,
        "recommended_action": OA.for_root_cause(
            scored["root_cause"]["class"],
            scored["spatial_decision"]["contextual_decision"])
        if anomalous else OA.for_verdict(True),
    }

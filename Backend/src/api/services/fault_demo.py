"""Controlled fault demo: deterministic replay of injected sensor faults.

The demo streams REAL Delhi observations from ``data/processed/delhi_clean.csv``
through the SAME serving inference core the probe and replay use
(``src.api.services.scoring``). Faults are applied with the EXISTING
benchmark injectors (``src.benchmark.injectors``) using fixed parameters
taken from the frozen benchmark configuration ranges
(``src.benchmark.config``) — no new thresholds, no new models, no changed
detector behaviour.

Honesty rules enforced here:

- the stored observations are never modified: rows are read into a new
  frame and injections happen on that copy only;
- every row carries its phase label, so a detection is never presented as
  a real-world event;
- the payload label is explicit that this is a controlled demonstration,
  not live IMD data;
- NORMAL rows are real, unmodified observations, so any flag on them is a
  genuine false positive and is reported as such.

The sequence is deterministic: fixed anchor timestamp, fixed injection
parameters, fixed row counts. Repeated calls return identical output.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.api.services import scoring as SC
from src.benchmark import config as BC
from src.benchmark.injectors import (apply_cross_variable, apply_drift,
                                     apply_frozen, apply_spike)

logger = logging.getLogger("skyguard.fault_demo")

LABEL = "CONTROLLED DEMO"
DISCLAIMER = ("CONTROLLED DEMO — NOT LIVE IMD DATA. Injected values exist only "
              "in this stream; the stored observations are unmodified.")

STATION_ID = "DEL-01"
BACKEND_ID = "delhi"

# Deterministic anchor inside the real Delhi AWS record (moderate, clean
# conditions): temperatures in the high 20s/low 30s with no fault flags on
# the surrounding rows.
ANCHOR = "2024-03-10 06:00:00"
CONTEXT_ROWS = 144          # unmodified real observations used as causal context
SEGMENTS = (
    ("NORMAL", 84, "Real observations, unmodified."),
    ("SPIKE", 3, "Temperature offset applied (fixed 20.0 C)."),
    ("FROZEN", 10, "Temperature held at the window-start value."),
    ("DRIFT", 36, "Temperature ramping at a fixed 4.0 C/hour."),
    ("CROSS_VARIABLE", 12, "Fixed per-reading ramps on T/RH/P (controlled "
                           "multivariate inconsistency)."),
)

# Fixed parameters, inside the frozen benchmark ranges (train_id group):
# SPIKE_AMPLITUDE temperature 15-25 C, DRIFT_RATE_PER_HOUR temperature
# 2.0-4.0, CROSS_RATES_PER_READING train_id group.
SPIKE_AMPLITUDE_C = 20.0
DRIFT_RATE_C_PER_HOUR = 4.0
CROSS_RATES = {"temperature_c": 0.8, "relative_humidity_pct": 1.5,
               "pressure_hpa": -0.3}

_CACHE: dict[str, dict] = {}


def _real_window(store) -> pd.DataFrame:
    """Real Delhi rows: CONTEXT_ROWS before the anchor plus every demo row."""
    obs = store.pipeline[BACKEND_ID]["obs"]
    stamps = obs["timestamp"].astype(str)
    mask = stamps >= ANCHOR
    if not bool(mask.any()):
        raise RuntimeError(f"Anchor {ANCHOR} is outside the Delhi record.")
    start = int(mask.to_numpy().nonzero()[0][0]) - CONTEXT_ROWS
    if start < 0:
        raise RuntimeError("Not enough preceding observations for causal context.")
    total = sum(rows for _, rows, _ in SEGMENTS)
    window = obs.iloc[start:start + CONTEXT_ROWS + total].reset_index(drop=True)
    if len(window) < CONTEXT_ROWS + total:
        raise RuntimeError("Delhi record does not cover the demo window.")
    return window


CORE_VARIABLES = ("temperature_c", "pressure_hpa", "relative_humidity_pct")


def _apply_injections(window: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return a copy with the deterministic fault sequence applied.

    Positional writes only: a fault must never spill into the next
    segment, so every segment is written with iloc ranges.
    """
    frame = window.reset_index(drop=True).copy()
    columns = {name: frame.columns.get_loc(name) for name in CORE_VARIABLES}
    phases: list[str] = ["NORMAL"] * CONTEXT_ROWS
    cursor = CONTEXT_ROWS
    for name, rows, _note in SEGMENTS:
        start, end = cursor, cursor + rows

        def read(column: str) -> np.ndarray:
            return frame.iloc[start:end, columns[column]].to_numpy(dtype=float)

        def write(column: str, values) -> None:
            frame.iloc[start:end, columns[column]] = np.asarray(values, dtype=float)

        if name == "SPIKE":
            write("temperature_c", apply_spike(read("temperature_c"),
                                               SPIKE_AMPLITUDE_C, 1))
        elif name == "FROZEN":
            frozen = apply_frozen({c: read(c) for c in CORE_VARIABLES},
                                  "temperature_c")
            for column, values in frozen.items():
                write(column, values)
        elif name == "DRIFT":
            elapsed_hours = np.arange(1, rows + 1, dtype=float) * (5.0 / 60.0)
            write("temperature_c", apply_drift(read("temperature_c"),
                                               DRIFT_RATE_C_PER_HOUR, 1,
                                               elapsed_hours))
        elif name == "CROSS_VARIABLE":
            ramped = apply_cross_variable({c: read(c) for c in CORE_VARIABLES},
                                          CROSS_RATES)
            for column, values in ramped.items():
                write(column, values)
        phases.extend([name] * rows)
        cursor = end
    return frame, phases


def _detection_row(result: dict) -> dict:
    verdict = result["verdict"]
    ensemble = result["ensemble"]
    rc = result["root_cause"]
    return {
        "anomaly": bool(verdict["is_anomalous"]),
        "severity": verdict.get("severity"),
        "confidence": verdict.get("confidence"),
        "confidence_basis": verdict.get("confidence_basis"),
        "trigger": verdict.get("trigger"),
        "method": verdict.get("method"),
        "score": ensemble.get("median"),
        "threshold": ensemble.get("threshold"),
        "availability": ensemble.get("availability"),
        "components_available": ensemble.get("n_components"),
        "root_cause": (rc.get("class") if verdict["is_anomalous"] else "NORMAL"),
        "root_cause_confidence": rc.get("confidence"),
        "root_cause_basis": rc.get("basis"),
        "pattern": ("FROZEN" if result["freeze"].get("confirmed") else None),
        "frozen_variable": (result["freeze"].get("variable")
                            if result["freeze"].get("confirmed") else None),
        "freeze": result["freeze"] if result["freeze"].get("confirmed") else None,
        "reason": result["explanation"]["text"],
        "explanation_features": result["explanation"]["features"][:5],
        "multivariate_max_abs_robust_deviation_2h":
            result["evidence"]["multivariate"].get(
                "multivariate_max_abs_robust_deviation_2h"),
        "data_quality": result["data_quality"]["status"],
        "spatial_context": result["spatial_decision"].get("contextual_decision"),
    }


def build(store) -> dict:
    """Deterministic controlled demo payload (cached after first run)."""
    if STATION_ID in _CACHE:
        return _CACHE[STATION_ID]
    window = _real_window(store)
    injected, phases = _apply_injections(window)
    sensor = pd.DataFrame({
        "timestamp": window["timestamp"].astype(str),
        "temperature_c": injected["temperature_c"],
        "pressure_hpa": injected["pressure_hpa"],
        "relative_humidity_pct": injected["relative_humidity_pct"],
    })
    frames = SC.build_frames(store, BACKEND_ID, sensor)
    rows = []
    for pos in range(CONTEXT_ROWS, len(sensor)):
        result = SC.score_position(frames, BACKEND_ID, pos,
                                   spatial_ts=str(sensor["timestamp"].iloc[pos]),
                                   spatial_temp=SC.num(
                                       sensor["temperature_c"].iloc[pos]))
        rows.append({
            "index": pos - CONTEXT_ROWS,
            "timestamp": str(sensor["timestamp"].iloc[pos]),
            "phase": phases[pos],
            "injected": phases[pos] != "NORMAL",
            "temperature_c": SC.num(sensor["temperature_c"].iloc[pos]),
            "pressure_hpa": SC.num(sensor["pressure_hpa"].iloc[pos]),
            "relative_humidity_pct": SC.num(
                sensor["relative_humidity_pct"].iloc[pos]),
            "detection": _detection_row(result),
        })
    summary: dict = {"rows": len(rows), "by_phase": {}}
    for name, _, _note in SEGMENTS:
        phase_rows = [r for r in rows if r["phase"] == name]
        detections = [r for r in phase_rows if r["detection"]["anomaly"]]
        summary["by_phase"][name] = {
            "rows": len(phase_rows),
            "detected": len(detections),
            "first_detection": (
                {"index": detections[0]["index"],
                 "timestamp": detections[0]["timestamp"],
                 "severity": detections[0]["detection"]["severity"],
                 "root_cause": detections[0]["detection"]["root_cause"],
                 "confidence": detections[0]["detection"]["confidence"]}
                if detections else None),
        }
    normal = summary["by_phase"]["NORMAL"]
    summary["normal_false_positives"] = normal["detected"]
    summary["faults_detected"] = sum(
        1 for name, _, _ in SEGMENTS if name != "NORMAL"
        and summary["by_phase"][name]["detected"] > 0)
    summary["faults_total"] = len(SEGMENTS) - 1
    payload = {
        "label": LABEL,
        "disclaimer": DISCLAIMER,
        "station_id": STATION_ID,
        "city": "Delhi",
        "city_coordinates": {"latitude": 28.6139, "longitude": 77.209},
        "source_dataset": "delhi_clean (real AWS observations)",
        "cadence_min": 5.0,
        "anchor": ANCHOR,
        "context_rows": CONTEXT_ROWS,
        "detector": "Frozen ensemble (statistical + Isolation Forest + LSTM) "
                    "with the deterministic freeze rule",
        "injection_parameters": {
            "spike_amplitude_c": SPIKE_AMPLITUDE_C,
            "frozen_variable": "temperature_c",
            "frozen_rows": 10,
            "drift_rate_c_per_hour": DRIFT_RATE_C_PER_HOUR,
            "cross_variable_rates_per_reading": CROSS_RATES,
            "source": "frozen benchmark configuration ranges "
                      "(src.benchmark.config), train_id group",
        },
        "summary": summary,
        "rows": rows,
        "stored_data_modified": False,
    }
    _CACHE[STATION_ID] = payload
    return payload

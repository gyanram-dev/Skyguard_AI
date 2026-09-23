"""Ground-truth label construction.

Row labels: one row per present benchmark observation.
Event labels: one row per fault event (sensor faults and gaps).
Injected values: clean vs injected per affected observation/variable.

Labels are evaluation metadata ONLY and must never enter model input
matrices. Non-injected background rows (ground_truth_anomaly = 0) are
NOT proven normal — they are non-injected background observations.
"""

from __future__ import annotations

import pandas as pd

from src.benchmark import config as C

ROW_LABEL_COLUMNS = [
    "timestamp",
    "dataset",
    "split",
    "ground_truth_anomaly",
    "ground_truth_fault_type",
    "injection_id",
    "target_variable",
    "injection_start",
    "injection_end",
    "injection_layer",
]

EVENT_LABEL_COLUMNS = [
    "injection_id",
    "dataset",
    "split",
    "fault_type",
    "target_variable",
    "start_timestamp",
    "end_timestamp",
    "duration_rows",
    "duration_minutes",
    "layer",
    "amplitude",
    "direction",
    "drift_rate_per_hour",
    "run_length",
    "anchor_value",
    "start_value",
    "end_value",
    "rates_per_reading",
    "components",
    "removed_row_count",
]


def build_event_label(event, cadence_min: int) -> dict:
    """Flatten a PlannedEvent into an event-label row."""
    p = event.params
    spike = p.get("spike") if isinstance(p.get("spike"), dict) else None
    return {
        "injection_id": event.injection_id,
        "dataset": event.dataset,
        "split": event.split,
        "fault_type": event.fault_type,
        "target_variable": event.target_variable,
        "start_timestamp": p["_start_timestamp"],
        "end_timestamp": p["_end_timestamp"],
        "duration_rows": event.duration_rows,
        "duration_minutes": round(event.duration_rows * cadence_min, 3),
        "layer": C.LAYER_DATA_QUALITY if event.fault_type == "COMMUNICATION_GAP" else C.LAYER_ML_BENCHMARK,
        "amplitude": p.get("amplitude", spike.get("amplitude") if spike else None),
        "direction": p.get("direction", spike.get("direction") if spike else None),
        "drift_rate_per_hour": p.get("drift_rate_per_hour"),
        "run_length": p.get("run_length"),
        "anchor_value": p.get("anchor_value"),
        "start_value": p.get("start_value"),
        "end_value": p.get("end_value"),
        "rates_per_reading": str(p.get("rates_per_reading")) if p.get("rates_per_reading") else None,
        "components": str(["SPIKE", "DRIFT"]) if event.fault_type == "SPIKE_PLUS_DRIFT" else None,
        "removed_row_count": p.get("removed_row_count"),
    }

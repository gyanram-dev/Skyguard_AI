"""Event-level detection and latency from row-level results.

An event is DETECTED when at least one of its injected rows is flagged.
Latency = first_detection_timestamp - injection_start_timestamp (minutes);
NaN when never detected (never fabricated).
"""

from __future__ import annotations

import pandas as pd


def build_event_results(
    row_results: pd.DataFrame,
    event_labels: pd.DataFrame,
    dataset: str,
    split: str,
) -> pd.DataFrame:
    """One row per injected sensor-fault event with per-method outcomes."""
    faults = event_labels[event_labels["fault_type"] != "COMMUNICATION_GAP"].copy()
    faults = faults[faults["split"] == split].reset_index(drop=True)
    rows = row_results.reset_index(drop=True)

    records: list[dict] = []
    for _, e in faults.iterrows():
        # Event rows located by injection id (exact, gap-free by construction).
        sub = rows[rows["injection_id"] == e["injection_id"]].sort_values("timestamp")
        n_rows = len(sub)
        rec: dict = {
            "source_dataset": dataset.lower(),
            "split": split,
            "injection_id": e["injection_id"],
            "fault_type": e["fault_type"],
            "target_variable": e["target_variable"],
            "start_timestamp": e["start_timestamp"],
            "end_timestamp": e["end_timestamp"],
            "duration_minutes": float(e["duration_minutes"]),
            "injected_row_count": int(n_rows),
        }
        start_ts = pd.Timestamp(e["start_timestamp"])
        for method, col in (("zscore", "zscore_combined_flag"), ("iqr", "iqr_combined_flag")):
            flagged = sub[sub[col] == 1]
            detected = len(flagged) > 0
            rec[f"{method}_detected"] = int(detected)
            rec[f"{method}_detected_row_count"] = int(len(flagged))
            if detected:
                first = pd.Timestamp(flagged["timestamp"].iloc[0])
                rec[f"{method}_first_detection_timestamp"] = str(flagged["timestamp"].iloc[0])
                rec[f"{method}_latency_minutes"] = (first - start_ts).total_seconds() / 60.0
            else:
                rec[f"{method}_first_detection_timestamp"] = None
                rec[f"{method}_latency_minutes"] = float("nan")
        records.append(rec)
    cols = ["source_dataset", "split", "injection_id", "fault_type", "target_variable",
            "start_timestamp", "end_timestamp", "duration_minutes", "injected_row_count",
            "zscore_detected", "iqr_detected",
            "zscore_detected_row_count", "iqr_detected_row_count",
            "zscore_first_detection_timestamp", "iqr_first_detection_timestamp",
            "zscore_latency_minutes", "iqr_latency_minutes"]
    return pd.DataFrame(records, columns=cols)

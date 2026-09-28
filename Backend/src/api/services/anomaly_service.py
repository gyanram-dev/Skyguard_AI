"""Operational alerts from frozen detector outputs (no benchmark truth).

An alert is a run of consecutively flagged ensemble rows
(`ens_median_flag == 1` on evaluation-eligible rows) in the frozen
per-row predictions. No injection IDs, fault-type labels, event tables,
latencies, or hidden test labels enter: those belong to offline
evaluation only. A per-row root-cause diagnosis is attached when the
frozen diagnosis table has one for the alert's first timestamp;
otherwise the alert stays `review`/`None` instead of inventing one.
"""

from __future__ import annotations

import pandas as pd


def build_alerts(store) -> list[dict]:
    """Detector-driven alerts, timestamp descending (frozen outputs)."""
    alerts: list[dict] = []
    for ds in ("jena", "delhi"):
        bundle = store.pipeline[ds]
        frame = bundle["ens"].sort_values("timestamp").reset_index(drop=True)
        rc_index = _diagnosis_index(bundle["rc"])
        frontend = _frontend_for(store, ds)
        flagged = (frame["ens_median_flag"].astype(int) == 1).to_numpy()
        eligible = (frame["evaluation_eligible"].astype(int) == 1).to_numpy()
        active = bool(flagged[0] and eligible[0]) if len(frame) else False
        start = 0
        for pos in range(len(frame)):
            on = bool(flagged[pos] and eligible[pos])
            if on and not active:
                active, start = True, pos
            if active and (not on or pos == len(frame) - 1):
                end = pos if on else pos - 1
                alerts.append(_event_alert(store, ds, frontend, frame,
                                           rc_index, start, end))
                active = False
    alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    return alerts


def _diagnosis_index(rc: pd.DataFrame) -> dict:
    """First diagnosed row per timestamp (frozen classifier outputs)."""
    index = {}
    if rc is None or len(rc) == 0 or "timestamp" not in rc.columns:
        return index
    flagged = rc[rc["has_diagnosis"].astype(bool)].sort_values("timestamp")
    for stamp, row in flagged.groupby(flagged["timestamp"].astype(str), sort=True):
        first = row.iloc[0]
        index[str(stamp)] = {
            "class": str(first["predicted_class"]),
            "confidence": _num(first.get("confidence")),
        }
    return index


def _event_alert(store, ds: str, frontend: str, frame: pd.DataFrame,
                 rc_index: dict, start: int, end: int) -> dict:
    """One alert for a consecutive flagged run [start, end]."""
    window = frame.iloc[start:end + 1]
    stamp = str(window["timestamp"].iloc[0])
    score = _num(pd.to_numeric(window["ens_median"], errors="coerce").max())
    diagnosis = rc_index.get(stamp)
    predicted = diagnosis["class"] if diagnosis else None
    confidence = diagnosis["confidence"] if diagnosis else None
    if predicted is None or predicted == "UNKNOWN":
        status, event = "review", (predicted if predicted else "Anomaly")
    else:
        status, event = "anomaly", predicted
    rows = int(end - start + 1)
    return {
        "alert_id": f"{ds}:op:{stamp}",
        "station_id": frontend,
        "backend_id": ds,
        "timestamp": stamp,
        "status": status,
        "event": event,
        "anomaly_score": score,
        "detection_rows": str(rows),
        "root_cause": predicted,
        "root_cause_confidence": confidence,
        "summary": (f"{event} on {frontend}: {rows} flagged rows from {stamp}; "
                    f"max ensemble score {score if score is not None else 'unknown'}."),
    }


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    import math

    return None if math.isnan(number) else number


def _frontend_for(store, backend_id: str) -> str:
    for entry in store.mapping:
        if entry.get("backend_station_id") == backend_id:
            return entry["frontend_station_id"]
    return backend_id

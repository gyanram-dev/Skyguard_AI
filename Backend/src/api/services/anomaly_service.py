"""Alert construction from frozen ensemble events + root-cause diagnosis."""

from __future__ import annotations

import pandas as pd


def build_alerts(store) -> list[dict]:
    """Detected ID/OOD events with measured summaries (timestamp desc)."""
    alerts: list[dict] = []
    for ds in ("jena", "delhi"):
        events = pd.read_csv(store.root / "reports" / "ensemble" / f"{ds}_event_results.csv")
        events = events[events["method"] == "ens_median_flag"]
        diag = pd.read_csv(store.root / "reports" / "root_cause" / "end_to_end_diagnosis.csv")
        diag = diag[(diag["dataset"] == ds)
                    & (diag["split"].isin(("test_in_distribution", "test_generalization")))]
        rc = store.pipeline[ds]["rc"]
        frontend = _frontend_for(store, ds)
        for _, event in events.iterrows():
            if int(event.get("detected", 0)) != 1:
                continue
            if str(event.get("split")) not in ("test_in_distribution", "test_generalization"):
                continue
            match = diag[diag["injection_id"] == event["injection_id"]]
            predicted, confidence = None, None
            if len(match):
                predicted = str(match.iloc[0]["predicted_class"])
                sub = rc[rc["injection_id"] == event["injection_id"]]
                sub = sub[sub["has_diagnosis"].astype(bool)]
                if len(sub) and "confidence" in sub.columns:
                    confidence = float(pd.to_numeric(sub["confidence"],
                                                     errors="coerce").mean())
            ens_rows = store.pipeline[ds]["ens"]
            ens_sub = ens_rows[ens_rows["injection_id"] == event["injection_id"]]
            score = None
            if len(ens_sub):
                flagged = ens_sub[ens_sub["ens_median_flag"].astype(int) == 1]
                pool = flagged if len(flagged) else ens_sub
                score = _num(pd.to_numeric(pool["ens_median"], errors="coerce").max())
            status = "review" if predicted == "UNKNOWN" else "anomaly"
            latency = event.get("latency_minutes")
            try:
                latency_text = f"{float(latency):.1f} min" if latency == latency else "unknown latency"
            except (TypeError, ValueError):
                latency_text = "unknown latency"
            alerts.append({
                "alert_id": f"{ds}:{event['split']}:{event['injection_id']}",
                "station_id": frontend,
                "backend_id": ds,
                "timestamp": str(event["start_timestamp"]),
                "status": status,
                "event": str(event["fault_type"]),
                "anomaly_score": score,
                "detection_rows": f"{int(event['detected_row_count'])}/"
                                  f"{int(event['injected_row_count'])}",
                "latency_minutes": latency,
                "root_cause": predicted,
                "root_cause_confidence": confidence,
                "summary": (f"{event['fault_type']} on {event['target_variable']}: "
                            f"{int(event['detected_row_count'])}/"
                            f"{int(event['injected_row_count'])} rows flagged, first "
                            f"detection {latency_text} after start."),
            })
    alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    return alerts


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

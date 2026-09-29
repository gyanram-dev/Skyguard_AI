"""Analysis over normalized uploaded frames (station-specific context).

Reused existing machinery (same definitions, no retraining, no new
thresholds for production components):
- features/quality ... prepare_split (delhi-shaped frame + inferred cadence)
- statistical ......... build_statistical_baseline (frozen Z/IQR rules)
- multivariate ........ canonical Phase 3 deviation features
- data quality ........ batch validator priority taxonomy

Deliberately NOT applied (marked unavailable with reasons): Delhi/Jena
Isolation Forest, LSTM, calibrated ensemble, trained root-cause
classifier, SHAP, spatial neighbors — those artifacts are validated only
for their training stations. Root-cause *estimates* below are transparent
pattern heuristics over measured features, labeled as such, never
presented as trained-model diagnoses.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

from src.api.services.upload_session import UploadError, get_session
from src.baseline.statistical_baseline import build_statistical_baseline
from src.baseline.zscore_baseline import Z_THRESHOLD
from src.data_quality.quality_engine import (
    COMMUNICATION_GAP,
    DATA_AVAILABILITY_EVENT,
    DATA_INTEGRITY_FAULT,
)
from src.features.feature_builder import horizons_for_cadence
from src.isolation_forest.evaluator import prepare_split
from src.spatial import decision as SD

logger = logging.getLogger("skyguard.upload_analysis")

DATA_MODE = "upload_analysis"

GAP_STATUSES = {COMMUNICATION_GAP, DATA_AVAILABILITY_EVENT, DATA_INTEGRITY_FAULT}

RECOMMENDED_ACTIONS = {
    "SPIKE": "Verify the observation and cross-check nearby/reference stations.",
    "DRIFT": "Inspect sensor calibration and review recent sensor behavior.",
    "FROZEN": "Check sensor operation and telemetry.",
    "CROSS": "Cross-check the affected variables and inspect sensor consistency.",
    "COMMUNICATION_GAP": "Check data transmission/network availability.",
    "UNKNOWN": "Insufficient evidence for a specific diagnosis; operator review recommended.",
}


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _station_entries(session: dict) -> list[tuple[str, dict]]:
    """Normalized per-station frames in deterministic order."""
    stations = session.get("stations")
    if not stations:
        raise UploadError(422, "mapping_required",
                         "Confirm column mapping and units before preview.")
    return sorted(stations.items(), key=lambda kv: kv[0])


def _station_preview(sid: str, entry: dict) -> dict:
    frame = entry["frame"]
    cadence = float(entry["cadence_min"])
    features, quality = prepare_split(frame, "delhi", cadence)
    stamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    valid = stamps.dropna()
    rh = pd.to_numeric(frame["relative_humidity_pct"], errors="coerce")
    has_rh = bool(rh.notna().any())
    return {
        "station": sid,
        "rows": int(len(frame)),
        "time_range": {"start": str(valid.min()), "end": str(valid.max())}
        if len(valid) else {"start": None, "end": None},
        "cadence_min": cadence,
        "horizons": horizons_for_cadence(cadence),
        "duplicates": int(quality["timestamp_duplicate"].sum()),
        "missing": {
            "temperature": int(quality["temperature_missing"].sum()),
            "humidity": int(quality["humidity_missing"].sum()),
            "pressure": int(quality["pressure_missing"].sum()),
        },
        "large_gaps": int(quality["communication_gap"].sum()),
        "invalid_timestamps": int(entry.get("invalid_timestamps", 0)),
        "non_finite": int(quality["physical_sanity_fault"].sum()),
        "rh_invalid": int((((rh < 0) | (rh > 100)).fillna(False)).sum())
        if has_rh else None,
        "rh_available": has_rh,
        "pressure_available": bool(pd.to_numeric(
            frame["pressure_hpa"], errors="coerce").notna().any()),
        "ml_eligible": int((quality["ml_eligible"] == 1).sum()),
        "quality_counts": {str(k): int(v) for k, v in
                           quality["quality_status"].value_counts().items()},
    }


def dq_preview(session_id: str) -> dict:
    """Dataset + data-quality summary for a confirmed upload (no ML)."""
    session = get_session(session_id)
    parts = [_station_preview(sid, entry) for sid, entry in _station_entries(session)]
    total_rows = sum(p["rows"] for p in parts)
    cadences = sorted({p["cadence_min"] for p in parts})
    horizons = horizons_for_cadence(cadences[0])
    merged_missing = {"temperature": 0, "humidity": 0, "pressure": 0}
    merged_counts: dict[str, int] = {}
    for p in parts:
        for k in merged_missing:
            merged_missing[k] += int(p["missing"].get(k, 0))
        for k, v in p["quality_counts"].items():
            merged_counts[k] = merged_counts.get(k, 0) + int(v)
    starts = [p["time_range"]["start"] for p in parts if p["time_range"]["start"]]
    ends = [p["time_range"]["end"] for p in parts if p["time_range"]["end"]]
    return {
        "session_id": session_id,
        "station_label": session["station_label"],
        "rows": int(total_rows),
        "time_range": {"start": min(starts) if starts else None,
                       "end": max(ends) if ends else None},
        "cadence_min": cadences[0],
        "horizons": horizons,
        "duplicates": sum(p["duplicates"] for p in parts),
        "missing": merged_missing,
        "large_gaps": sum(p["large_gaps"] for p in parts),
        "invalid_timestamps": sum(p["invalid_timestamps"] for p in parts),
        "non_finite": sum(p["non_finite"] for p in parts),
        "rh_invalid": sum(p["rh_invalid"] or 0 for p in parts)
        if any(p["rh_available"] for p in parts) else None,
        "rh_available": any(p["rh_available"] for p in parts),
        "pressure_available": any(p["pressure_available"] for p in parts),
        "ml_eligible": sum(p["ml_eligible"] for p in parts),
        "quality_counts": merged_counts,
        "stations": parts,
    }


def _estimate_pattern(feat: pd.Series, dq_freeze: bool) -> tuple[str, str]:
    """Transparent pattern estimate over measured features (heuristic).

    Returns (class, reason). Documented rules only; MIXED is never forced
    (single-row heuristics cannot assess combined faults honestly).
    """
    devs = {v: abs(_num(feat.get(f"{v}_deviation_from_median_2h")) or 0.0)
            for v in ("temperature", "pressure", "humidity")}
    zmax = max(devs.values())
    # FROZEN only when a *deviating* variable is itself unchanged (stuck at
    # an extreme); flat-but-normal channels must not mask a real spike.
    for v in ("temperature", "pressure", "humidity"):
        if devs[v] >= 3.0 and int(_num(feat.get(f"{v}_zero_delta")) or 0) == 1 \
                and dq_freeze:
            return "FROZEN", f"{v} unchanged at a departing level with a freeze flag"
    if zmax >= 6.0:
        return "SPIKE", f"abrupt {zmax:.1f} robust-deviation jump within 2h"
    flagged = [v for v, d in devs.items() if d >= 3.0]
    if len(flagged) == 1:
        return "CROSS", f"only {flagged[0]} departs while related signals hold"
    # DRIFT needs slope exceeding local variability (not just nonzero noise).
    for v in ("temperature", "pressure", "humidity"):
        trend = _num(feat.get(f"{v}_trend_2h")) or 0.0
        spread = _num(feat.get(f"{v}_prev_std_2h")) or 0.0
        if spread > 0 and abs(trend) > spread:
            return "DRIFT", (f"sustained directional movement ({v} "
                             f"{trend:+.4f}/h vs local std {spread:.4f})")
    return "UNKNOWN", "pattern does not match a known fault shape"


def _upload_spatial_decision() -> dict:
    """Shared contextual policy for stations with no neighbor graph.

    Same ``decide_context`` function as probe/replay/batch: with no
    usable neighbors the interpretation is honestly unconfirmed.
    """
    empty = SD.variable_evidence(None, {}, 0)
    decision = SD.decide_context(SD.BASE_ANOMALOUS, empty)
    decision["description"] = SD.describe(decision)
    return decision


def _analyze_station(frame: pd.DataFrame, cadence: float, station: str,
                     multi: bool) -> tuple[list, dict, int]:
    """Statistical + DQ + multivariate analysis for one station frame."""
    features, quality = prepare_split(frame, "delhi", cadence)
    baseline, _ = build_statistical_baseline(features, quality, "delhi",
                                             cadence_min=cadence)
    z_cols = ["temperature_zscore_baseline", "pressure_zscore_baseline",
              "humidity_zscore_baseline"]
    z_mat = np.stack([pd.to_numeric(baseline[c], errors="coerce").to_numpy(dtype=float)
                      for c in z_cols], axis=1)
    records = []
    breakdown: dict[str, int] = {}
    for pos in range(len(frame)):
        dq_status = str(quality["quality_status"].iloc[pos])
        eligible = bool(int(quality["ml_eligible"].iloc[pos]))
        flag = baseline["statistical_baseline_flag"].iloc[pos]
        flagged = bool(eligible and pd.notna(flag) and float(flag) == 1.0)
        if not flagged:
            continue
        feat = features.iloc[pos]
        z_row = z_mat[pos]
        finite_z = z_row[np.isfinite(z_row)]
        zmax = float(np.nanmax(np.abs(finite_z))) if len(finite_z) else None
        freeze_flag = "possible_freeze" in str(quality["quality_reason"].iloc[pos])
        estimate, reason = _estimate_pattern(feat, freeze_flag)
        temp = _num(frame["temperature_c"].iloc[pos])
        pres = _num(frame["pressure_hpa"].iloc[pos])
        hum = _num(frame["relative_humidity_pct"].iloc[pos])
        multi = _num(feat.get("multivariate_max_abs_robust_deviation_2h"))
        correction = None
        if estimate == "SPIKE" and pos > 0:
            prev = _num(frame["temperature_c"].iloc[pos - 1])
            if prev is not None:
                correction = {
                    "original_value": temp,
                    "suggested_value": prev,
                    "reason": "Last valid observation before the spike; "
                              "operator approval required.",
                }
        breakdown[estimate] = breakdown.get(estimate, 0) + 1
        zmax_text = f"{zmax:.2f}" if zmax is not None else "unavailable (zero local variance)"
        records.append({
            "timestamp": str(frame["timestamp"].iloc[pos]),
            "station": station,
            "observation": {"temperature_c": temp, "pressure_hpa": pres,
                            "relative_humidity_pct": hum},
            "score": round(zmax, 4) if zmax is not None else None,
            "decision": "anomaly",
            "confidence": None,
            "root_cause_estimate": estimate,
            "evidence": {
                "statistical": {
                    "max_abs_z": round(zmax, 4) if zmax is not None else None,
                    "threshold": Z_THRESHOLD,
                    "reason": str(baseline["statistical_baseline_reason"].iloc[pos]),
                },
                "temporal": {
                    "cadence_min": cadence,
                    "frozen": freeze_flag,
                },
                "multivariate": {"max_abs_robust_deviation_2h": multi},
                "data_quality": {"status": dq_status, "ml_eligible": eligible},
                "ml_models": {"available": False,
                              "reason": "Delhi/Jena-trained detectors are not "
                                        "validated for unseen stations."},
                "spatial": {"available": False,
                            "reason": "No neighbor context for an unseen station.",
                            "spatial_decision": _upload_spatial_decision()},
            },
            "explanation": (
                f"Heuristic pattern estimate ({estimate}): {reason}; "
                f"max|z|={zmax_text} vs baseline threshold {Z_THRESHOLD}. "
                "Not a trained-model diagnosis."),
            "correction": correction,
            "recommended_action": RECOMMENDED_ACTIONS[estimate],
        })
    dq_total = int((quality["quality_status"] != "PASS").sum())
    return records, breakdown, dq_total


def run_analysis(session_id: str) -> dict:
    """Full uploaded-dataset analysis (statistical + DQ + multivariate)."""
    session = get_session(session_id)
    entries = _station_entries(session)
    multi = len(entries) > 1
    label = session["station_label"]
    records: list = []
    breakdown: dict[str, int] = {}
    total = 0
    dq_total = 0
    per_station = []
    for sid, entry in entries:
        station_name = sid if multi else label
        part_records, part_breakdown, part_dq = _analyze_station(
            entry["frame"], float(entry["cadence_min"]), station_name, multi)
        records.extend(part_records)
        for key, count in part_breakdown.items():
            breakdown[key] = breakdown.get(key, 0) + int(count)
        total += int(entry["rows"])
        dq_total += int(part_dq)
        per_station.append({"station": station_name, "rows": int(entry["rows"]),
                            "cadence_min": float(entry["cadence_min"]),
                            "anomalies": int(len(part_records))})
    records.sort(key=lambda r: (r["timestamp"], r["station"]))
    result = {
        "session_id": session_id,
        "filename": session["filename"],
        "station_label": label,
        "data_mode": DATA_MODE,
        "cadence_min": float(entries[0][1]["cadence_min"]),
        "observations": int(total),
        "normal": int(total - len(records)),
        "anomalies": int(len(records)),
        "dq_events": int(dq_total),
        "evidence_availability": {
            "statistical": True, "temporal": True, "multivariate": True,
            "data_quality": True, "isolation_forest": False, "lstm": False,
            "ensemble": False, "root_cause_model": False, "shap": False,
            "spatial": False,
        },
        "breakdown": breakdown,
        "anomalies_detail": records,
        "mapping": session.get("mapping"),
        "units": session.get("units"),
        "stations": per_station,
        "notes": [
            "Anomaly decisions reuse the frozen statistical baseline "
            f"(|z|>{Z_THRESHOLD} or IQR flag) on station-specific rolling context.",
            "Root-cause values are heuristic pattern estimates, not "
            "trained-classifier diagnoses; confidence is not reported.",
            "ML detectors and spatial context are marked unavailable: their "
            "artifacts are validated only for Delhi/Jena.",
        ],
    }
    with_ = get_session(session_id)
    with_["analysis"] = result
    return result


def get_result(session_id: str) -> dict:
    """Stored analysis result for navigation re-fetch (no recompute)."""
    session = get_session(session_id)
    result = session.get("analysis")
    if result is None:
        raise UploadError(404, "analysis_not_found",
                         "No analysis stored for this session yet.")
    return result

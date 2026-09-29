"""Contextual anomaly interpretation from neighbor agreement.

A deterministic decision layer AFTER detector evidence is available:

    detector evidence -> base decision -> spatial context
    -> contextual interpretation -> final classification

Spatial context NEVER enters the ensemble score and NEVER creates an
anomaly from a normal base decision; it only re-interprets an already
flagged observation as locally inconsistent with its neighborhood
(LOCAL_SENSOR_ANOMALY), consistent with it (POSSIBLE_REGIONAL_EVENT),
or unconfirmed (ANOMALY_WITHOUT_SPATIAL_CONFIRMATION). Nearby stations
are contextual evidence, never confirmation of a physical event.

Causality: neighbor values are gathered with
``src.spatial.alignment.align_neighbor`` (neighbor timestamp <= target
timestamp, 30-minute tolerance, no interpolation, no fill), so future
neighbor observations cannot influence a decision.

Thresholds are conventions, fixed before any measurement and never
fitted to held-out outcomes: the contradiction boundary mirrors the
official statistical threshold (``Z_THRESHOLD = 3.0``); the support
boundary (2.0) leaves an indeterminate band so borderline cases keep
the base decision instead of flipping on noise.

Variable policy: temperature is primary. Relative humidity participates
only when measured at both target and neighbor (never manufactured).
Pressure participates only when both sides share the altimeter basis;
AWS station pressure against neighbor altimeter is reported
UNAVAILABLE with an explicit basis-mismatch reason.
"""

from __future__ import annotations

import math

import pandas as pd

from src.spatial.alignment import TIME_TOLERANCE, align_neighbor
from src.spatial.reference import neighbor_mad, neighbor_median

# Base detector states (input).
BASE_NORMAL = "BASE_NORMAL"
BASE_ANOMALOUS = "BASE_ANOMALOUS"
BASE_INSUFFICIENT = "BASE_INSUFFICIENT"

# Per-variable spatial states (output).
SPATIAL_SUPPORTED = "SPATIAL_SUPPORTED"
SPATIAL_CONTRADICTED = "SPATIAL_CONTRADICTED"
SPATIAL_UNAVAILABLE = "SPATIAL_UNAVAILABLE"
SPATIAL_INSUFFICIENT = "SPATIAL_INSUFFICIENT"

# Contextual classifications (output).
NORMAL = "NORMAL"
LOCAL_SENSOR_ANOMALY = "LOCAL_SENSOR_ANOMALY"
POSSIBLE_REGIONAL_EVENT = "POSSIBLE_REGIONAL_EVENT"
ANOMALY_WITHOUT_SPATIAL_CONFIRMATION = "ANOMALY_WITHOUT_SPATIAL_CONFIRMATION"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

# Robust-score bands: |target - neighbor_median| / MAD.
# Fixed conventions (see module docstring), not fitted values.
SUPPORT_SCORE_MAX = 2.0
CONTRADICT_SCORE_MIN = 3.0
MIN_SCORABLE_NEIGHBORS = 2

# Per-neighbor agreement bands in multiples of neighborhood MAD.
SUPPORT_BAND_MAD = 2.0
CONTRADICT_BAND_MAD = 3.0


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def gather_neighbor_values(target_ts, neighbor_frames: dict,
                           selected: list[str], column: str,
                           ts_col: str = "timestamp_utc",
                           tolerance=TIME_TOLERANCE) -> dict:
    """Latest value per selected neighbor at/before the target timestamp.

    Returns ``{neighbor_id: float | None}`` in ``selected`` order
    (duplicates removed, order preserved). ``None`` marks a stale or
    missing neighbor — never filled, never interpolated. Deterministic:
    inputs are sorted internally, so source row order cannot matter.
    """
    seen: list[str] = []
    for nid in selected:
        if nid not in seen:
            seen.append(nid)
    target = pd.Series([pd.to_datetime(target_ts, utc=True)])
    out: dict = {}
    for nid in seen:
        frame = neighbor_frames.get(nid)
        if frame is None or column not in frame.columns or len(frame) == 0:
            out[nid] = None
            continue
        pos = align_neighbor(target, frame[ts_col], tolerance=tolerance)
        idx = int(pos.iloc[0])
        if idx < 0:
            out[nid] = None
            continue
        out[nid] = _finite(frame[column].iloc[idx])
    return out


def variable_evidence(target_value, values_by_id: dict,
                      expected_count: int,
                      pressure_compatible: bool = True) -> dict:
    """Per-variable spatial evidence record (pure, deterministic).

    ``values_by_id`` maps neighbor id -> value or None (see
    :func:`gather_neighbor_values`). ``expected_count`` is the number
    of neighbors the geography provides; fewer usable ones degrade the
    state instead of failing.
    """
    target = _finite(target_value)
    ids = list(values_by_id)
    usable = {nid: _finite(values_by_id[nid]) for nid in ids}
    usable = {nid: v for nid, v in usable.items() if v is not None}
    n_usable = len(usable)
    record = {
        "status": SPATIAL_UNAVAILABLE,
        "reference_median": None,
        "mad": None,
        "robust_score": None,
        "deviation": None,
        "neighbor_count": int(expected_count),
        "usable_neighbor_count": int(n_usable),
        "supporting_neighbors": [],
        "contradicting_neighbors": [],
        "reason": "",
    }
    if not pressure_compatible:
        record["reason"] = ("pressure_basis_mismatch: station pressure "
                            "is never compared against altimeter data")
        return record
    if target is None:
        record["reason"] = "target_missing"
        return record
    if n_usable == 0:
        record["reason"] = "no_usable_neighbors"
        return record
    vals = [usable[nid] for nid in ids if nid in usable]
    median = float(neighbor_median(vals))
    mad = float(neighbor_mad(vals))
    record["reference_median"] = median
    record["mad"] = mad if math.isfinite(mad) else None
    record["deviation"] = float(target) - median
    if n_usable < MIN_SCORABLE_NEIGHBORS:
        record["reason"] = "fewer_than_two_usable_neighbors"
        record["status"] = SPATIAL_INSUFFICIENT
        return record
    if not math.isfinite(mad) or mad == 0.0:
        record["reason"] = "degenerate_neighbor_dispersion"
        record["status"] = SPATIAL_INSUFFICIENT
        return record
    score = abs(float(target) - median) / mad
    record["robust_score"] = float(score)
    for nid in ids:
        if nid not in usable:
            continue
        gap = abs(usable[nid] - float(target))
        if gap <= SUPPORT_BAND_MAD * mad:
            record["supporting_neighbors"].append(nid)
        elif gap > CONTRADICT_BAND_MAD * mad:
            record["contradicting_neighbors"].append(nid)
    if score <= SUPPORT_SCORE_MAX:
        record["status"] = SPATIAL_SUPPORTED
        record["reason"] = "target_consistent_with_neighbors"
    elif score >= CONTRADICT_SCORE_MIN:
        record["status"] = SPATIAL_CONTRADICTED
        record["reason"] = "target_disagrees_with_neighbors"
    else:
        record["status"] = SPATIAL_INSUFFICIENT
        record["reason"] = "indeterminate_band"
    return record


def decide_context(base_state: str, temp_evidence: dict,
                   humidity_evidence: dict | None = None) -> dict:
    """Contextual classification from base decision + spatial evidence.

    Temperature drives the classification; humidity is reported as
    corroboration only. The base anomaly verdict is always preserved:
    spatial agreement can suggest a regional reading but never clears
    the flag, and spatial evidence never creates a flag from normal.
    """
    temp_status = str(temp_evidence.get("status", SPATIAL_UNAVAILABLE))
    rh_status = str((humidity_evidence or {}).get("status", SPATIAL_UNAVAILABLE))
    if base_state == BASE_INSUFFICIENT:
        contextual, influence = INSUFFICIENT_EVIDENCE, "none"
    elif base_state == BASE_NORMAL:
        contextual, influence = NORMAL, "none"
    elif temp_status == SPATIAL_CONTRADICTED:
        contextual, influence = LOCAL_SENSOR_ANOMALY, "contradicted"
    elif temp_status == SPATIAL_SUPPORTED:
        contextual, influence = POSSIBLE_REGIONAL_EVENT, "supported"
    elif temp_status == SPATIAL_UNAVAILABLE:
        contextual, influence = ANOMALY_WITHOUT_SPATIAL_CONFIRMATION, "unavailable"
    else:
        contextual, influence = ANOMALY_WITHOUT_SPATIAL_CONFIRMATION, "insufficient"
    corroboration = None
    if rh_status == SPATIAL_SUPPORTED and temp_status == SPATIAL_SUPPORTED:
        corroboration = "humidity_supports_regional_reading"
    elif rh_status == SPATIAL_CONTRADICTED and temp_status == SPATIAL_CONTRADICTED:
        corroboration = "humidity_supports_local_reading"
    return {
        "base_decision": base_state,
        "contextual_decision": contextual,
        "spatial_influence": influence,
        "spatial_status": temp_status,
        "humidity_status": rh_status,
        "humidity_corroboration": corroboration,
    }


def describe(decision: dict) -> str:
    """One honest sentence for display (no probability language)."""
    contextual = decision.get("contextual_decision", INSUFFICIENT_EVIDENCE)
    if contextual == LOCAL_SENSOR_ANOMALY:
        return ("Target disagrees with nearby stations: local sensor "
                "anomaly is the supported reading.")
    if contextual == POSSIBLE_REGIONAL_EVENT:
        return ("Nearby stations show similar behavior: possible "
                "regional event — the anomaly flag is preserved.")
    if contextual == ANOMALY_WITHOUT_SPATIAL_CONFIRMATION:
        return ("No usable neighbor confirmation: anomaly stands "
                "without spatial confirmation.")
    if contextual == NORMAL:
        return "Base detector did not flag this observation."
    return "Insufficient evidence for a contextual interpretation."

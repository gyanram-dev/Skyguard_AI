"""Live inference through the existing SkyGuard machinery (no new detector).

One observation at a time, causal history only:

- DQ .............. ``prepare_split`` (frozen rules, same as batch/upload)
- statistical ..... ``build_statistical_baseline`` (frozen Z/IQR rules)
- multivariate .... canonical Phase 3 deviation features
- pattern ......... transparent heuristic estimator (shared with upload)
- spatial ......... Go 2 ``decide_context`` over live neighbors when any
  are co-temporal, else honestly UNAVAILABLE

Delhi/Jena Isolation Forest, LSTM, calibrated ensemble and the trained
root-cause classifier are NOT applied to live IMD stations: those
artifacts are validated only for their training stations. The LSTM
stays unavailable until ``WARM_ROWS_LSTM`` rows exist — and even then
is reported unavailable for unvalidated stations rather than run.
"""

from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from src.api.services import upload_analysis as UA
from src.baseline.statistical_baseline import build_statistical_baseline
from src.detection import freeze as FE
from src.baseline.zscore_baseline import Z_THRESHOLD
from src.isolation_forest.evaluator import prepare_split
from src.live import history as LH
from src.live import obs as LO
from src.spatial import decision as SD

logger = logging.getLogger("skyguard.live_inference")

SPATIAL_TOLERANCE_MIN = 30.0


def _neighbor_values(target_ts, histories: dict, station_id: str,
                     variable: str) -> dict:
    """Latest live-neighbor values at/before the target (30-min stale cap)."""
    out: dict = {}
    for nid, hist in histories.items():
        if nid == station_id:
            continue
        best = None
        for ob in hist._rows:
            if ob.timestamp <= target_ts:
                best = ob
            else:
                break
        value = getattr(best, variable, None) if best is not None else None
        if best is not None and (target_ts - best.timestamp).total_seconds() \
                > SPATIAL_TOLERANCE_MIN * 60.0:
            value = None
        try:
            number = float(value) if value is not None else None
        except (TypeError, ValueError):
            number = None
        out[nid] = (None if number is None or not np.isfinite(number) else number)
    return out


def score_station(history: LH.StationHistory, histories: dict,
                  cadence_min: float) -> dict:
    """Score the newest buffered observation (shared frozen machinery)."""
    started = time.perf_counter()
    latest = history.latest()
    warm = history.warm_state()
    if latest is None:
        return {"verdict": LO.WARMING_UP, "inference_ms": 0.0}
    frame = history.frame()
    features, quality = prepare_split(frame, "delhi", float(cadence_min))
    pos = len(frame) - 1
    dq_status = str(quality["quality_status"].iloc[pos])
    eligible = bool(int(quality["ml_eligible"].iloc[pos]))
    dq_reason = str(quality["quality_reason"].iloc[pos])
    if warm != LO.VALID:
        return {
            "verdict": warm, "timestamp": latest.timestamp.isoformat(),
            "observations": {"temperature_c": latest.temperature_c,
                             "pressure_hpa": latest.pressure_hpa,
                             "relative_humidity_pct":
                                 latest.relative_humidity_pct},
            "data_quality": {"status": dq_status, "ml_eligible": eligible,
                             "reason": dq_reason},
            "base_decision": SD.BASE_INSUFFICIENT,
            "anomaly_score": None,
            "spatial_decision": _unavailable_spatial(),
            "pattern": None,
            "explanation": ("Warming up: collecting causal history before "
                            "any anomaly verdict."),
            "ml_models": {"available": False, "reason": _ml_reason()},
            "inference_ms": round((time.perf_counter() - started) * 1000.0, 2),
        }
    baseline, _ = build_statistical_baseline(features, quality, "delhi",
                                             cadence_min=float(cadence_min))
    flag = baseline["statistical_baseline_flag"].iloc[pos]
    flagged = bool(eligible and pd.notna(flag) and float(flag) == 1.0)
    z_cols = ["temperature_zscore_baseline", "pressure_zscore_baseline",
              "humidity_zscore_baseline"]
    z_mat = np.stack([pd.to_numeric(baseline[c], errors="coerce")
                      .to_numpy(dtype=float) for c in z_cols], axis=1)
    finite_z = z_mat[pos][np.isfinite(z_mat[pos])]
    zmax = float(np.abs(finite_z).max()) if len(finite_z) else None
    feat = features.iloc[pos]
    freeze_flag = "possible_freeze" in str(quality["quality_reason"].iloc[pos])
    estimate, reason = UA._estimate_pattern(feat, freeze_flag)
    gap_arr = (quality["communication_gap"].to_numpy()
               if "communication_gap" in quality.columns else None)
    if FE.applicable(float(cadence_min)):
        freeze_run_rows, freeze_var_code = FE.scan_frame(frame, gap_rows=gap_arr)
    else:
        # Slow, coarsely quantized cadence: no fast-rule confirmations.
        freeze_run_rows = np.zeros(len(frame), dtype=int)
        freeze_var_code = np.zeros(len(frame), dtype=np.int8)
    freeze = FE.row_evidence(freeze_run_rows, freeze_var_code, pos,
                             float(cadence_min))
    freeze_confirmed = bool(eligible and freeze["confirmed"])
    if freeze_confirmed:
        estimate = "FROZEN"
        reason = FE.reason_text(freeze, float(cadence_min))
    if flagged or freeze_confirmed:
        base, verdict = SD.BASE_ANOMALOUS, "ANOMALY"
    elif zmax is None or not eligible:
        # No measurable statistical evidence: honestly insufficient,
        # never a clean bill of health (Go 1 evidence rule).
        base, verdict = SD.BASE_INSUFFICIENT, "INSUFFICIENT_EVIDENCE"
    else:
        base, verdict = SD.BASE_NORMAL, "NORMAL"
    temp_vals = _neighbor_values(latest.timestamp, histories,
                                 history.station_id, "temperature_c")
    rh_vals = _neighbor_values(latest.timestamp, histories,
                               history.station_id, "relative_humidity_pct")
    pres_vals = _neighbor_values(latest.timestamp, histories,
                                 history.station_id, "pressure_hpa")
    n_live = sum(1 for v in temp_vals.values() if v is not None)
    expected = max(len(temp_vals), 0)
    temp_ev = SD.variable_evidence(latest.temperature_c, temp_vals, expected)
    rh_ev = SD.variable_evidence(latest.relative_humidity_pct, rh_vals, expected) \
        if latest.relative_humidity_pct is not None \
        else SD.variable_evidence(None, {}, expected)
    pres_ev = SD.variable_evidence(latest.pressure_hpa, pres_vals, expected,
                                   pressure_compatible=True) \
        if latest.pressure_hpa is not None \
        else SD.variable_evidence(None, {}, expected)
    # Live IMD pressures share the station-level basis among live
    # stations (never altimeter); mark the basis explicitly.
    pres_ev["basis"] = "station_level"
    spatial = SD.decide_context(base, temp_ev, rh_ev)
    spatial["description"] = SD.describe(spatial)
    spatial["variables"] = {"temperature": temp_ev, "humidity": rh_ev,
                            "pressure": pres_ev}
    spatial["live_neighbor_count"] = int(n_live)
    multi = _finite(feat.get("multivariate_max_abs_robust_deviation_2h"))
    zmax_text = f"{zmax:.2f}" if zmax is not None else "unavailable"
    if freeze_confirmed:
        explanation = (f"{reason} max|z|={zmax_text} vs {Z_THRESHOLD}. "
                       f"{spatial['description']}")
    else:
        explanation = (f"Heuristic pattern estimate ({estimate}): {reason}; "
                       f"max|z|={zmax_text} vs {Z_THRESHOLD}. "
                       f"{spatial['description']}")
    return {
        "verdict": verdict,
        "timestamp": latest.timestamp.isoformat(),
        "observations": {"temperature_c": latest.temperature_c,
                         "pressure_hpa": latest.pressure_hpa,
                         "relative_humidity_pct": latest.relative_humidity_pct},
        "data_quality": {"status": dq_status, "ml_eligible": eligible,
                         "reason": dq_reason},
        "base_decision": base,
        "anomaly_score": round(zmax, 4) if zmax is not None else None,
        "score_threshold": Z_THRESHOLD,
        "statistical": {"max_abs_z": zmax, "threshold": Z_THRESHOLD,
                        "reason": str(
                            baseline["statistical_baseline_reason"].iloc[pos])},
        "multivariate": {"max_abs_robust_deviation_2h": multi},
        "spatial_decision": spatial,
        "freeze": freeze,
        "trigger": ("statistical+freeze" if flagged and freeze_confirmed
                    else "freeze" if freeze_confirmed
                    else "statistical" if flagged else None),
        "pattern": {"estimate": estimate, "reason": reason},
        "explanation": explanation,
        "ml_models": {"available": False, "reason": _ml_reason()},
        "inference_ms": round((time.perf_counter() - started) * 1000.0, 2),
    }


def _unavailable_spatial() -> dict:
    empty = SD.variable_evidence(None, {}, 0)
    decision = SD.decide_context(SD.BASE_INSUFFICIENT, empty)
    decision["description"] = SD.describe(decision)
    return decision


def _ml_reason() -> str:
    return ("Delhi/Jena-trained detectors are not validated for live "
            "stations; statistical + DQ + multivariate evidence only.")


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(number) else number

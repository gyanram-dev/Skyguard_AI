"""Shared single-row inference core: REST probe, replay, and future entries.

One implementation of per-observation scoring through the frozen pipeline
(Steps 4-14 reuse inventory):

- features/quality ... src.isolation_forest.evaluator.prepare_split
- statistical ......... src.baseline.statistical_baseline.build_statistical_baseline
- ECDF/calibration .... src.ensemble.calibration + src.ensemble.aggregation
- isolation forest .... frozen joblib model + frozen train ECDF + schema guard
- LSTM ................ frozen scaler + keras model, causal 12-step lookback
- root cause .......... frozen RF + frozen UNKNOWN/MIXED rules
- SHAP ................ frozen TreeExplainer on the scored row only
- spatial ............. anchor-timestamp NOAA medians (historical context only)

Callers (probe service, replay engine) build their own sensor frames and
assemble their own responses. This module never touches the network,
never retrains, never invents history.
"""

from __future__ import annotations

import logging
import math
import re
import threading

import joblib
import numpy as np
import pandas as pd

from src.baseline.statistical_baseline import build_statistical_baseline
from src.ensemble import aggregation as G
from src.ensemble import calibration as C
from src.isolation_forest.evaluator import prepare_split
from src.isolation_forest.features import to_model_matrix
from src.isolation_forest.scoring import raw_scores as if_raw_scores
from src.lstm_autoencoder.scoring import reconstruction_errors
from src.lstm_autoencoder.sequences import prepare_frame, valid_sequence_mask
from src.root_cause import confidence as CF
from src.root_cause import explain as EX
from src.root_cause.classifier import predict_proba
from src.root_cause.features import DIAGNOSTIC_FEATURES, build_evidence_frame
from src.root_cause.unknown_mixed import decide

logger = logging.getLogger("skyguard.scoring")

DATA_MODE = "historical_replay"

CONFIDENCE_BY_AVAILABILITY = {
    "FULL_EVIDENCE": 1.0,
    "PARTIAL_EVIDENCE": 0.67,
    "LOW_CONTEXT": 0.33,
    "INSUFFICIENT_EVIDENCE": None,
}

_BAD_TEXT = re.compile(r"\bnan\b|\bNone\b|\binf\b", re.IGNORECASE)

_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_NOAA_LOOKUP: dict | None = None


def num(value) -> float | None:
    """Finite float or None (missing stays missing, never zero-filled)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def sanitize_text(text: str | None, fallback: str) -> str:
    """Never leak nan/None/inf literals into user-facing explanation text."""
    if not text or not str(text).strip() or _BAD_TEXT.search(str(text)):
        return fallback
    return str(text)


def get_models(store, ds: str) -> dict:
    """Lazily load (once) and cache the frozen artifacts for a dataset."""
    with _CACHE_LOCK:
        if ds in _CACHE:
            return _CACHE[ds]
        root = store.root
        if_bundle = joblib.load(root / "models" / "isolation_forest" / f"{ds}_isolation_forest.joblib")
        cal_bundle = joblib.load(root / "models" / "ensemble" / f"{ds}_calibration.joblib")
        scaler_bundle = joblib.load(root / "models" / "lstm_autoencoder" / f"{ds}_scaler.joblib")
        import tensorflow as tf

        lstm_model = tf.keras.models.load_model(
            root / "models" / "lstm_autoencoder" / f"{ds}_lstm_autoencoder.keras")
        rc_model = joblib.load(root / "models" / "root_cause" / f"{ds}_root_cause.joblib")
        explainer = joblib.load(root / "models" / "root_cause" / f"{ds}_root_cause_explainer.joblib")
        bundle = {"if": if_bundle, "cal": cal_bundle, "scaler": scaler_bundle,
                  "lstm": lstm_model, "rc": rc_model, "explainer": explainer}
        _CACHE[ds] = bundle
        logger.info("Scoring models cached for dataset '%s'", ds)
        return bundle


def noaa_lookup(store) -> dict:
    """Anchor IST timestamp -> historical NOAA context (Delhi only)."""
    global _NOAA_LOOKUP
    if _NOAA_LOOKUP is not None:
        return _NOAA_LOOKUP
    out: dict = {}
    path = store.root / "reports" / "noaa" / "aws_context_validation.csv"
    if path.is_file():
        ctx = pd.read_csv(path, usecols=["timestamp_ist", "ctx_temp_median",
                                         "ctx_temp_station_count", "ctx_temp_context"])
        for _, row in ctx.iterrows():
            try:
                count = int(row["ctx_temp_station_count"])
                median = float(row["ctx_temp_median"])
            except (TypeError, ValueError):
                continue
            if count <= 0 or math.isnan(median):
                continue
            out[str(row["timestamp_ist"])] = {
                "median": median, "count": count,
                "context": str(row["ctx_temp_context"])}
    _NOAA_LOOKUP = out
    return out


def build_frames(store, ds: str, sensor_frame: pd.DataFrame) -> dict:
    """Score-ready frames for a causal sensor frame (history + targets).

    sensor_frame needs timestamp/temperature_c/pressure_hpa/
    relative_humidity_pct columns; label columns, when present, are never
    selected (prepare_split builds from sensor values only).
    """
    models = get_models(store, ds)
    features, quality = prepare_split(sensor_frame, ds)
    baseline, _ = build_statistical_baseline(features, quality, ds)
    z_raw_all, _ = C.z_evidence(baseline)
    iqr_raw_all, _ = C.iqr_evidence(baseline)
    if_bundle = models["if"]
    if list(features.columns) != list(if_bundle["_feature_schema"]):
        raise RuntimeError("Feature schema drift versus frozen Isolation Forest artifact.")
    X, scorable = to_model_matrix(features, if_bundle["allowlist"])
    lstm_bundle = models["scaler"]
    mat, segments, eligible, finite = prepare_frame(
        features, quality, list(lstm_bundle["feature_order"]))
    scaled = lstm_bundle["scaler"].transform(mat)
    valid = valid_sequence_mask(segments, eligible, finite)
    return {"models": models, "features": features, "quality": quality,
            "z_raw_all": z_raw_all, "iqr_raw_all": iqr_raw_all,
            "if_X": X, "if_scorable": scorable,
            "lstm_scaled": scaled, "lstm_valid": valid,
            "cal": models["cal"]["ecdf"], "thresholds": models["cal"]["thresholds"],
            "noaa": noaa_lookup(store) if ds == "delhi" else {}}


def score_position(frames: dict, ds: str, pos: int, *,
                   spatial_ts: str | None = None,
                   spatial_temp: float | None = None) -> dict:
    """Score one frame position through every detector + diagnosis.

    Returns evidence, ensemble verdict, root cause, explanation, DQ, and
    spatial context. Never raises for missing evidence: unavailable
    components stay missing and the ensemble availability policy decides.
    """
    models = frames["models"]
    features = frames["features"]
    quality = frames["quality"]
    cal = frames["cal"]
    thresholds = frames["thresholds"]
    feat = features.iloc[pos]

    dq_status = str(quality["quality_status"].iloc[pos])
    ml_eligible = bool(int(quality["ml_eligible"].iloc[pos]))
    dq_reason = str(quality["quality_reason"].iloc[pos])
    obs = {"temperature_c": num(feat.get("temperature_c")),
           "pressure_hpa": num(feat.get("pressure_hpa")),
           "relative_humidity_pct": num(feat.get("relative_humidity_pct"))}

    z_raw = num(frames["z_raw_all"][pos])
    iqr_raw = num(frames["iqr_raw_all"][pos])
    z_cal = num(C.calibrate(np.array([np.nan if z_raw is None else z_raw]), cal["z"])[0])
    iqr_cal = num(C.calibrate(np.array([np.nan if iqr_raw is None else iqr_raw]),
                              cal["iqr"])[0])
    stat_vals = [v for v in (z_cal, iqr_cal) if v is not None]
    stat_cal = float(sum(stat_vals) / len(stat_vals)) if stat_vals else None
    stat_ok = len(stat_vals) > 0

    if_bundle = models["if"]
    scorable = frames["if_scorable"]
    if_raw = num(if_raw_scores(if_bundle["model"], frames["if_X"][pos:pos + 1])[0]) \
        if bool(scorable[pos]) else None
    if_cal = num(C.calibrate(
        np.array([np.nan if if_raw is None else if_raw]),
        np.asarray(if_bundle["train_raw_sorted"], dtype=float))[0]) \
        if if_raw is not None else None
    if_ok = if_raw is not None

    lstm_raw: float | None = None
    lstm_full: float | None = None
    if bool(frames["lstm_valid"][pos]):
        X_seq = frames["lstm_scaled"][pos - 11:pos + 1][None, :, :].astype(np.float32)
        X_hat = models["lstm"].predict(X_seq, verbose=0)
        t_mse, f_mse = reconstruction_errors(X_seq, X_hat)
        lstm_raw, lstm_full = num(t_mse[0]), num(f_mse[0])
    lstm_cal = num(C.calibrate(
        np.array([np.nan if lstm_raw is None else lstm_raw]), cal["lstm"])[0]) \
        if lstm_raw is not None else None
    lstm_ok = lstm_raw is not None

    comp = np.array([[np.nan if stat_cal is None else stat_cal,
                      np.nan if if_cal is None else if_cal,
                      np.nan if lstm_cal is None else lstm_cal]], dtype=float)
    ens_mean, ens_median, avail = G.combine(comp)
    availability = str(avail[0])
    anomaly_score = num(ens_median[0])
    threshold = num(thresholds.get("ens_median"))
    is_anomalous = bool(ml_eligible and anomaly_score is not None
                        and threshold is not None and anomaly_score >= threshold)
    n_comp = int(stat_ok) + int(if_ok) + int(lstm_ok)

    rc_class: str | None = None
    rc_conf: float | None = None
    rc_runner: str | None = None
    explanation_text: str | None = None
    explanation_features: list = []
    if is_anomalous:
        evidence_row = {
            "z_maxabs": np.nan if z_raw is None else z_raw,
            "iqr_combined": np.nan if iqr_raw is None else iqr_raw,
            "if_raw": np.nan if if_raw is None else if_raw,
            "if_cal": np.nan if if_cal is None else if_cal,
            "lstm_target_mse": np.nan if lstm_raw is None else lstm_raw,
            "lstm_full_mse": np.nan if lstm_full is None else lstm_full,
            "ens_mean": num(ens_mean[0]),
            "ens_median": anomaly_score,
            "n_components_available": n_comp,
            "ml_eligible": int(ml_eligible),
        }
        for col in DIAGNOSTIC_FEATURES:
            if col not in evidence_row:
                evidence_row[col] = feat.get(col, np.nan)
        ev_frame, complete = build_evidence_frame(
            pd.DataFrame([evidence_row], columns=list(DIAGNOSTIC_FEATURES)))
        if bool(complete[0]):
            X_ev = ev_frame
            probas = predict_proba(models["rc"], X_ev)
            labels, conf, runner = decide(probas, list(models["rc"].classes_))
            rc_class, rc_conf = str(labels[0]), num(conf[0])
            rc_runner = str(runner[0]) if str(runner[0]) else None
            try:
                shap_values = models["explainer"].shap_values(X_ev)
                if isinstance(shap_values, list):
                    shap_values = np.stack(shap_values, axis=-1)
                shap_values = np.asarray(shap_values)
                argmax = int(np.argmax(probas[0]))
                cls_vals = shap_values[0, :, argmax] if shap_values.ndim == 3 \
                    else shap_values[0]
                top = EX.shap_top_features(
                    cls_vals, list(X_ev.columns),
                    X_ev.iloc[0].to_numpy(dtype=float))
                row_series = pd.Series({c: float(X_ev.iloc[0][c]) for c in X_ev.columns})
                noaa_text = ""
                info = frames["noaa"].get(str(spatial_ts)) if spatial_ts else None
                if info and spatial_temp is not None:
                    noaa_text = EX.noaa_sentence_for(
                        str(spatial_ts),
                        {str(spatial_ts): {"temp_diff": spatial_temp - info["median"],
                                           "n": info["count"]}})
                explanation_text = EX.compose_explanation(rc_class, row_series, top,
                                                          noaa_text)
                explanation_features = [
                    {"name": t["feature"], "value": num(t["feature_value"]),
                     "contribution": num(t["shap_value"]),
                     "direction": ("increases_anomaly"
                                   if "increases" in str(t["direction"])
                                   else "decreases_anomaly")}
                    for t in top
                ]
            except Exception as exc:  # noqa: BLE001 - honest degradation
                logger.warning("SHAP unavailable for scoring: %s", exc)
                explanation_text = None
                explanation_features = []
        else:
            rc_class = CF.UNKNOWN
    if is_anomalous and not explanation_text:
        explanation_text = ("Insufficient evidence for root-cause classification: "
                            "context too sparse to support a known class.")
    if not is_anomalous:
        explanation_text = ("Observation consistent with the station's historical context; "
                            "no fault pattern diagnosed. This is a model prediction, "
                            "not a confirmed physical diagnosis.")
    explanation_text = sanitize_text(explanation_text,
                                     "Explanation not available for this observation.")

    spatial: dict = {"available": False, "neighbor_count": 0}
    if ds == "delhi" and spatial_ts:
        info = frames["noaa"].get(str(spatial_ts))
        if info:
            spatial = {"available": True, "neighbor_count": info["count"],
                       "context": info["context"],
                       "reference_median": info["median"],
                       "probe_difference": num(spatial_temp - info["median"])
                       if spatial_temp is not None else None,
                       "note": "Historical NOAA context at the anchor timestamp; "
                               "not live neighboring sensors."}

    multivariate = {k: num(feat.get(k)) for k in
                    ("multivariate_max_abs_robust_deviation_2h",
                     "multivariate_deviation_range_2h")}
    return {
        "observations": obs,
        "data_quality": {"status": dq_status, "ml_eligible": ml_eligible,
                         "reason": dq_reason},
        "evidence": {
            "statistical": {"available": stat_ok, "raw": z_raw, "calibrated": stat_cal},
            "isolation_forest": {"available": if_ok, "raw": if_raw,
                                 "calibrated": if_cal},
            "lstm": {"available": lstm_ok, "raw": lstm_raw, "calibrated": lstm_cal},
            "multivariate": multivariate,
            "spatial": spatial,
        },
        "ensemble": {"mean": num(ens_mean[0]), "median": anomaly_score,
                     "availability": availability, "threshold": threshold,
                     "is_anomalous": is_anomalous,
                     "confidence": CONFIDENCE_BY_AVAILABILITY.get(availability),
                     "n_components": n_comp, "method": "ens_median"},
        "root_cause": {"class": rc_class, "confidence": rc_conf,
                       "runner_up": rc_runner},
        "explanation": {"text": explanation_text, "features": explanation_features},
    }

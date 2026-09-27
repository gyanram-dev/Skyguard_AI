"""Judge-probe orchestration: one observation through the frozen pipeline.

Thin layer over existing inference services (Steps 4-14 reuse, no
retraining, no new thresholds, no synthetic history):

- features/quality ... src.isolation_forest.evaluator.prepare_split
- statistical ......... src.baseline.statistical_baseline.build_statistical_baseline
- ECDF/calibration .... src.ensemble.calibration + src.ensemble.aggregation
- isolation forest .... frozen joblib model + frozen train ECDF
- LSTM ................ frozen scaler + keras model + frozen ECDF
- root cause .......... frozen RF + frozen UNKNOWN/MIXED rules
- SHAP ................ frozen TreeExplainer on THIS probe row
- spatial ............. anchor-timestamp NOAA medians (historical context only)

The probe observation is appended to the station's real trailing history
and evaluated against the selected station's available historical
context (replayed history, never described as live sensors).
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
from src.ensemble.aggregation import FULL_EVIDENCE
from src.features.feature_builder import CADENCE_HORIZONS
from src.isolation_forest.evaluator import prepare_split
from src.isolation_forest.features import to_model_matrix
from src.isolation_forest.scoring import raw_scores as if_raw_scores
from src.lstm_autoencoder.scoring import reconstruction_errors
from src.lstm_autoencoder.sequences import (
    build_sequences,
    prepare_frame,
    valid_sequence_mask,
)
from src.root_cause import confidence as CF
from src.root_cause import explain as EX
from src.root_cause.classifier import predict_proba
from src.root_cause.features import DIAGNOSTIC_FEATURES, build_evidence_frame
from src.root_cause.unknown_mixed import decide

logger = logging.getLogger("skyguard.probe")

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


class ProbeError(Exception):
    """Structured probe failure (status_code, code, detail)."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _sanitize_text(text: str | None, fallback: string) -> str:
    """Never leak nan/None/inf literals into user-facing explanation text."""
    if not text or not str(text).strip() or _BAD_TEXT.search(str(text)):
        return fallback
    return str(text)


def _get_models(store, ds: str) -> dict:
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
        logger.info("Probe models cached for dataset '%s'", ds)
        return bundle


def _noaa_lookup(store) -> dict:
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
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            try:
                median = float(row["ctx_temp_median"])
            except (TypeError, ValueError):
                continue
            if math.isnan(median):
                continue
            out[str(row["timestamp_ist"])] = {
                "median": median, "count": count,
                "context": str(row["ctx_temp_context"])}
    _NOAA_LOOKUP = out
    return out


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


def run_probe(store, station_id: str | None,
              temperature: float, pressure: float, humidity: float) -> dict:
    """Score one judge-supplied observation through the frozen pipeline."""
    temp_c, pres_hpa, hum_pct = _validate_inputs(temperature, pressure, humidity)

    if station_id is None:
        raise ProbeError(422, STATION_REQUIRED,
                         "A station is required: contextual inference needs "
                         "station history. No default station is assumed.")
    entry = next((m for m in store.mapping if m["frontend_station_id"] == station_id), None)
    if entry is None or not entry.get("backend_station_id"):
        raise ProbeError(404, UNKNOWN_STATION,
                         f"Station '{station_id}' is not available for probing.")
    backend_id = entry["backend_station_id"]
    if entry.get("source_dataset") == "noaa_ghcnh":
        raise ProbeError(422, INSUFFICIENT_CONTEXT,
                         f"Station '{station_id}' has contextual observations only; "
                         "no detector models cover it, so probe inference is unavailable.")
    ds = backend_id
    if ds not in ("jena", "delhi"):
        raise ProbeError(404, UNKNOWN_STATION,
                         f"Station '{station_id}' is not available for probing.")

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

    features, quality = prepare_split(frame, ds)
    pos = len(features) - 1
    segment = features["segment_id"].to_numpy()
    if segment[pos] != segment[pos - 1]:
        raise ProbeError(422, INSUFFICIENT_CONTEXT,
                         "Insufficient historical context for probe inference: "
                         "the probe does not continue the station's latest segment.")
    feat = features.iloc[pos]
    dq_status = str(quality["quality_status"].iloc[pos])
    ml_eligible = bool(int(quality["ml_eligible"].iloc[pos]))
    dq_reason = str(quality["quality_reason"].iloc[pos])

    models = _get_models(store, ds)
    cal = models["cal"]["ecdf"]
    thresholds = models["cal"]["thresholds"]

    # Statistical: same causal baselines, last-row evidence, frozen ECDFs.
    baseline, _ = build_statistical_baseline(features, quality, ds)
    z_raw_all, _ = C.z_evidence(baseline)
    iqr_raw_all, _ = C.iqr_evidence(baseline)
    z_raw = _num(z_raw_all[pos])
    iqr_raw = _num(iqr_raw_all[pos])
    z_cal = _num(C.calibrate(np.array([np.nan if z_raw is None else z_raw]),
                             cal["z"])[0])
    iqr_cal = _num(C.calibrate(np.array([np.nan if iqr_raw is None else iqr_raw]),
                               cal["iqr"])[0])
    stat_vals = [v for v in (z_cal, iqr_cal) if v is not None]
    stat_cal = float(sum(stat_vals) / len(stat_vals)) if stat_vals else None
    stat_ok = len(stat_vals) > 0

    # Isolation Forest: frozen allowlist, schema guard, frozen train ECDF.
    if_bundle = models["if"]
    if list(features.columns) != list(if_bundle["_feature_schema"]):
        raise ProbeError(500, "internal_error",
                         "Feature schema drift versus frozen Isolation Forest artifact.")
    X, scorable = to_model_matrix(features, if_bundle["allowlist"])
    if_raw = _num(if_raw_scores(if_bundle["model"], X[pos:pos + 1])[0]) \
        if bool(scorable[pos]) else None
    if_cal = _num(C.calibrate(
        np.array([np.nan if if_raw is None else if_raw]),
        np.asarray(if_bundle["train_raw_sorted"], dtype=float))[0]) \
        if if_raw is not None else None
    if_ok = if_raw is not None

    # LSTM: actual 12-step historical lookback + probe as final step.
    lstm_bundle = models["scaler"]
    mat, segments, eligible, finite = prepare_frame(
        features, quality, list(lstm_bundle["feature_order"]))
    scaled = lstm_bundle["scaler"].transform(mat)
    valid = valid_sequence_mask(segments, eligible, finite)
    lstm_raw: float | None = None
    lstm_full: float | None = None
    if bool(valid[pos]):
        X_seq = scaled[pos - 11:pos + 1][None, :, :].astype(np.float32)
        X_hat = models["lstm"].predict(X_seq, verbose=0)
        t_mse, f_mse = reconstruction_errors(X_seq, X_hat)
        lstm_raw, lstm_full = _num(t_mse[0]), _num(f_mse[0])
    lstm_cal = _num(C.calibrate(
        np.array([np.nan if lstm_raw is None else lstm_raw]), cal["lstm"])[0]) \
        if lstm_raw is not None else None
    lstm_ok = lstm_raw is not None

    # Calibrated ensemble: same combination + availability policy.
    comp = np.array([[np.nan if stat_cal is None else stat_cal,
                      np.nan if if_cal is None else if_cal,
                      np.nan if lstm_cal is None else lstm_cal]], dtype=float)
    ens_mean, ens_median, avail = G.combine(comp)
    availability = str(avail[0])
    anomaly_score = _num(ens_median[0])
    threshold = _num(thresholds.get("ens_median"))
    is_anomalous = bool(anomaly_score is not None and threshold is not None
                        and anomaly_score >= threshold)
    if availability == G.INSUFFICIENT_EVIDENCE:
        raise ProbeError(422, INSUFFICIENT_CONTEXT,
                         "Insufficient historical context for probe inference: "
                         "fewer than two detector components are available.")
    n_comp = int(stat_ok) + int(if_ok) + int(lstm_ok)

    # Root cause: gated on the ensemble flag (production parity), frozen rules.
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
            "ens_mean": _num(ens_mean[0]),
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
            rc_class, rc_conf = str(labels[0]), _num(conf[0])
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
                row_series = pd.Series({c: float(X_ev.iloc[0][c])
                                        for c in X_ev.columns})
                noaa_text = ""
                if ds == "delhi":
                    info = _noaa_lookup(store).get(anchor)
                    if info:
                        noaa_text = EX.noaa_sentence_for(
                            anchor,
                            {anchor: {"temp_diff": temp_c - info["median"],
                                      "n": info["count"]}})
                explanation_text = EX.compose_explanation(rc_class, row_series, top,
                                                          noaa_text)
                explanation_features = [
                    {"name": t["feature"], "value": _num(t["feature_value"]),
                     "contribution": _num(t["shap_value"]),
                     "direction": ("increases_anomaly"
                                   if "increases" in str(t["direction"])
                                   else "decreases_anomaly")}
                    for t in top
                ]
            except Exception as exc:  # noqa: BLE001 - honest degradation
                logger.warning("Probe SHAP unavailable: %s", exc)
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
    explanation_text = _sanitize_text(
        explanation_text, "Explanation not available for this probe.")

    # Spatial: anchor-timestamp historical context only (Delhi); never live.
    spatial: dict = {"available": False, "neighbor_count": 0}
    if ds == "delhi":
        info = _noaa_lookup(store).get(anchor)
        if info:
            spatial = {"available": True, "neighbor_count": info["count"],
                       "context": info["context"],
                       "reference_median": info["median"],
                       "probe_difference": _num(temp_c - info["median"]),
                       "note": "Historical NOAA context at the anchor timestamp; "
                               "not live neighboring sensors."}

    feat_row = {k: _num(feat.get(k)) for k in
                ("multivariate_max_abs_robust_deviation_2h",
                 "multivariate_deviation_range_2h")}
    return {
        "data_mode": DATA_MODE,
        "probe": {"station_id": station_id, "temperature": temp_c,
                  "pressure": pres_hpa, "humidity": hum_pct},
        "context": {
            "station_available": True,
            "historical_anchor": anchor,
            "spatial_available": bool(spatial["available"]),
            "neighbor_count": int(spatial.get("neighbor_count", 0)),
            "context_note": ("This probe evaluates the supplied observation against "
                             f"{station_id}'s available historical context anchored at "
                             f"{anchor}; replayed history, not live sensors."),
        },
        "result": {
            "is_anomalous": is_anomalous,
            "anomaly_score": anomaly_score,
            "confidence": CONFIDENCE_BY_AVAILABILITY.get(availability),
            "availability": availability,
            "threshold": threshold,
            "method": "ens_median",
        },
        "evidence": {
            "statistical": {"available": stat_ok, "raw": z_raw,
                            "calibrated": stat_cal},
            "isolation_forest": {"available": if_ok, "raw": if_raw,
                                 "calibrated": if_cal},
            "lstm": {"available": lstm_ok, "raw": lstm_raw,
                     "calibrated": lstm_cal},
            "multivariate": {k: v for k, v in feat_row.items()},
            "spatial": spatial,
            "data_quality": {"status": dq_status, "ml_eligible": ml_eligible,
                            "reason": dq_reason},
        },
        "root_cause": {"class": rc_class, "confidence": rc_conf,
                       "runner_up": rc_runner},
        "explanation": {"text": explanation_text,
                        "features": explanation_features},
    }

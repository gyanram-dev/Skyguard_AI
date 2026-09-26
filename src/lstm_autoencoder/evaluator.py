"""Phase 9 evaluation: clean-train LSTM, frozen threshold, injected tests.

Experiment: CLEAN TRAIN -> LSTM AE FIT -> CLEAN TRAIN THRESHOLD ->
INJECTED ID TEST -> INJECTED OOD TEST. Benchmark labels/manifests never
enter fitting, scaling, or thresholding; test splits supply injected
sensor values plus labels for measurement only.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.evaluation.statistical_baseline.metrics import confusion_counts, prf_metrics
from src.isolation_forest.evaluator import load_clean_train_frame, prepare_split
from src.lstm_autoencoder import model as M
from src.lstm_autoencoder import scoring as S
from src.lstm_autoencoder import training as T
from src.lstm_autoencoder.features import LSTM_FEATURES, validate_feature_schema
from src.lstm_autoencoder.sequences import (
    LOOKBACK,
    build_sequences,
    prepare_frame,
    valid_sequence_mask,
)
from src.lstm_autoencoder.threshold import THRESHOLD_METHOD, fit_threshold

logger = logging.getLogger("aws_lstm.evaluator")

METHOD = "lstm_ae"
FAULT_TYPES = ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT")


def train_pipeline(clean: pd.DataFrame, dataset: str) -> dict:
    """Fit scaler + autoencoder + threshold on clean rows. Return bundle."""
    from src.isolation_forest.features import assert_no_forbidden_columns

    assert_no_forbidden_columns(clean)
    features, quality = prepare_split(clean, dataset)
    feature_list = validate_feature_schema(list(features.columns))
    mat, segments, eligible, finite = prepare_frame(features, quality, feature_list)
    row_mask = eligible & finite
    scaler = T.fit_scaler(mat, row_mask)
    scaled = scaler.transform(mat)
    valid = valid_sequence_mask(segments, eligible, finite)
    X, positions = build_sequences(scaled, valid)
    if len(X) == 0:
        raise ValueError(f"No valid clean sequences for {dataset}")
    model, train_info = T.train_autoencoder(X)
    X_hat = model.predict(X, batch_size=1024, verbose=0)
    target_mse, _ = S.reconstruction_errors(X, X_hat)
    threshold, thresh_diag = fit_threshold(target_mse)
    logger.info("%s: %d sequences, threshold=%.6f", dataset, len(X), threshold)
    return {
        "model": model,
        "scaler": scaler,
        "feature_list": feature_list,
        "feature_schema": list(features.columns),
        "threshold": threshold,
        "threshold_diag": thresh_diag,
        "threshold_method": THRESHOLD_METHOD,
        "train_info": train_info,
        "n_clean_rows": int(len(features)),
        "n_eligible_finite_rows": int(row_mask.sum()),
        "n_train_sequences": int(len(X)),
        "train_start": str(clean["timestamp"].iloc[0]),
        "train_end": str(clean["timestamp"].iloc[-1]),
    }


def predict_split(bundle: dict, bench: pd.DataFrame, dataset: str, split: str) -> pd.DataFrame:
    """Score a benchmark split with frozen scaler/model/threshold."""
    features, quality = prepare_split(bench, dataset)
    if list(features.columns) != bundle["feature_schema"]:
        raise ValueError("Feature schema drift between train and evaluation")
    mat, segments, eligible, finite = prepare_frame(
        features, quality, bundle["feature_list"])
    scaler_ref = bundle["scaler"]
    if isinstance(scaler_ref, dict):
        if list(scaler_ref.get("feature_order", bundle["feature_list"])) != bundle["feature_list"]:
            raise ValueError("Scaler feature order mismatch")
        scaler_ref = scaler_ref["scaler"]
    scaled = scaler_ref.transform(mat)
    valid = valid_sequence_mask(segments, eligible, finite)
    X, positions = build_sequences(scaled, valid)
    target_mse = np.full(len(bench), np.nan)
    full_mse = np.full(len(bench), np.nan)
    if len(X):
        X_hat = bundle["model"].predict(X, batch_size=1024, verbose=0)
        t_mse, f_mse = S.reconstruction_errors(X, X_hat)
        target_mse[positions] = t_mse
        full_mse[positions] = f_mse
    flag = np.zeros(len(bench), dtype=int)
    scorable = valid & np.isfinite(target_mse)
    flag[scorable] = S.flag_scores(target_mse[scorable], bundle["threshold"])
    evaluation_eligible = (quality["ml_eligible"].to_numpy(dtype=int) == 1).astype(int)
    return pd.DataFrame({
        "timestamp": bench["timestamp"].astype(str).values,
        "source_dataset": dataset.lower(),
        "split": split,
        "temperature_c": pd.to_numeric(bench["temperature_c"], errors="coerce").values,
        "pressure_hpa": pd.to_numeric(bench["pressure_hpa"], errors="coerce").values,
        "relative_humidity_pct": pd.to_numeric(bench["relative_humidity_pct"], errors="coerce").values,
        "lstm_full_mse": full_mse,
        "lstm_target_mse": target_mse,
        "lstm_anomaly_flag": flag,
        "scorable": scorable.astype(int),
        "ground_truth_anomaly": bench["ground_truth_anomaly"].to_numpy(dtype=int),
        "ground_truth_fault_type": bench["ground_truth_fault_type"].astype(str).values,
        "injection_id": bench["injection_id"].astype(str).values,
        "evaluation_eligible": evaluation_eligible,
        "data_quality_status": quality["quality_status"].astype(str).values,
    })


def summarize_rows(rows: pd.DataFrame, dataset: str, split: str,
                   event_labels: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Row/event/variable/FP summaries; SPIKE_PLUS_DRIFT never merged."""
    FLAG = "lstm_anomaly_flag"
    summary: list[dict] = []
    el = rows[rows["evaluation_eligible"] == 1]
    y_true = el["ground_truth_anomaly"].to_numpy(dtype=int)
    y_pred = el[FLAG].to_numpy(dtype=int)
    cc = confusion_counts(y_true, y_pred)
    summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": "overall",
                    "group": "all", **cc, **prf_metrics(cc["tp"], cc["fp"], cc["tn"], cc["fn"]),
                    "eligible_rows": int(len(el))})
    for fault in FAULT_TYPES:
        sub = el[el["ground_truth_fault_type"] == fault]
        if len(sub) == 0:
            summary.append({"dataset": dataset, "split": split, "method": METHOD,
                            "scope": "fault_type", "group": fault, "injected_rows": 0,
                            "note": "absent_in_split"})
            continue
        injected = int((sub["ground_truth_anomaly"] == 1).sum())
        cc2 = confusion_counts(sub["ground_truth_anomaly"].tolist(), sub[FLAG].tolist())
        summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": "fault_type",
                        "group": fault, "injected_rows": injected, **cc2,
                        **prf_metrics(cc2["tp"], cc2["fp"], cc2["tn"], cc2["fn"]),
                        "eligible_rows": int(len(sub))})
    faults = event_labels[(event_labels["split"] == split)
                          & (event_labels["fault_type"].isin(("SPIKE", "FROZEN", "DRIFT")))]
    target_of = dict(zip(faults["injection_id"].astype(str), faults["target_variable"].astype(str)))
    tmp = el.copy()
    tmp["event_target"] = tmp["injection_id"].map(target_of)
    for var in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
        sub = tmp[(tmp["ground_truth_anomaly"] == 1) & (tmp["event_target"] == var)]
        injected = int(len(sub))
        detected = int((sub[FLAG] == 1).sum())
        summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": "variable",
                        "group": var, "injected_rows": injected, "detected_rows": detected,
                        "missed_rows": injected - detected,
                        "recall": (detected / injected) if injected else float("nan")})
    events = build_event_frame(rows, event_labels, dataset, split)
    for scope_rows, scope in (([("all", events)], "event"),
                              ([(f, events[events["fault_type"] == f])
                                for f in events["fault_type"].unique()], "event_by_fault")):
        for group, sub in scope_rows:
            det = sub["detected"].to_numpy(dtype=int)
            lat = sub["latency_minutes"].to_numpy(dtype=float)
            ok = lat[~np.isnan(lat)]
            summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": scope,
                            "group": str(group), "events": int(len(sub)),
                            "events_detected": int(det.sum()),
                            "event_recall": float(det.mean()) if len(det) else float("nan"),
                            "latency_median_min": float(np.median(ok)) if len(ok) else float("nan"),
                            "latency_mean_min": float(np.mean(ok)) if len(ok) else float("nan")})
    bg = el[el["ground_truth_anomaly"] == 0]
    fp = int((bg[FLAG] == 1).sum())
    total = int(len(bg))
    summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": "false_positive",
                    "group": "background", "background_rows": total, "false_positive_count": fp,
                    "background_flag_rate": (fp / total) if total else float("nan"),
                    "fp_per_10k": (fp / total * 10000.0) if total else float("nan")})
    return summary, events


def build_event_frame(rows: pd.DataFrame, event_labels: pd.DataFrame,
                      dataset: str, split: str) -> pd.DataFrame:
    """Per-event detection, first flag, latency, coverage (gaps excluded)."""
    faults = event_labels[(event_labels["split"] == split)
                          & (event_labels["fault_type"] != "COMMUNICATION_GAP")].reset_index(drop=True)
    out: list[dict] = []
    for _, event in faults.iterrows():
        sub = rows[rows["injection_id"] == event["injection_id"]].sort_values("timestamp")
        flagged = sub[sub["lstm_anomaly_flag"] == 1]
        detected = len(flagged) > 0
        rec: dict = {
            "source_dataset": dataset.lower(), "split": split,
            "injection_id": event["injection_id"], "fault_type": event["fault_type"],
            "target_variable": event["target_variable"],
            "start_timestamp": event["start_timestamp"], "end_timestamp": event["end_timestamp"],
            "duration_minutes": float(event["duration_minutes"]),
            "injected_row_count": int(len(sub)),
            "detected": int(detected),
            "detected_row_count": int(len(flagged)),
            "row_coverage": (len(flagged) / len(sub)) if len(sub) else float("nan"),
        }
        if detected:
            first = pd.Timestamp(flagged["timestamp"].iloc[0])
            rec["first_detection_timestamp"] = str(flagged["timestamp"].iloc[0])
            rec["latency_minutes"] = (first - pd.Timestamp(event["start_timestamp"])).total_seconds() / 60.0
        else:
            rec["first_detection_timestamp"] = None
            rec["latency_minutes"] = float("nan")
        out.append(rec)
    cols = ["source_dataset", "split", "injection_id", "fault_type", "target_variable",
            "start_timestamp", "end_timestamp", "duration_minutes", "injected_row_count",
            "detected", "detected_row_count", "row_coverage",
            "first_detection_timestamp", "latency_minutes"]
    return pd.DataFrame(out, columns=cols)

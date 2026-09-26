"""Phase 10 evaluation: clean-train calibration, frozen ensemble, measurement.

Calibration and thresholds use clean-training component scores only.
Benchmark labels enter solely through frozen evaluation metrics.
Frozen models are scored, never retrained.
"""

from __future__ import annotations

import logging

import joblib
import numpy as np
import pandas as pd

from src.ensemble import aggregation as G
from src.ensemble import calibration as C
from src.ensemble.threshold import THRESHOLD_METHOD, fit_threshold
from src.evaluation.statistical_baseline.metrics import confusion_counts, prf_metrics
from src.isolation_forest.evaluator import load_clean_train_frame, prepare_split
from src.isolation_forest.features import to_model_matrix
from src.isolation_forest.scoring import raw_scores as if_raw_scores

logger = logging.getLogger("aws_ensemble.evaluator")

METHODS = ("ens_mean", "ens_median", "diag_mean", "diag_median")
FAULT_TYPES = ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT")


def clean_component_frame(dataset: str, project_root: str = ".") -> pd.DataFrame:
    """Per-row component scores on clean training rows (frozen models only)."""
    from pathlib import Path

    from src.lstm_autoencoder.sequences import (
        build_sequences,
        prepare_frame,
        valid_sequence_mask,
    )
    from src.lstm_autoencoder.scoring import reconstruction_errors

    root = Path(project_root)
    ds = dataset.lower()
    clean = load_clean_train_frame(ds, root)
    features, quality = prepare_split(clean, ds)

    base = pd.read_csv(root / "data" / "baseline" / f"{ds}_statistical_baseline.csv",
                       usecols=["timestamp", "temperature_zscore_baseline",
                                "pressure_zscore_baseline", "humidity_zscore_baseline",
                                "temperature_iqr_flag", "pressure_iqr_flag",
                                "humidity_iqr_flag"])
    base = base.rename(columns={"temperature_zscore_baseline": "temperature_zscore",
                                "pressure_zscore_baseline": "pressure_zscore",
                                "humidity_zscore_baseline": "humidity_zscore"})
    merged = pd.merge(clean[["timestamp"]], base, on="timestamp", how="left",
                      validate="one_to_one", indicator=True)
    unmatched = merged[merged["_merge"] == "left_only"]
    if len(unmatched):
        raise ValueError(f"{ds}: {len(unmatched)} clean-train rows lack baseline scores")
    merged = merged.drop(columns=["_merge"])
    z_raw, z_avail = C.z_evidence(merged)
    iqr_raw, iqr_avail = C.iqr_evidence(merged)

    artifact = joblib.load(root / "models" / "isolation_forest" / f"{ds}_isolation_forest.joblib")
    if list(features.columns) != list(artifact["_feature_schema"]):
        raise ValueError("Feature schema drift versus frozen IF artifact")
    X, scorable = to_model_matrix(features, artifact["allowlist"])
    if_raw = np.full(len(features), np.nan)
    if_raw[scorable] = if_raw_scores(artifact["model"], X[scorable])
    stored = np.asarray(artifact["train_raw_sorted"], dtype=float)
    for q in (0.5, 0.9, 0.99):
        if abs(float(np.quantile(if_raw[scorable], q)) - float(np.quantile(stored, q))) > 1e-6:
            raise ValueError(f"{ds}: recomputed IF scores diverge from frozen artifact at q={q}")

    lstm_bundle = joblib.load(root / "models" / "lstm_autoencoder" / f"{ds}_scaler.joblib")
    import tensorflow as tf

    lstm_model = tf.keras.models.load_model(
        root / "models" / "lstm_autoencoder" / f"{ds}_lstm_autoencoder.keras")
    mat, segments, eligible, finite = prepare_frame(
        features, quality, list(lstm_bundle["feature_order"]))
    scaled = lstm_bundle["scaler"].transform(mat)
    valid = valid_sequence_mask(segments, eligible, finite)
    X_seq, positions = build_sequences(scaled, valid)
    lstm_raw = np.full(len(features), np.nan)
    if len(X_seq):
        X_hat = lstm_model.predict(X_seq, batch_size=1024, verbose=0)
        t_mse, _ = reconstruction_errors(X_seq, X_hat)
        lstm_raw[positions] = t_mse

    return pd.DataFrame({
        "timestamp": clean["timestamp"].astype(str).values,
        "z_raw": z_raw, "z_available": z_avail.astype(int),
        "iqr_raw": iqr_raw, "iqr_available": iqr_avail.astype(int),
        "if_raw": if_raw, "if_available": scorable.astype(int),
        "lstm_raw": lstm_raw, "lstm_available": valid.astype(int),
        "eligible": (quality["ml_eligible"].to_numpy(dtype=int) == 1).astype(int),
    })


def fit_calibration(train: pd.DataFrame) -> dict:
    """Freeze ECDFs on clean-train scores; no labels involved."""
    cal = {}
    for key in ("z", "iqr", "if", "lstm"):
        raw = train[f"{key}_raw"].to_numpy(dtype=float)
        cal[key] = C.fit_ecdf(raw)
    return cal


def apply_calibration(frame: pd.DataFrame, cal: dict) -> pd.DataFrame:
    """Calibrate raw component scores with frozen ECDFs (NaN stays NaN)."""
    out = frame.copy()
    for key in ("z", "iqr", "if", "lstm"):
        out[f"{key}_cal"] = C.calibrate(frame[f"{key}_raw"].to_numpy(dtype=float), cal[key])
    stat_cal, stat_n = G.statistical_component(out["z_cal"].to_numpy(dtype=float),
                                               out["iqr_cal"].to_numpy(dtype=float))
    out["stat_cal"] = stat_cal
    comp = np.stack([out["stat_cal"].to_numpy(dtype=float),
                     out["if_cal"].to_numpy(dtype=float),
                     out["lstm_cal"].to_numpy(dtype=float)], axis=1)
    mean, median, avail = G.combine(comp)
    out["ens_mean"], out["ens_median"], out["availability"] = mean, median, avail
    diag = np.stack([out["z_cal"].to_numpy(dtype=float),
                     out["iqr_cal"].to_numpy(dtype=float),
                     out["if_cal"].to_numpy(dtype=float),
                     out["lstm_cal"].to_numpy(dtype=float)], axis=1)
    dmean, dmedian, _ = G.combine(diag)
    out["diag_mean"], out["diag_median"] = dmean, dmedian
    return out


def fit_thresholds(train_cal: pd.DataFrame) -> dict:
    """99th percentile of clean-train ensemble scores, per method."""
    thresholds = {}
    for key in ("ens_mean", "ens_median"):
        scores = train_cal[key].to_numpy(dtype=float)
        scores = scores[np.isfinite(scores)]
        thr, diag = fit_threshold(scores)
        thresholds[key] = {"value": thr, "diag": diag, "method": THRESHOLD_METHOD,
                           "n_scores": int(len(scores))}
    return thresholds


def load_eval_frame(dataset: str, split: str, project_root: str = ".") -> pd.DataFrame:
    """Join frozen ID/OOD component outputs on timestamp (no recomputation)."""
    from pathlib import Path

    root = Path(project_root)
    ds = dataset.lower()
    if_pred = pd.read_csv(root / "data" / "isolation_forest" / f"{ds}_isolation_forest_predictions.csv")
    lstm_pred = pd.read_csv(root / "data" / "lstm_autoencoder" / f"{ds}_lstm_predictions.csv")
    stat_eval = pd.read_csv(root / "data" / "evaluation" / "statistical_baseline"
                            / f"{ds}_{split}_results.csv")
    if_pred = if_pred[if_pred["split"] == split].reset_index(drop=True)
    lstm_pred = lstm_pred[lstm_pred["split"] == split].reset_index(drop=True)
    if not (if_pred["timestamp"].tolist() == lstm_pred["timestamp"].tolist()
            == stat_eval["timestamp"].astype(str).tolist()):
        raise ValueError(f"{ds}/{split}: frozen sources disagree on timestamps")
    if not (if_pred["ground_truth_anomaly"].tolist() == lstm_pred["ground_truth_anomaly"].tolist()
            == stat_eval["ground_truth_anomaly"].tolist()):
        raise ValueError(f"{ds}/{split}: frozen sources disagree on labels")
    z_raw, z_avail = C.z_evidence(stat_eval)
    iqr_raw, iqr_avail = C.iqr_evidence(stat_eval)
    if_raw = np.array(if_pred["if_raw_score"].to_numpy(dtype=float), copy=True)
    if_raw[if_pred["scorable"].to_numpy(dtype=int) == 0] = np.nan
    lstm_raw = np.array(lstm_pred["lstm_target_mse"].to_numpy(dtype=float), copy=True)
    lstm_raw[lstm_pred["scorable"].to_numpy(dtype=int) == 0] = np.nan
    return pd.DataFrame({
        "timestamp": if_pred["timestamp"].astype(str).values,
        "source_dataset": ds,
        "split": split,
        "temperature_c": if_pred["temperature_c"].values,
        "pressure_hpa": if_pred["pressure_hpa"].values,
        "relative_humidity_pct": if_pred["relative_humidity_pct"].values,
        "z_raw": z_raw, "z_available": z_avail.astype(int),
        "iqr_raw": iqr_raw, "iqr_available": iqr_avail.astype(int),
        "if_raw": if_raw,
        "if_available": if_pred["scorable"].to_numpy(dtype=int),
        "lstm_raw": lstm_raw,
        "lstm_available": lstm_pred["scorable"].to_numpy(dtype=int),
        "ground_truth_anomaly": if_pred["ground_truth_anomaly"].to_numpy(dtype=int),
        "ground_truth_fault_type": if_pred["ground_truth_fault_type"].astype(str).values,
        "injection_id": if_pred["injection_id"].astype(str).values,
        "evaluation_eligible": if_pred["evaluation_eligible"].to_numpy(dtype=int),
        "data_quality_status": if_pred["data_quality_status"].astype(str).values,
    })


def flag_frame(frame: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """Apply frozen thresholds to calibrated ensemble scores."""
    out = frame.copy()
    for key, flag in (("ens_mean", "ens_mean_flag"), ("ens_median", "ens_median_flag"),
                      ("diag_mean", "diag_mean_flag"), ("diag_median", "diag_median_flag")):
        scores = frame[key].to_numpy(dtype=float)
        method = key if key in thresholds else ("ens_mean" if "mean" in key else "ens_median")
        thr = thresholds[method]["value"]
        flags = np.zeros(len(frame), dtype=int)
        ok = np.isfinite(scores)
        flags[ok] = (scores[ok] >= thr).astype(int)
        out[flag] = flags
    return out


def summarize_rows(rows: pd.DataFrame, dataset: str, split: str,
                   event_labels: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Row/event/variable/FP summaries for every ensemble method."""
    summary: list[dict] = []
    flags = {"ens_mean": "ens_mean_flag", "ens_median": "ens_median_flag",
             "diag_mean": "diag_mean_flag", "diag_median": "diag_median_flag"}
    el = rows[rows["evaluation_eligible"] == 1]
    event_frames: list[pd.DataFrame] = []
    for method, flag_col in flags.items():
        y_true = el["ground_truth_anomaly"].to_numpy(dtype=int)
        y_pred = el[flag_col].to_numpy(dtype=int)
        cc = confusion_counts(y_true, y_pred)
        summary.append({"dataset": dataset, "split": split, "method": method, "scope": "overall",
                        "group": "all", **cc,
                        **prf_metrics(cc["tp"], cc["fp"], cc["tn"], cc["fn"]),
                        "eligible_rows": int(len(el))})
        for fault in FAULT_TYPES:
            sub = el[el["ground_truth_fault_type"] == fault]
            if len(sub) == 0:
                summary.append({"dataset": dataset, "split": split, "method": method,
                                "scope": "fault_type", "group": fault, "injected_rows": 0,
                                "note": "absent_in_split"})
                continue
            injected = int((sub["ground_truth_anomaly"] == 1).sum())
            cc2 = confusion_counts(sub["ground_truth_anomaly"].tolist(), sub[flag_col].tolist())
            summary.append({"dataset": dataset, "split": split, "method": method,
                            "scope": "fault_type", "group": fault, "injected_rows": injected,
                            **cc2, **prf_metrics(cc2["tp"], cc2["fp"], cc2["tn"], cc2["fn"]),
                            "eligible_rows": int(len(sub))})
        faults = event_labels[(event_labels["split"] == split)
                              & (event_labels["fault_type"].isin(("SPIKE", "FROZEN", "DRIFT")))]
        target_of = dict(zip(faults["injection_id"].astype(str),
                             faults["target_variable"].astype(str)))
        tmp = el.copy()
        tmp["event_target"] = tmp["injection_id"].map(target_of)
        for var in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
            sub = tmp[(tmp["ground_truth_anomaly"] == 1) & (tmp["event_target"] == var)]
            injected = int(len(sub))
            detected = int((sub[flag_col] == 1).sum())
            summary.append({"dataset": dataset, "split": split, "method": method,
                            "scope": "variable", "group": var, "injected_rows": injected,
                            "detected_rows": detected, "missed_rows": injected - detected,
                            "recall": (detected / injected) if injected else float("nan")})
        events = build_event_frame(rows, flag_col, event_labels, dataset, split)
        event_frames.append(events)
        for scope_rows, scope in (([("all", events)], "event"),
                                  ([(f, events[events["fault_type"] == f])
                                    for f in events["fault_type"].unique()], "event_by_fault")):
            for group, sub in scope_rows:
                det = sub["detected"].to_numpy(dtype=int)
                lat = sub["latency_minutes"].to_numpy(dtype=float)
                ok = lat[~np.isnan(lat)]
                summary.append({"dataset": dataset, "split": split, "method": method,
                                "scope": scope, "group": str(group),
                                "events": int(len(sub)),
                                "events_detected": int(det.sum()),
                                "event_recall": float(det.mean()) if len(det) else float("nan"),
                                "latency_median_min": float(np.median(ok)) if len(ok) else float("nan"),
                                "latency_mean_min": float(np.mean(ok)) if len(ok) else float("nan")})
        bg = el[el["ground_truth_anomaly"] == 0]
        fp = int((bg[flag_col] == 1).sum())
        total = int(len(bg))
        summary.append({"dataset": dataset, "split": split, "method": method,
                        "scope": "false_positive", "group": "background",
                        "background_rows": total, "false_positive_count": fp,
                        "background_flag_rate": (fp / total) if total else float("nan"),
                        "fp_per_10k": (fp / total * 10000.0) if total else float("nan")})
    return summary, pd.concat(event_frames, ignore_index=True)


def build_event_frame(rows: pd.DataFrame, flag_col: str, event_labels: pd.DataFrame,
                      dataset: str, split: str) -> pd.DataFrame:
    """Per-event detection, first flag, latency, coverage (gaps excluded)."""
    faults = event_labels[(event_labels["split"] == split)
                          & (event_labels["fault_type"] != "COMMUNICATION_GAP")].reset_index(drop=True)
    out: list[dict] = []
    for _, event in faults.iterrows():
        sub = rows[rows["injection_id"] == event["injection_id"]].sort_values("timestamp")
        flagged = sub[sub[flag_col] == 1]
        detected = len(flagged) > 0
        rec: dict = {
            "source_dataset": dataset.lower(), "split": split, "method": flag_col,
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
    cols = ["source_dataset", "split", "method", "injection_id", "fault_type", "target_variable",
            "start_timestamp", "end_timestamp", "duration_minutes", "injected_row_count",
            "detected", "detected_row_count", "row_coverage",
            "first_detection_timestamp", "latency_minutes"]
    return pd.DataFrame(out, columns=cols)

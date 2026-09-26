"""Phase 11 evaluation: evidence assembly, training, metrics, end-to-end.

Training uses benchmark TRAIN fault rows only (supervised classification
is explicitly allowed labels here). ID/OOD labels are measurement-only.
Frozen detectors are scored, never retrained; thresholds never modified.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.ensemble.calibration import calibrate, fit_ecdf
from src.ensemble.aggregation import statistical_component
from src.evaluation.statistical_baseline.evaluator import evaluate_split
from src.isolation_forest.evaluator import prepare_split
from src.root_cause import confidence as CF
from src.root_cause import classifier as CL
from src.root_cause import explain as EX
from src.root_cause.features import (
    DIAGNOSTIC_FEATURES,
    KNOWN_CLASSES,
    TRAIN_CLASS_MAP,
    build_evidence_frame,
    map_training_class,
)
from src.root_cause.unknown_mixed import decide

logger = logging.getLogger("aws_root_cause.evaluator")

GATE_FLAG = "ens_median_flag"


def build_split_evidence(bench: pd.DataFrame, dataset: str, split: str,
                         project_root: str = ".") -> pd.DataFrame:
    """Assemble detector evidence + temporal features for one split frame."""
    from pathlib import Path

    root = Path(project_root)
    ds = dataset.lower()
    stat_rows, _ = evaluate_split(ds, split, bench)
    features, quality = prepare_split(bench, ds)
    if not (stat_rows["timestamp"].astype(str).tolist() == bench["timestamp"].astype(str).tolist()):
        raise ValueError(f"{ds}/{split}: stat evidence misaligned")

    frozen_if = pd.read_csv(root / "data" / "isolation_forest" / f"{ds}_isolation_forest_predictions.csv")
    frozen_if = frozen_if[frozen_if["split"] == split].reset_index(drop=True)
    if frozen_if["timestamp"].astype(str).tolist() != bench["timestamp"].astype(str).tolist():
        raise ValueError(f"{ds}/{split}: IF evidence misaligned")
    if_raw = np.array(frozen_if["if_raw_score"].to_numpy(dtype=float), copy=True)
    if_cal = np.array(frozen_if["if_anomaly_score"].to_numpy(dtype=float), copy=True)
    if_ok = frozen_if["scorable"].to_numpy(dtype=int) == 1
    if_raw[~if_ok] = np.nan
    if_cal[~if_ok] = np.nan

    if split == "train":
        lstm_target, lstm_full, lstm_ok = _lstm_train_scores(features, quality, ds, root)
    else:
        frozen_lstm = pd.read_csv(root / "data" / "lstm_autoencoder" / f"{ds}_lstm_predictions.csv")
        frozen_lstm = frozen_lstm[frozen_lstm["split"] == split].reset_index(drop=True)
        if frozen_lstm["timestamp"].astype(str).tolist() != bench["timestamp"].astype(str).tolist():
            raise ValueError(f"{ds}/{split}: LSTM evidence misaligned")
        lstm_target = np.array(frozen_lstm["lstm_target_mse"].to_numpy(dtype=float), copy=True)
        lstm_full = np.array(frozen_lstm["lstm_full_mse"].to_numpy(dtype=float), copy=True)
        lstm_ok = frozen_lstm["scorable"].to_numpy(dtype=int) == 1
        lstm_target[~lstm_ok] = np.nan
        lstm_full[~lstm_ok] = np.nan

    z = np.stack([pd.to_numeric(stat_rows[c], errors="coerce").to_numpy(dtype=float)
                  for c in ("temperature_zscore", "pressure_zscore", "humidity_zscore")], axis=1)
    z_ok = np.isfinite(z).any(axis=1)
    z_max = np.full(len(bench), np.nan)
    z_max[z_ok] = np.nanmax(np.abs(z[z_ok]), axis=1)
    iqr = np.stack([pd.to_numeric(stat_rows[c], errors="coerce").to_numpy(dtype=float)
                    for c in ("temperature_iqr_flag", "pressure_iqr_flag",
                              "humidity_iqr_flag")], axis=1)
    iqr_ok = np.isfinite(iqr).any(axis=1)
    iqr_comb = np.full(len(bench), np.nan)
    iqr_comb[iqr_ok] = np.nanmax(iqr[iqr_ok], axis=1)

    if split == "train":
        cal_bundle = __import__("joblib").load(
            root / "models" / "ensemble" / f"{ds}_calibration.joblib")
        comp = pd.DataFrame({"z_raw": z_max, "iqr_raw": iqr_comb,
                             "if_raw": if_raw, "lstm_raw": lstm_target})
        ens_mean, ens_median = _ensemble_from_frozen(comp, cal_bundle["ecdf"])
        thr = cal_bundle["thresholds"]
        mean_flag = (ens_mean >= thr["ens_mean"]).astype(int)
        median_flag = (ens_median >= thr["ens_median"]).astype(int)
    else:
        frozen_ens = pd.read_csv(root / "data" / "ensemble" / f"{ds}_ensemble_predictions.csv")
        frozen_ens = frozen_ens[frozen_ens["split"] == split].reset_index(drop=True)
        if frozen_ens["timestamp"].astype(str).tolist() != bench["timestamp"].astype(str).tolist():
            raise ValueError(f"{ds}/{split}: ensemble evidence misaligned")
        ens_mean = frozen_ens["ens_mean"].to_numpy(dtype=float)
        ens_median = frozen_ens["ens_median"].to_numpy(dtype=float)
        mean_flag = frozen_ens["ens_mean_flag"].to_numpy(dtype=int)
        median_flag = frozen_ens["ens_median_flag"].to_numpy(dtype=int)

    eligible = (quality["ml_eligible"].to_numpy(dtype=int) == 1).astype(int)
    stat_ok = (z_ok | iqr_ok).astype(int)
    n_comp = stat_ok + if_ok.astype(int) + lstm_ok.astype(int)
    combined = pd.DataFrame({
        "timestamp": bench["timestamp"].astype(str).values,
        "source_dataset": ds,
        "split": split,
        "z_maxabs": z_max,
        "iqr_combined": iqr_comb,
        "if_raw": if_raw,
        "if_cal": if_cal,
        "lstm_target_mse": lstm_target,
        "lstm_full_mse": lstm_full,
        "ens_mean": ens_mean,
        "ens_median": ens_median,
        "ens_mean_flag": mean_flag,
        "ens_median_flag": median_flag,
        "n_components_available": n_comp,
        "ml_eligible": eligible,
    })
    for col in ("temperature_c", "pressure_hpa", "relative_humidity_pct", "hour_sin",
                "hour_cos", "temperature_delta", "temperature_rate_per_hour",
                "temperature_abs_rate_per_hour", "pressure_delta", "pressure_rate_per_hour",
                "pressure_abs_rate_per_hour", "humidity_delta", "humidity_rate_per_hour",
                "humidity_abs_rate_per_hour", "temperature_deviation_from_median_2h",
                "temperature_robust_deviation_2h", "pressure_deviation_from_median_2h",
                "pressure_robust_deviation_2h", "humidity_deviation_from_median_2h",
                "humidity_robust_deviation_2h", "temperature_trend_2h", "pressure_trend_2h",
                "humidity_trend_2h", "temperature_zero_delta_ratio_2h",
                "pressure_zero_delta_ratio_2h", "humidity_zero_delta_ratio_2h",
                "multivariate_max_abs_robust_deviation_2h",
                "multivariate_deviation_range_2h"):
        combined[col] = pd.to_numeric(features[col], errors="coerce").values
    combined["ground_truth_anomaly"] = bench["ground_truth_anomaly"].to_numpy(dtype=int)
    combined["ground_truth_fault_type"] = bench["ground_truth_fault_type"].astype(str).values
    combined["injection_id"] = bench["injection_id"].astype(str).values
    combined["evaluation_eligible"] = eligible
    combined["data_quality_status"] = quality["quality_status"].astype(str).values
    return combined


def _lstm_train_scores(features: pd.DataFrame, quality: pd.DataFrame,
                       dataset: str, root) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Frozen LSTM inference on train-split rows (no refit)."""
    import joblib
    import tensorflow as tf

    from src.lstm_autoencoder.scoring import reconstruction_errors
    from src.lstm_autoencoder.sequences import build_sequences, prepare_frame, valid_sequence_mask

    bundle = joblib.load(root / "models" / "lstm_autoencoder" / f"{dataset}_scaler.joblib")
    model = tf.keras.models.load_model(
        root / "models" / "lstm_autoencoder" / f"{dataset}_lstm_autoencoder.keras")
    mat, segments, eligible, finite = prepare_frame(
        features, quality, list(bundle["feature_order"]))
    scaled = bundle["scaler"].transform(mat)
    valid = valid_sequence_mask(segments, eligible, finite)
    X, positions = build_sequences(scaled, valid)
    target = np.full(len(features), np.nan)
    full = np.full(len(features), np.nan)
    if len(X):
        X_hat = model.predict(X, batch_size=1024, verbose=0)
        t_mse, f_mse = reconstruction_errors(X, X_hat)
        target[positions] = t_mse
        full[positions] = f_mse
    return target, full, valid


def _ensemble_from_frozen(comp: pd.DataFrame, ecdf: dict) -> tuple[np.ndarray, np.ndarray]:
    """Equal-weight mean/median from frozen ECDFs (train rows)."""
    z_cal = calibrate(comp["z_raw"].to_numpy(dtype=float), ecdf["z"])
    iqr_cal = calibrate(comp["iqr_raw"].to_numpy(dtype=float), ecdf["iqr"])
    if_cal = calibrate(comp["if_raw"].to_numpy(dtype=float), ecdf["if"])
    lstm_cal = calibrate(comp["lstm_raw"].to_numpy(dtype=float), ecdf["lstm"])
    stat_cal, _ = statistical_component(z_cal, iqr_cal)
    mat = np.stack([stat_cal, if_cal, lstm_cal], axis=1)
    n_avail = np.isfinite(mat).sum(axis=1)
    mean = np.full(len(mat), np.nan)
    median = np.full(len(mat), np.nan)
    ok = n_avail > 0
    with np.errstate(all="ignore"):
        mean[ok] = np.nanmean(mat[ok], axis=1)
        median[ok] = np.nanmedian(mat[ok], axis=1)
    mean[n_avail < 2] = np.nan
    median[n_avail < 2] = np.nan
    return mean, median


def fit_dataset(evidence: pd.DataFrame) -> tuple[object, dict, pd.DataFrame]:
    """Fit the classifier on labeled train fault rows; return model/info/frame."""
    work = evidence.copy()
    work["train_class"] = work["ground_truth_fault_type"].map(TRAIN_CLASS_MAP)
    spray = work[work["train_class"].notna()].reset_index(drop=True)
    if (work["split"] != "train").any():
        raise ValueError("Classifier fitting requires train-split evidence only")
    X_all, complete = build_evidence_frame(spray[list(DIAGNOSTIC_FEATURES)])
    spray = spray[complete].reset_index(drop=True)
    X_all = X_all[complete].reset_index(drop=True)
    y_all = spray["train_class"]
    n = len(spray)
    fit_idx, val_idx = CF.chronological_validation_split(n)
    model, train_info = CL.fit_classifier(X_all.iloc[fit_idx], y_all.iloc[fit_idx])
    val_stats = CF.validation_confidence_stats(model, X_all.iloc[val_idx], y_all.iloc[val_idx])
    excluded = int((~complete).sum())
    info = {**train_info, "validation_stats": val_stats,
            "n_complete_rows": int(complete.sum()), "n_excluded_incomplete": excluded,
            "val_fraction": CF.VAL_FRACTION}
    return model, info, spray


def diagnose_frame(model, evidence: pd.DataFrame) -> pd.DataFrame:
    """Classify rows with complete evidence; others get no prediction."""
    X_all, complete = build_evidence_frame(evidence[list(DIAGNOSTIC_FEATURES)])
    out = evidence.copy()
    for col in ("predicted_class", "confidence", "runner_up", "explanation"):
        out[col] = None
    out["has_diagnosis"] = False
    if complete.sum() == 0:
        return out
    probas = CL.predict_proba(model, X_all[complete])
    labels, conf, runner = decide(probas, list(model.classes_))
    idx = out.index[complete]
    out.loc[idx, "predicted_class"] = labels
    out.loc[idx, "confidence"] = conf
    out.loc[idx, "runner_up"] = runner
    out.loc[idx, "has_diagnosis"] = True
    prob_cols = pd.DataFrame(probas, index=idx,
                             columns=[f"proba_{c}" for c in model.classes_])
    for col in prob_cols.columns:
        out[col] = np.nan
        out.loc[idx, col] = prob_cols[col].values
    return out


def classification_metrics(truth: list[str], pred: list[str],
                           classes: list[str]) -> dict:
    """Accuracy, macro P/R/F1, per-class P/R/F1, confusion counts."""
    truth = np.array(truth, dtype=object)
    pred = np.array(pred, dtype=object)
    accuracy = float((truth == pred).mean()) if len(truth) else float("nan")
    per_class, precisions, recalls, f1s = {}, [], [], []
    matrix = {actual: {predicted: 0 for predicted in classes} for actual in classes}
    for actual, predicted in zip(truth, pred):
        if actual in matrix and predicted in matrix[actual]:
            matrix[actual][predicted] += 1
    for actual in classes:
        row = matrix[actual]
        tp = row.get(actual, 0)
        fp = sum(matrix[a].get(actual, 0) for a in classes if a != actual)
        fn = sum(v for k, v in row.items() if k != actual)
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall and not (np.isnan(precision) or np.isnan(recall))
              else float("nan"))
        per_class[actual] = {"precision": precision, "recall": recall, "f1": f1,
                             "support": int((truth == actual).sum())}
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
    macro = {f"macro_{m}": float(np.nanmean(v)) for m, v in
             (("precision", precisions), ("recall", recalls), ("f1", f1s))}
    return {"accuracy": accuracy, **macro, "per_class": per_class,
            "confusion": matrix, "n": int(len(truth))}

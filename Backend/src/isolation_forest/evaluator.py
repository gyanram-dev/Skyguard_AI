"""Per-dataset Isolation Forest pipeline: train, freeze, predict, measure.

Training data: CLEAN pre-benchmark observations from data/processed/
restricted to the exact Phase 5 training-period boundaries. Benchmark
files, labels, manifests, and mutated sensor values never enter fitting
or threshold selection (a forbidden-column guard rejects them loudly).
Evaluation splits use the injected benchmark values and labels.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from src.data_quality.batch_validator import validate_dataframe
from src.evaluation.statistical_baseline.evaluator import _as_feature_input
from src.evaluation.statistical_baseline.metrics import confusion_counts, prf_metrics
from src.features.feature_builder import build_features_for_dataset
from src.isolation_forest import features as F
from src.isolation_forest.model import fit_model, load_artifact
from src.isolation_forest.scoring import flag_scores, normalize_scores, raw_scores
from src.isolation_forest.threshold import fit_threshold

logger = logging.getLogger("aws_iforest.evaluator")

METHOD = "iforest"

# Exact Phase 5 training-period boundaries (from benchmark_manifest.json).
# The pipeline asserts the manifest agrees with these before fitting.
EXPECTED_TRAIN_PERIODS = {
    "jena": ("2009-01-01 00:10:00", "2013-10-17 22:50:00"),
    "delhi": ("2022-04-01 00:00:00", "2023-11-25 14:15:00"),
}

TRAINING_SOURCE_TEMPLATE = "data/processed/{dataset}_clean.csv"


def train_period_bounds(project_root: str | Path, dataset: str) -> tuple[str, str]:
    """Return the manifest's train-split (start, end) for a dataset."""
    ds = dataset.lower()
    manifest = json.loads(
        (Path(project_root) / "data" / "benchmark" / "manifests"
         / "benchmark_manifest.json").read_text(encoding="utf-8"))
    train = next(s for s in manifest["datasets"][ds]["splits"] if s["name"] == "train")
    return str(train["start_timestamp"]), str(train["end_timestamp"])


def load_clean_train_frame(dataset: str, project_root: str | Path = ".") -> pd.DataFrame:
    """Load clean pre-benchmark training rows for the Phase 5 train period.

    Source is data/processed/{dataset}_clean.csv (never data/benchmark/).
    Rows are restricted to the exact manifest train boundaries, inclusive.
    """
    ds = dataset.lower()
    root = Path(project_root)
    start, end = train_period_bounds(root, ds)
    expected = EXPECTED_TRAIN_PERIODS[ds]
    if (start, end) != expected:
        raise ValueError(
            f"Phase 5 train boundaries moved for {ds}: manifest {(start, end)} "
            f"!= expected {expected}")
    clean = pd.read_csv(root / TRAINING_SOURCE_TEMPLATE.format(dataset=ds))
    F.assert_no_forbidden_columns(clean)
    ts = pd.to_datetime(clean["timestamp"], errors="coerce")
    mask = (ts >= pd.Timestamp(start)) & (ts <= pd.Timestamp(end))
    frame = clean.loc[mask].sort_values("timestamp").reset_index(drop=True)
    if len(frame) == 0:
        raise ValueError(f"No clean training rows for {ds} in [{start}, {end}]")
    return frame


def prepare_split(sensor_frame: pd.DataFrame, dataset: str,
                  cadence_min: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Causal features + DQ context from sensor values (clean or benchmark).

    An explicit cadence overrides frozen dataset tables for uploaded data;
    existing callers pass nothing and are unaffected.
    """
    feat_input = _as_feature_input(sensor_frame, dataset)
    features = build_features_for_dataset(feat_input, dataset, cadence_min)
    quality, _ = validate_dataframe(feat_input, dataset, cadence_min)
    return features, quality


def train_dataset(train_clean: pd.DataFrame, dataset: str) -> dict:
    """Fit model + threshold on clean pre-benchmark rows only.

    train_clean must come from data/processed/ (see load_clean_train_frame).
    Any benchmark label/injection column in the input raises loudly, so a
    benchmark train frame can never be fitted silently. No labels used.
    """
    ds = dataset.lower()
    F.assert_no_forbidden_columns(train_clean)
    features, quality = prepare_split(train_clean, ds)
    allowlist = F.build_allowlist(list(features.columns))
    X, scorable = F.to_model_matrix(features, allowlist)
    eligible = quality["ml_eligible"].to_numpy(dtype=int) == 1
    train_mask = eligible & scorable
    if train_mask.sum() == 0:
        raise ValueError(f"No eligible train rows for {ds}")
    model = fit_model(X[train_mask])
    train_raw = raw_scores(model, X[train_mask])
    threshold_raw, thresh_diag = fit_threshold(train_raw)
    bundle = {
        "model": model,
        "allowlist": allowlist,
        "_feature_schema": list(features.columns),
        "threshold_raw": threshold_raw,
        "threshold_diag": thresh_diag,
        "train_raw_sorted": np.sort(train_raw),
        "n_train_rows": int(len(features)),
        "n_train_eligible": int(eligible.sum()),
        "n_train_fitted": int(train_mask.sum()),
        "sklearn_version": sklearn.__version__,
        "train_start_timestamp": str(train_clean["timestamp"].iloc[0]),
        "train_end_timestamp": str(train_clean["timestamp"].iloc[-1]),
    }
    logger.info("%s: fitted on %d/%d rows; threshold=%.4f", ds, bundle["n_train_fitted"],
                bundle["n_train_rows"], threshold_raw)
    return bundle


def predict_split(bundle: dict, bench: pd.DataFrame, dataset: str, split: str) -> pd.DataFrame:
    """Predict with the frozen bundle. Unscorable rows get NaN scores, flag 0."""
    ds = dataset.lower()
    features, quality = prepare_split(bench, ds)
    if list(features.columns) != list(bundle["_feature_schema"]):
        raise ValueError("Feature schema drift between train and evaluation")
    X, scorable = F.to_model_matrix(features, bundle["allowlist"])
    raw = np.full(len(bench), np.nan)
    raw[scorable] = raw_scores(bundle["model"], X[scorable])
    norm = np.full(len(bench), np.nan)
    norm[scorable] = normalize_scores(raw[scorable], bundle["train_raw_sorted"])
    flag = np.zeros(len(bench), dtype=int)
    flag[scorable] = flag_scores(raw[scorable], bundle["threshold_raw"])
    eligible = (quality["ml_eligible"].to_numpy(dtype=int) == 1).astype(int)
    return pd.DataFrame({
        "timestamp": bench["timestamp"].astype(str).values,
        "source_dataset": ds,
        "split": split,
        "temperature_c": pd.to_numeric(bench["temperature_c"], errors="coerce").values,
        "pressure_hpa": pd.to_numeric(bench["pressure_hpa"], errors="coerce").values,
        "relative_humidity_pct": pd.to_numeric(bench["relative_humidity_pct"], errors="coerce").values,
        "if_raw_score": raw,
        "if_anomaly_score": norm,
        "if_anomaly_flag": flag,
        "scorable": scorable.astype(int),
        "ground_truth_anomaly": bench["ground_truth_anomaly"].to_numpy(dtype=int),
        "ground_truth_fault_type": bench["ground_truth_fault_type"].astype(str).values,
        "injection_id": bench["injection_id"].astype(str).values,
        "evaluation_eligible": eligible,
        "data_quality_status": quality["quality_status"].astype(str).values,
    })


def summarize_rows(rows: pd.DataFrame, dataset: str, split: str,
                   event_labels: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Row/event/variable/FP summaries in Phase 6-compatible record format."""
    summary: list[dict] = []
    el = rows[rows["evaluation_eligible"] == 1]
    y_true = el["ground_truth_anomaly"].to_numpy(dtype=int)
    y_pred = el["if_anomaly_flag"].to_numpy(dtype=int)
    cc = confusion_counts(y_true, y_pred)
    summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": "overall",
                    "group": "all", **cc, **prf_metrics(cc["tp"], cc["fp"], cc["tn"], cc["fn"]),
                    "eligible_rows": int(len(el))})
    for fault in ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT"):
        sub = el[el["ground_truth_fault_type"] == fault]
        if len(sub) == 0:
            summary.append({"dataset": dataset, "split": split, "method": METHOD,
                            "scope": "fault_type", "group": fault, "injected_rows": 0,
                            "note": "absent_in_split"})
            continue
        injected = int((sub["ground_truth_anomaly"] == 1).sum())
        cc2 = confusion_counts(sub["ground_truth_anomaly"].tolist(), sub["if_anomaly_flag"].tolist())
        summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": "fault_type",
                        "group": fault, "injected_rows": injected, **cc2,
                        **prf_metrics(cc2["tp"], cc2["fp"], cc2["tn"], cc2["fn"]),
                        "eligible_rows": int(len(sub))})
    # Per-variable recall from benchmark metadata (single-variable faults).
    faults = event_labels[(event_labels["split"] == split)
                          & (event_labels["fault_type"].isin(("SPIKE", "FROZEN", "DRIFT")))]
    target_of = dict(zip(faults["injection_id"].astype(str), faults["target_variable"].astype(str)))
    tmp = el.copy()
    tmp["event_target"] = tmp["injection_id"].map(target_of)
    for var in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
        sub = tmp[(tmp["ground_truth_anomaly"] == 1) & (tmp["event_target"] == var)]
        injected = int(len(sub))
        detected = int((sub["if_anomaly_flag"] == 1).sum())
        summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": "variable",
                        "group": var, "injected_rows": injected, "detected_rows": detected,
                        "missed_rows": injected - detected,
                        "recall": (detected / injected) if injected else float("nan")})
    # Events.
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
                            "latency_mean_min": float(np.mean(ok)) if len(ok) else float("nan"),
                            "latency_min_min": float(np.min(ok)) if len(ok) else float("nan"),
                            "latency_max_min": float(np.max(ok)) if len(ok) else float("nan")})
    # False positives on eligible background.
    bg = el[el["ground_truth_anomaly"] == 0]
    fp = int((bg["if_anomaly_flag"] == 1).sum())
    total = int(len(bg))
    summary.append({"dataset": dataset, "split": split, "method": METHOD, "scope": "false_positive",
                    "group": "background", "background_rows": total, "false_positive_count": fp,
                    "background_flag_rate": (fp / total) if total else float("nan"),
                    "fp_per_10k": (fp / total * 10000.0) if total else float("nan")})
    return summary, events


def build_event_frame(rows: pd.DataFrame, event_labels: pd.DataFrame,
                      dataset: str, split: str) -> pd.DataFrame:
    """Per-event detection, first flag, latency, coverage (gaps excluded upstream)."""
    faults = event_labels[(event_labels["split"] == split)
                          & (event_labels["fault_type"] != "COMMUNICATION_GAP")].reset_index(drop=True)
    out: list[dict] = []
    for _, e in faults.iterrows():
        sub = rows[rows["injection_id"] == e["injection_id"]].sort_values("timestamp")
        flagged = sub[sub["if_anomaly_flag"] == 1]
        detected = len(flagged) > 0
        rec: dict = {
            "source_dataset": dataset.lower(), "split": split, "injection_id": e["injection_id"],
            "fault_type": e["fault_type"], "target_variable": e["target_variable"],
            "start_timestamp": e["start_timestamp"], "end_timestamp": e["end_timestamp"],
            "duration_minutes": float(e["duration_minutes"]),
            "injected_row_count": int(len(sub)),
            "detected": int(detected),
            "detected_row_count": int(len(flagged)),
            "row_coverage": (len(flagged) / len(sub)) if len(sub) else float("nan"),
        }
        if detected:
            first = pd.Timestamp(flagged["timestamp"].iloc[0])
            rec["first_detection_timestamp"] = str(flagged["timestamp"].iloc[0])
            rec["latency_minutes"] = (first - pd.Timestamp(e["start_timestamp"])).total_seconds() / 60.0
        else:
            rec["first_detection_timestamp"] = None
            rec["latency_minutes"] = float("nan")
        out.append(rec)
    cols = ["source_dataset", "split", "injection_id", "fault_type", "target_variable",
            "start_timestamp", "end_timestamp", "duration_minutes", "injected_row_count",
            "detected", "detected_row_count", "row_coverage",
            "first_detection_timestamp", "latency_minutes"]
    return pd.DataFrame(out, columns=cols)

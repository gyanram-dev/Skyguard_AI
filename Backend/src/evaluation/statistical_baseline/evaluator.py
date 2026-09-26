"""Recompute the frozen Phase 4 baseline on one benchmark split's actual signal.

Pipeline per split (no duplicated algorithms):
    benchmark sensor values
        -> Phase 3 build_features_for_dataset (causal, gap-aware segments)
        -> Phase 2.5 validate_dataframe (ml_eligible / quality context)
        -> Phase 4 build_statistical_baseline (z + IQR views)
        -> join ground-truth labels + per-method combined predictions

Clean-data rolling scores are NEVER reused at injected timestamps.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.data_quality.batch_validator import validate_dataframe
from src.evaluation.statistical_baseline.metrics import (
    OFFICIAL_IQR_FACTOR,
    OFFICIAL_Z_THRESHOLD,
)
from src.features.feature_builder import build_features_for_dataset
from src.baseline.statistical_baseline import build_statistical_baseline

logger = logging.getLogger("aws_eval_baseline.evaluator")

Z_VARS = ("temperature", "pressure", "humidity")


def _as_feature_input(bench: pd.DataFrame, dataset: str) -> pd.DataFrame:
    """Phase 2-schema input for the feature builder (Delhi flags synthesized)."""
    df = pd.DataFrame({
        "timestamp": bench["timestamp"].astype(str).values,
        "temperature_c": pd.to_numeric(bench["temperature_c"], errors="coerce").values,
        "pressure_hpa": pd.to_numeric(bench["pressure_hpa"], errors="coerce").values,
        "relative_humidity_pct": pd.to_numeric(bench["relative_humidity_pct"], errors="coerce").values,
        "source_dataset": dataset.lower(),
    })
    if dataset.lower() == "delhi":
        t_miss = df["temperature_c"].isna().astype(int)
        h_miss = df["relative_humidity_pct"].isna().astype(int)
        p_miss = df["pressure_hpa"].isna().astype(int)
        df["temperature_missing"] = t_miss
        df["humidity_missing"] = h_miss
        df["pressure_missing"] = p_miss
        df["any_core_missing"] = ((t_miss + h_miss + p_miss) > 0).astype(int)
        df["missing_core_count"] = (t_miss + h_miss + p_miss).astype(int)
    return df


def _combined_prediction(frame: pd.DataFrame, view: str) -> np.ndarray:
    """Per-method combined flag: any variable flag == 1 (NaN -> 0 = not flagged)."""
    cols = [f"{v}_{view}_flag" for v in Z_VARS]
    mat = frame[cols].to_numpy(dtype=float)
    return (np.nan_to_num(mat, nan=0.0) == 1.0).any(axis=1).astype(int)


def evaluate_split(dataset: str, split: str, bench: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate one benchmark split. Return (row_results, event_inputs).

    row_results: one auditable row per benchmark observation with both
    methods' flags, labels, eligibility, and quality status.
    event_inputs: the baseline frame joined to labels for event analysis.
    """
    ds = dataset.lower()
    logger.info("Evaluating %s %s (%d rows)...", ds, split, len(bench))

    feat_input = _as_feature_input(bench, ds)
    features = build_features_for_dataset(feat_input, ds)
    quality, _ = validate_dataframe(feat_input, ds)
    baseline, _ = build_statistical_baseline(
        features, quality, ds,
        z_threshold=OFFICIAL_Z_THRESHOLD, iqr_factor=OFFICIAL_IQR_FACTOR,
    )

    z_pred = _combined_prediction(baseline, "zscore")
    iqr_pred = _combined_prediction(baseline, "iqr")
    combined_pred = np.maximum(z_pred, iqr_pred)
    eligible = (quality["ml_eligible"].to_numpy(dtype=int) == 1).astype(int)

    rows = pd.DataFrame({
        "timestamp": bench["timestamp"].astype(str).values,
        "source_dataset": ds,
        "split": split,
        "temperature_c": pd.to_numeric(bench["temperature_c"], errors="coerce").values,
        "pressure_hpa": pd.to_numeric(bench["pressure_hpa"], errors="coerce").values,
        "relative_humidity_pct": pd.to_numeric(bench["relative_humidity_pct"], errors="coerce").values,
        "temperature_zscore": baseline["temperature_zscore_baseline"].to_numpy(dtype=float),
        "pressure_zscore": baseline["pressure_zscore_baseline"].to_numpy(dtype=float),
        "humidity_zscore": baseline["humidity_zscore_baseline"].to_numpy(dtype=float),
        "temperature_zscore_flag": baseline["temperature_zscore_flag"].to_numpy(dtype=float),
        "pressure_zscore_flag": baseline["pressure_zscore_flag"].to_numpy(dtype=float),
        "humidity_zscore_flag": baseline["humidity_zscore_flag"].to_numpy(dtype=float),
        "temperature_iqr_flag": baseline["temperature_iqr_flag"].to_numpy(dtype=float),
        "pressure_iqr_flag": baseline["pressure_iqr_flag"].to_numpy(dtype=float),
        "humidity_iqr_flag": baseline["humidity_iqr_flag"].to_numpy(dtype=float),
        "zscore_combined_flag": z_pred,
        "iqr_combined_flag": iqr_pred,
        "combined_flag": combined_pred,
        "ground_truth_anomaly": bench["ground_truth_anomaly"].to_numpy(dtype=int),
        "ground_truth_fault_type": bench["ground_truth_fault_type"].astype(str).values,
        "injection_id": bench["injection_id"].astype(str).values,
        "evaluation_eligible": eligible,
        "data_quality_status": quality["quality_status"].astype(str).values,
    })
    return rows, baseline

"""Diagnostic evidence features for root-cause classification.

Every feature is computed from detector evidence or causal Phase 3
features available at the timestamp. No ground-truth, injection,
fault-type, event-ID, or test/OOD metadata ever enters. Forbidden
columns raise loudly instead of being silently dropped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.isolation_forest.features import assert_no_forbidden_columns

# Detector evidence (frozen Phase 6/7/9/10 outputs, never refit here).
EVIDENCE_FEATURES: tuple[str, ...] = (
    "z_maxabs",
    "iqr_combined",
    "if_raw",
    "if_cal",
    "lstm_target_mse",
    "lstm_full_mse",
    "ens_mean",
    "ens_median",
    "n_components_available",
    "ml_eligible",
)

# Causal Phase 3 temporal/diagnostic features (subset of the Phase 7
# 94-feature allowlist; same frozen definitions).
TEMPORAL_FEATURES: tuple[str, ...] = (
    "temperature_c",
    "pressure_hpa",
    "relative_humidity_pct",
    "hour_sin",
    "hour_cos",
    "temperature_delta",
    "temperature_rate_per_hour",
    "temperature_abs_rate_per_hour",
    "pressure_delta",
    "pressure_rate_per_hour",
    "pressure_abs_rate_per_hour",
    "humidity_delta",
    "humidity_rate_per_hour",
    "humidity_abs_rate_per_hour",
    "temperature_deviation_from_median_2h",
    "temperature_robust_deviation_2h",
    "pressure_deviation_from_median_2h",
    "pressure_robust_deviation_2h",
    "humidity_deviation_from_median_2h",
    "humidity_robust_deviation_2h",
    "temperature_trend_2h",
    "pressure_trend_2h",
    "humidity_trend_2h",
    "temperature_zero_delta_ratio_2h",
    "pressure_zero_delta_ratio_2h",
    "humidity_zero_delta_ratio_2h",
    "multivariate_max_abs_robust_deviation_2h",
    "multivariate_deviation_range_2h",
)

DIAGNOSTIC_FEATURES: tuple[str, ...] = EVIDENCE_FEATURES + TEMPORAL_FEATURES

# Benchmark fault type -> classifier training class.
TRAIN_CLASS_MAP = {
    "SPIKE": "SPIKE",
    "FROZEN": "FROZEN",
    "DRIFT": "DRIFT",
    "CROSS_VARIABLE": "CROSS",
    "SPIKE_PLUS_DRIFT": "MIXED",
}
KNOWN_CLASSES = ("SPIKE", "FROZEN", "DRIFT", "CROSS")


def map_training_class(fault_type: str) -> str | None:
    """Map a benchmark fault type to a training class (None = excluded)."""
    if fault_type in ("NONE", "COMMUNICATION_GAP"):
        return None
    return TRAIN_CLASS_MAP.get(fault_type)


def build_evidence_frame(feature_frame: pd.DataFrame) -> pd.DataFrame:
    """Assemble the classifier matrix; rows with any NaN are masked out.

    The input must contain ONLY model features: any label/evaluation
    column present raises loudly instead of being silently dropped.
    Callers keep labels/metadata in a separate frame joined by position.
    """
    assert_no_forbidden_columns(feature_frame)
    missing = [c for c in DIAGNOSTIC_FEATURES if c not in feature_frame.columns]
    if missing:
        raise ValueError(f"Evidence frame lacks features: {missing}")
    mat = feature_frame[list(DIAGNOSTIC_FEATURES)].to_numpy(dtype=float)
    complete = np.isfinite(mat).all(axis=1)
    return pd.DataFrame(mat, columns=list(DIAGNOSTIC_FEATURES)), complete

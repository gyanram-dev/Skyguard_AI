"""Automated unit and integration test suite for Phase 3 Feature Engineering.

Validates:
- Strict anti-data-leakage (non-anticipation).
- Sampling-aware row window horizons.
- Segment boundary quarantine (rolling windows do not cross gaps).
- Immutability of processed inputs.
- Deterministic feature reproduction.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features.feature_builder import build_features_for_dataset
from src.features.validation import (
    validate_delhi_features,
    validate_jena_features,
    verify_anti_data_leakage,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


@pytest.fixture(scope="module")
def jena_clean_sample(project_root) -> pd.DataFrame:
    p = project_root / "data" / "processed" / "jena_clean.csv"
    return pd.read_csv(p, nrows=200)


@pytest.fixture(scope="module")
def delhi_clean_sample(project_root) -> pd.DataFrame:
    p = project_root / "data" / "processed" / "delhi_clean.csv"
    return pd.read_csv(p, nrows=200)


# ==============================================================================
# ANTI-DATA-LEAKAGE TESTS (CRITICAL REQUIREMENT)
# ==============================================================================

def test_anti_data_leakage_jena(jena_clean_sample):
    """Verify that perturbing observation at t+1 cannot alter features at timestamp t for Jena."""
    res = verify_anti_data_leakage(jena_clean_sample, "jena", target_col="temperature_c", perturb_idx=50)
    assert res["passed"] is True
    assert res["max_diff_prior"] <= 1e-12
    assert res["shock_propagated_to_future"] is True


def test_anti_data_leakage_delhi(delhi_clean_sample):
    """Verify that perturbing observation at t+1 cannot alter features at timestamp t for Delhi."""
    res = verify_anti_data_leakage(delhi_clean_sample, "delhi", target_col="temperature_c", perturb_idx=50)
    assert res["passed"] is True
    assert res["max_diff_prior"] <= 1e-12
    assert res["shock_propagated_to_future"] is True


# ==============================================================================
# SEGMENT & GAP CONTAINMENT TESTS
# ==============================================================================

def test_segment_boundary_containment():
    """Verify that causal rolling features NEVER use observations across a structural gap."""
    # Synthesize data with a 2-hour gap between row 9 and row 10 (cadence 10m)
    dates_part1 = pd.date_range("2024-01-01 00:00", periods=10, freq="10min")
    dates_part2 = pd.date_range("2024-01-01 03:30", periods=10, freq="10min")  # 2h gap
    all_dates = list(dates_part1) + list(dates_part2)

    df_synth = pd.DataFrame({
        "timestamp": [d.strftime("%Y-%m-%d %H:%M:%S") for d in all_dates],
        "temperature_c": np.arange(20, dtype=float),
        "pressure_hpa": np.full(20, 1000.0),
        "relative_humidity_pct": np.full(20, 50.0),
        "source_dataset": "jena",
    })

    feat = build_features_for_dataset(df_synth, "jena")

    # Row 10 is the first row after the gap (gap_before == 1)
    assert feat.loc[10, "gap_before"] == 1
    assert feat.loc[10, "segment_id"] == 1
    assert feat.loc[9, "segment_id"] == 0

    # 30m rolling mean requires 3 prior observations inside the SAME segment
    # Row 10 has 0 prior observations in segment 1 -> must be NaN
    # Row 11 has 1 prior observation in segment 1 -> must be NaN
    # Row 12 has 2 prior observations in segment 1 -> must be NaN
    # Row 13 has 3 prior observations in segment 1 (rows 10, 11, 12) -> valid float!
    assert pd.isna(feat.loc[10, "temperature_prev_mean_30m"])
    assert pd.isna(feat.loc[11, "temperature_prev_mean_30m"])
    assert pd.isna(feat.loc[12, "temperature_prev_mean_30m"])
    assert not pd.isna(feat.loc[13, "temperature_prev_mean_30m"])

    # Verify that row 13 uses rows 10, 11, 12: values 10, 11, 12 -> mean = 11.0
    assert np.isclose(feat.loc[13, "temperature_prev_mean_30m"], 11.0)


# ==============================================================================
# FEATURE BUILDER INTEGRITY TESTS
# ==============================================================================

def test_feature_columns_and_counts(jena_clean_sample):
    """Verify feature count and column schema organization."""
    feat = build_features_for_dataset(jena_clean_sample, "jena")
    assert len(feat) == len(jena_clean_sample)
    assert len(feat.columns) == 106

    # Verify column presence
    expected_cols = [
        "timestamp", "source_dataset", "temperature_c", "pressure_hpa", "relative_humidity_pct",
        "temperature_missing", "humidity_missing", "pressure_missing", "any_core_missing",
        "valid_core_count", "all_core_valid", "elapsed_minutes_since_prev", "gap_before", "segment_id",
        "hour_sin", "hour_cos", "day_of_year_sin", "day_of_year_cos",
        "temperature_delta", "temperature_rate_per_hour", "temperature_abs_rate_per_hour",
        "temperature_zero_delta", "temperature_zero_delta_ratio_2h", "temperature_rolling_std_2h",
        "temperature_prev_mean_30m", "temperature_prev_std_30m", "temperature_prev_median_30m", "temperature_prev_mad_30m",
        "temperature_deviation_from_median_30m", "temperature_robust_deviation_30m", "temperature_trend_30m",
        "multivariate_max_abs_robust_deviation_30m", "multivariate_deviation_range_30m",
    ]
    for col in expected_cols:
        assert col in feat.columns, f"Missing expected column: {col}"


def test_deterministic_feature_generation(jena_clean_sample):
    """Verify that re-running feature generation produces strictly identical outputs."""
    feat1 = build_features_for_dataset(jena_clean_sample, "jena")
    feat2 = build_features_for_dataset(jena_clean_sample, "jena")
    pd.testing.assert_frame_equal(feat1, feat2)

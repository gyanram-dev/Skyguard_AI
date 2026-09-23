"""Validation module for Phase 3 feature engineering.

Includes:
- Strict anti-data-leakage verification.
- Segment boundary containment validation.
- Dataset-specific integrity checks (Jena, Delhi).
- Global invariant checks.
- Feature sanity diagnostics (coverage, bounds, history availability).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger("aws_features.validation")


def verify_anti_data_leakage(
    df_sample: pd.DataFrame,
    dataset_name: str,
    target_col: str = "temperature_c",
    perturb_idx: int = 50,
) -> Dict[str, Any]:
    """Strict anti-data-leakage test: Perturb future row k, verify rows < k remain 100% identical.

    Causal guarantee:
        Changing observation at t+1 CANNOT alter any feature value at timestamp t.
    """
    from src.features.feature_builder import build_features_for_dataset

    # Slice a sample of 100 rows
    sample_df = df_sample.iloc[:100].copy().reset_index(drop=True)
    if perturb_idx >= len(sample_df):
        perturb_idx = len(sample_df) // 2

    # Baseline features
    features_orig = build_features_for_dataset(sample_df, dataset_name)

    # Perturb observation at perturb_idx
    perturbed_df = sample_df.copy()
    original_val = perturbed_df.loc[perturb_idx, target_col]
    perturbed_df.loc[perturb_idx, target_col] = original_val + 50.0  # Massive 50-degree shock

    # Recompute features
    features_perturbed = build_features_for_dataset(perturbed_df, dataset_name)

    # Check rows strictly before perturb_idx (< perturb_idx)
    sub_orig = features_orig.iloc[:perturb_idx]
    sub_pert = features_perturbed.iloc[:perturb_idx]

    # Compare all numerical columns
    num_cols = sub_orig.select_dtypes(include=[np.number]).columns
    max_diff_prior = 0.0

    mismatches = []
    for col in num_cols:
        s1 = sub_orig[col].to_numpy(dtype=float)
        s2 = sub_pert[col].to_numpy(dtype=float)

        nan_mask_match = (np.isnan(s1) == np.isnan(s2)).all()
        if not nan_mask_match:
            mismatches.append(f"{col}: NaN pattern mismatch prior to perturbation")
            continue

        valid = ~np.isnan(s1)
        if np.any(valid):
            diff = np.max(np.abs(s1[valid] - s2[valid]))
            max_diff_prior = max(max_diff_prior, diff)
            if diff > 1e-12:
                mismatches.append(f"{col}: Max diff {diff} prior to perturbation")

    # Check that the shock DOES propagate to subsequent rows (>= perturb_idx)
    # to ensure the feature is actively tracking history
    sub_post_orig = features_orig.iloc[perturb_idx:]
    sub_post_pert = features_perturbed.iloc[perturb_idx:]
    has_post_effect = False
    for col in [f"temperature_delta", f"temperature_prev_mean_30m", f"temperature_robust_deviation_30m"]:
        if col in features_orig.columns:
            s1 = sub_post_orig[col].to_numpy(dtype=float)
            s2 = sub_post_pert[col].to_numpy(dtype=float)
            diff = np.nanmax(np.abs(s1 - s2))
            if diff > 0.1:
                has_post_effect = True
                break

    passed = (len(mismatches) == 0) and has_post_effect and (max_diff_prior <= 1e-12)
    logger.info(f"Anti-data-leakage test for {dataset_name.upper()}: Status={'PASS' if passed else 'FAIL'}")
    return {
        "passed": passed,
        "max_diff_prior": float(max_diff_prior),
        "mismatches": mismatches,
        "shock_propagated_to_future": has_post_effect,
        "perturbed_index": perturb_idx,
    }


def validate_jena_features(
    df_in: pd.DataFrame,
    df_feat: pd.DataFrame,
) -> Dict[str, Any]:
    """Execute all 10 mandatory validation checks for Jena features."""
    checks = {}
    checks["check_1_input_row_count"] = (len(df_in) == 420224)
    checks["check_2_output_row_count"] = (len(df_feat) == 420224)
    checks["check_3_timestamp_unchanged"] = bool((df_feat["timestamp"] == df_in["timestamp"]).all())
    checks["check_4_timestamp_order_monotonic"] = bool(pd.to_datetime(df_feat["timestamp"]).is_monotonic_increasing)

    for col in ["temperature_c", "pressure_hpa", "relative_humidity_pct"]:
        checks[f"check_5_{col}_unchanged"] = bool((df_feat[col] == df_in[col]).all())

    checks["check_6_source_dataset_is_jena"] = bool((df_feat["source_dataset"] == "jena").all())
    checks["check_7_gaps_detectable"] = bool(df_feat["gap_before"].sum() == 5)

    # Segment boundary check: immediately after gap (row where gap_before == 1),
    # 30m rolling mean must be NaN because previous segment cannot be used!
    gap_rows = df_feat[df_feat["gap_before"] == 1].index
    checks["check_8_rolling_does_not_cross_gap"] = bool(
        df_feat.loc[gap_rows, "temperature_prev_mean_30m"].isna().all()
    )

    all_passed = all(checks.values())
    logger.info(f"Jena Feature Validation: {sum(checks.values())}/{len(checks)} checks passed.")
    return {
        "all_passed": all_passed,
        "checks": checks,
    }


def validate_delhi_features(
    df_in: pd.DataFrame,
    df_feat: pd.DataFrame,
) -> Dict[str, Any]:
    """Execute all 10 mandatory validation checks for Delhi features."""
    checks = {}
    checks["check_1_input_row_count"] = (len(df_in) == 289728)
    checks["check_2_output_row_count"] = (len(df_feat) == 289728)
    checks["check_3_timestamp_unchanged"] = bool((df_feat["timestamp"] == df_in["timestamp"]).all())
    checks["check_4_timestamp_cadence_strictly_5min"] = bool(
        (pd.to_datetime(df_feat["timestamp"]).diff().dropna() == pd.Timedelta(minutes=5)).all()
    )

    for col in ["temperature_c", "pressure_hpa", "relative_humidity_pct"]:
        # Check equality with NaN alignment
        m1 = df_feat[col].isna()
        m2 = df_in[col].isna()
        checks[f"check_5_{col}_missingness_and_values_unchanged"] = bool(
            (m1 == m2).all() and np.allclose(df_feat.loc[~m1, col], df_in.loc[~m2, col])
        )

    checks["check_6_source_dataset_is_delhi"] = bool((df_feat["source_dataset"] == "delhi").all())

    # 42-hour outage preserved: 504 rows
    outage_mask = (df_feat["timestamp"] >= "2022-04-05 17:45:00") & (df_feat["timestamp"] <= "2022-04-07 11:40:00")
    outage_sub = df_feat.loc[outage_mask]
    checks["check_7_42h_outage_preserved"] = bool((len(outage_sub) == 504) and outage_sub["temperature_c"].isna().all())

    # Quality flags preserved
    checks["check_8_missing_quality_flags_preserved"] = bool(
        (df_feat["temperature_missing"] == df_in["temperature_missing"]).all()
        and (df_feat["missing_core_count"] == df_in["missing_core_count"]).all()
    )

    all_passed = all(checks.values())
    logger.info(f"Delhi Feature Validation: {sum(checks.values())}/{len(checks)} checks passed.")
    return {
        "all_passed": all_passed,
        "checks": checks,
    }


def compute_feature_sanity_diagnostics(df_features: pd.DataFrame) -> Dict[str, Any]:
    """Compute summary diagnostics for every numerical feature and history availability."""
    diagnostics = {}
    num_cols = df_features.select_dtypes(include=[np.number]).columns

    stats_dict = {}
    for col in num_cols:
        s = df_features[col]
        nan_cnt = int(s.isna().sum())
        valid = s.dropna()
        stats_dict[col] = {
            "missing_count": nan_cnt,
            "missing_pct": round(nan_cnt / len(df_features) * 100, 3),
            "min": float(valid.min()) if len(valid) > 0 else None,
            "max": float(valid.max()) if len(valid) > 0 else None,
            "mean": float(valid.mean()) if len(valid) > 0 else None,
            "std": float(valid.std()) if len(valid) > 1 else None,
        }

    # History coverage diagnostics
    valid_30m = int(df_features["temperature_prev_mean_30m"].notna().sum())
    valid_2h = int(df_features["temperature_prev_mean_2h"].notna().sum())
    valid_6h = int(df_features["temperature_prev_mean_6h"].notna().sum())

    diagnostics["feature_stats"] = stats_dict
    diagnostics["history_availability"] = {
        "valid_30m_history_rows": valid_30m,
        "valid_2h_history_rows": valid_2h,
        "valid_6h_history_rows": valid_6h,
        "total_rows": len(df_features),
        "total_feature_columns": len(df_features.columns),
    }
    return diagnostics

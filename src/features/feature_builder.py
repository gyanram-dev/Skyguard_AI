"""Feature builder orchestrator for AWS causal temporal and multivariate features.

Handles cadence-aware row window mapping, metadata integration, and feature assembly.
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from src.features.multivariate_features import compute_multivariate_features_for_horizon
from src.features.rolling_features import compute_causal_rolling_window_features
from src.features.temporal_features import (
    compute_cyclical_features,
    compute_first_order_dynamics,
    compute_frozen_features,
    compute_gap_and_segments,
)

logger = logging.getLogger("aws_features.builder")

# Semantic horizons and their row count mappings based on dataset cadence
CADENCE_HORIZONS: Dict[str, Dict[str, int]] = {
    "jena": {
        "expected_interval_min": 10,
        "30m": 3,
        "2h": 12,
        "6h": 36,
    },
    "delhi": {
        "expected_interval_min": 5,
        "30m": 6,
        "2h": 24,
        "6h": 72,
    },
}


def build_features_for_dataset(
    df_clean: pd.DataFrame,
    dataset_name: str,
) -> pd.DataFrame:
    """Transform Phase 2 standardized observations into causal ML-ready features.

    Strictly causal: no future observations are ever used.
    """
    ds_key = dataset_name.lower()
    if ds_key not in CADENCE_HORIZONS:
        raise ValueError(f"Unknown dataset '{dataset_name}'. Must be 'jena' or 'delhi'.")

    cfg = CADENCE_HORIZONS[ds_key]
    interval_min = cfg["expected_interval_min"]
    w_30m = cfg["30m"]
    w_2h = cfg["2h"]
    w_6h = cfg["6h"]

    n_rows = len(df_clean)
    logger.info(f"Building features for {dataset_name.upper()} ({n_rows:,} rows, cadence={interval_min}m)...")

    # 1. Timestamps and Gaps
    dt_series = pd.to_datetime(df_clean["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="raise")
    elapsed_min, gap_before, segment_id = compute_gap_and_segments(dt_series, interval_min)

    # 2. Quality context columns
    if ds_key == "jena":
        # Phase 2 established 0 missing core observations for Jena
        temp_missing = pd.Series(0, index=df_clean.index, dtype=int)
        rh_missing = pd.Series(0, index=df_clean.index, dtype=int)
        pres_missing = pd.Series(0, index=df_clean.index, dtype=int)
        any_missing = pd.Series(0, index=df_clean.index, dtype=int)
        missing_count = pd.Series(0, index=df_clean.index, dtype=int)
        valid_core_count = pd.Series(3, index=df_clean.index, dtype=int)
        all_core_valid = pd.Series(1, index=df_clean.index, dtype=int)
    else:
        # Delhi retains Phase 2 quality flags
        temp_missing = df_clean["temperature_missing"].astype(int)
        rh_missing = df_clean["humidity_missing"].astype(int)
        pres_missing = df_clean["pressure_missing"].astype(int)
        any_missing = df_clean["any_core_missing"].astype(int)
        missing_count = df_clean["missing_core_count"].astype(int)
        valid_core_count = 3 - missing_count
        all_core_valid = (valid_core_count == 3).astype(int)

    # 3. Cyclical Temporal Features
    df_cyclical = compute_cyclical_features(dt_series)

    # 4. First-Order Change Dynamics (Delta and Rates)
    t_dyn = compute_first_order_dynamics(df_clean["temperature_c"], elapsed_min, segment_id, "temperature")
    p_dyn = compute_first_order_dynamics(df_clean["pressure_hpa"], elapsed_min, segment_id, "pressure")
    rh_dyn = compute_first_order_dynamics(df_clean["relative_humidity_pct"], elapsed_min, segment_id, "humidity")

    # 5. Frozen Sensor Features
    t_froz = compute_frozen_features(df_clean["temperature_c"], segment_id, w_2h, "temperature")
    p_froz = compute_frozen_features(df_clean["pressure_hpa"], segment_id, w_2h, "pressure")
    rh_froz = compute_frozen_features(df_clean["relative_humidity_pct"], segment_id, w_2h, "humidity")

    # 6. Causal Rolling Baselines & Local Deviations across 30m, 2h, 6h
    # 30-Minute Horizon
    t_30m = compute_causal_rolling_window_features(df_clean["temperature_c"], segment_id, w_30m, "30m", "temperature")
    p_30m = compute_causal_rolling_window_features(df_clean["pressure_hpa"], segment_id, w_30m, "30m", "pressure")
    rh_30m = compute_causal_rolling_window_features(df_clean["relative_humidity_pct"], segment_id, w_30m, "30m", "humidity")
    multi_30m = compute_multivariate_features_for_horizon(
        t_30m["temperature_robust_deviation_30m"],
        p_30m["pressure_robust_deviation_30m"],
        rh_30m["humidity_robust_deviation_30m"],
        "30m",
    )

    # 2-Hour Horizon
    t_2h = compute_causal_rolling_window_features(df_clean["temperature_c"], segment_id, w_2h, "2h", "temperature")
    p_2h = compute_causal_rolling_window_features(df_clean["pressure_hpa"], segment_id, w_2h, "2h", "pressure")
    rh_2h = compute_causal_rolling_window_features(df_clean["relative_humidity_pct"], segment_id, w_2h, "2h", "humidity")
    multi_2h = compute_multivariate_features_for_horizon(
        t_2h["temperature_robust_deviation_2h"],
        p_2h["pressure_robust_deviation_2h"],
        rh_2h["humidity_robust_deviation_2h"],
        "2h",
    )

    # 6-Hour Horizon
    t_6h = compute_causal_rolling_window_features(df_clean["temperature_c"], segment_id, w_6h, "6h", "temperature")
    p_6h = compute_causal_rolling_window_features(df_clean["pressure_hpa"], segment_id, w_6h, "6h", "pressure")
    rh_6h = compute_causal_rolling_window_features(df_clean["relative_humidity_pct"], segment_id, w_6h, "6h", "humidity")
    multi_6h = compute_multivariate_features_for_horizon(
        t_6h["temperature_robust_deviation_6h"],
        p_6h["pressure_robust_deviation_6h"],
        rh_6h["humidity_robust_deviation_6h"],
        "6h",
    )

    # In Section 8: temperature_rolling_std_2h is the std of previous 2h window (< t)
    # This matches temperature_prev_std_2h
    t_rolling_std_2h = t_2h["temperature_prev_std_2h"]
    p_rolling_std_2h = p_2h["pressure_prev_std_2h"]
    rh_rolling_std_2h = rh_2h["humidity_prev_std_2h"]

    # Assemble complete DataFrame in strict recommended column order
    df_features = pd.DataFrame({
        # 1. Base Identification
        "timestamp": df_clean["timestamp"],
        "source_dataset": df_clean["source_dataset"],
        # 2. Raw Core Observations
        "temperature_c": df_clean["temperature_c"],
        "pressure_hpa": df_clean["pressure_hpa"],
        "relative_humidity_pct": df_clean["relative_humidity_pct"],
        # 3. Missing & Quality Metadata
        "temperature_missing": temp_missing,
        "humidity_missing": rh_missing,
        "pressure_missing": pres_missing,
        "any_core_missing": any_missing,
        "missing_core_count": missing_count,
        "valid_core_count": valid_core_count,
        "all_core_valid": all_core_valid,
        # 4. Gap & Segment Metadata
        "elapsed_minutes_since_prev": elapsed_min,
        "gap_before": gap_before,
        "segment_id": segment_id,
        # 5. Cyclical Temporal Features
        "hour_sin": df_cyclical["hour_sin"],
        "hour_cos": df_cyclical["hour_cos"],
        "day_of_year_sin": df_cyclical["day_of_year_sin"],
        "day_of_year_cos": df_cyclical["day_of_year_cos"],
        # 6. First-Order Rate Dynamics
        "temperature_delta": t_dyn["temperature_delta"],
        "temperature_rate_per_hour": t_dyn["temperature_rate_per_hour"],
        "temperature_abs_rate_per_hour": t_dyn["temperature_abs_rate_per_hour"],
        "pressure_delta": p_dyn["pressure_delta"],
        "pressure_rate_per_hour": p_dyn["pressure_rate_per_hour"],
        "pressure_abs_rate_per_hour": p_dyn["pressure_abs_rate_per_hour"],
        "humidity_delta": rh_dyn["humidity_delta"],
        "humidity_rate_per_hour": rh_dyn["humidity_rate_per_hour"],
        "humidity_abs_rate_per_hour": rh_dyn["humidity_abs_rate_per_hour"],
        # 7. Frozen Sensor Features
        "temperature_zero_delta": t_froz["temperature_zero_delta"],
        "pressure_zero_delta": p_froz["pressure_zero_delta"],
        "humidity_zero_delta": rh_froz["humidity_zero_delta"],
        "temperature_zero_delta_ratio_2h": t_froz["temperature_zero_delta_ratio_2h"],
        "pressure_zero_delta_ratio_2h": p_froz["pressure_zero_delta_ratio_2h"],
        "humidity_zero_delta_ratio_2h": rh_froz["humidity_zero_delta_ratio_2h"],
        "temperature_rolling_std_2h": t_rolling_std_2h,
        "pressure_rolling_std_2h": p_rolling_std_2h,
        "humidity_rolling_std_2h": rh_rolling_std_2h,
        # 8. 30-Minute Horizon Baselines, Deviations, Trends, Multivariate
        "temperature_prev_mean_30m": t_30m["temperature_prev_mean_30m"],
        "temperature_prev_std_30m": t_30m["temperature_prev_std_30m"],
        "temperature_prev_median_30m": t_30m["temperature_prev_median_30m"],
        "temperature_prev_mad_30m": t_30m["temperature_prev_mad_30m"],
        "temperature_deviation_from_median_30m": t_30m["temperature_deviation_from_median_30m"],
        "temperature_robust_deviation_30m": t_30m["temperature_robust_deviation_30m"],
        "temperature_trend_30m": t_30m["temperature_trend_30m"],
        "pressure_prev_mean_30m": p_30m["pressure_prev_mean_30m"],
        "pressure_prev_std_30m": p_30m["pressure_prev_std_30m"],
        "pressure_prev_median_30m": p_30m["pressure_prev_median_30m"],
        "pressure_prev_mad_30m": p_30m["pressure_prev_mad_30m"],
        "pressure_deviation_from_median_30m": p_30m["pressure_deviation_from_median_30m"],
        "pressure_robust_deviation_30m": p_30m["pressure_robust_deviation_30m"],
        "pressure_trend_30m": p_30m["pressure_trend_30m"],
        "humidity_prev_mean_30m": rh_30m["humidity_prev_mean_30m"],
        "humidity_prev_std_30m": rh_30m["humidity_prev_std_30m"],
        "humidity_prev_median_30m": rh_30m["humidity_prev_median_30m"],
        "humidity_prev_mad_30m": rh_30m["humidity_prev_mad_30m"],
        "humidity_deviation_from_median_30m": rh_30m["humidity_deviation_from_median_30m"],
        "humidity_robust_deviation_30m": rh_30m["humidity_robust_deviation_30m"],
        "humidity_trend_30m": rh_30m["humidity_trend_30m"],
        "multivariate_max_abs_robust_deviation_30m": multi_30m["multivariate_max_abs_robust_deviation_30m"],
        "multivariate_deviation_range_30m": multi_30m["multivariate_deviation_range_30m"],
        # 9. 2-Hour Horizon Baselines, Deviations, Trends, Multivariate
        "temperature_prev_mean_2h": t_2h["temperature_prev_mean_2h"],
        "temperature_prev_std_2h": t_2h["temperature_prev_std_2h"],
        "temperature_prev_median_2h": t_2h["temperature_prev_median_2h"],
        "temperature_prev_mad_2h": t_2h["temperature_prev_mad_2h"],
        "temperature_deviation_from_median_2h": t_2h["temperature_deviation_from_median_2h"],
        "temperature_robust_deviation_2h": t_2h["temperature_robust_deviation_2h"],
        "temperature_trend_2h": t_2h["temperature_trend_2h"],
        "pressure_prev_mean_2h": p_2h["pressure_prev_mean_2h"],
        "pressure_prev_std_2h": p_2h["pressure_prev_std_2h"],
        "pressure_prev_median_2h": p_2h["pressure_prev_median_2h"],
        "pressure_prev_mad_2h": p_2h["pressure_prev_mad_2h"],
        "pressure_deviation_from_median_2h": p_2h["pressure_deviation_from_median_2h"],
        "pressure_robust_deviation_2h": p_2h["pressure_robust_deviation_2h"],
        "pressure_trend_2h": p_2h["pressure_trend_2h"],
        "humidity_prev_mean_2h": rh_2h["humidity_prev_mean_2h"],
        "humidity_prev_std_2h": rh_2h["humidity_prev_std_2h"],
        "humidity_prev_median_2h": rh_2h["humidity_prev_median_2h"],
        "humidity_prev_mad_2h": rh_2h["humidity_prev_mad_2h"],
        "humidity_deviation_from_median_2h": rh_2h["humidity_deviation_from_median_2h"],
        "humidity_robust_deviation_2h": rh_2h["humidity_robust_deviation_2h"],
        "humidity_trend_2h": rh_2h["humidity_trend_2h"],
        "multivariate_max_abs_robust_deviation_2h": multi_2h["multivariate_max_abs_robust_deviation_2h"],
        "multivariate_deviation_range_2h": multi_2h["multivariate_deviation_range_2h"],
        # 10. 6-Hour Horizon Baselines, Deviations, Trends, Multivariate
        "temperature_prev_mean_6h": t_6h["temperature_prev_mean_6h"],
        "temperature_prev_std_6h": t_6h["temperature_prev_std_6h"],
        "temperature_prev_median_6h": t_6h["temperature_prev_median_6h"],
        "temperature_prev_mad_6h": t_6h["temperature_prev_mad_6h"],
        "temperature_deviation_from_median_6h": t_6h["temperature_deviation_from_median_6h"],
        "temperature_robust_deviation_6h": t_6h["temperature_robust_deviation_6h"],
        "temperature_trend_6h": t_6h["temperature_trend_6h"],
        "pressure_prev_mean_6h": p_6h["pressure_prev_mean_6h"],
        "pressure_prev_std_6h": p_6h["pressure_prev_std_6h"],
        "pressure_prev_median_6h": p_6h["pressure_prev_median_6h"],
        "pressure_prev_mad_6h": p_6h["pressure_prev_mad_6h"],
        "pressure_deviation_from_median_6h": p_6h["pressure_deviation_from_median_6h"],
        "pressure_robust_deviation_6h": p_6h["pressure_robust_deviation_6h"],
        "pressure_trend_6h": p_6h["pressure_trend_6h"],
        "humidity_prev_mean_6h": rh_6h["humidity_prev_mean_6h"],
        "humidity_prev_std_6h": rh_6h["humidity_prev_std_6h"],
        "humidity_prev_median_6h": rh_6h["humidity_prev_median_6h"],
        "humidity_prev_mad_6h": rh_6h["humidity_prev_mad_6h"],
        "humidity_deviation_from_median_6h": rh_6h["humidity_deviation_from_median_6h"],
        "humidity_robust_deviation_6h": rh_6h["humidity_robust_deviation_6h"],
        "humidity_trend_6h": rh_6h["humidity_trend_6h"],
        "multivariate_max_abs_robust_deviation_6h": multi_6h["multivariate_max_abs_robust_deviation_6h"],
        "multivariate_deviation_range_6h": multi_6h["multivariate_deviation_range_6h"],
    })

    assert len(df_features) == n_rows, f"Row count mismatch: {len(df_features)} != {n_rows}"
    logger.info(f"Features successfully built for {dataset_name.upper()}: {len(df_features.columns)} columns.")
    return df_features

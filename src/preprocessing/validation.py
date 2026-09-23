"""Automated validation module for Phase 2 data preprocessing.

Enforces all mandatory checks for Jena, Delhi, and Global invariants.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger("aws_preprocessing.validation")


def validate_jena_preprocessing(
    raw_df: pd.DataFrame,
    clean_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Execute all 11 mandatory validation tests for Jena Climate processed data."""
    results = {}

    # 1. Raw row count = 420,551
    results["check_1_raw_row_count"] = (len(raw_df) == 420551)
    # 2. Processed row count = 420,224
    results["check_2_processed_row_count"] = (len(clean_df) == 420224)
    # 3. Exactly 327 redundant duplicate rows removed
    results["check_3_duplicates_removed_count"] = (len(raw_df) - len(clean_df) == 327)

    dt_series = pd.to_datetime(clean_df["timestamp"], format="%Y-%m-%d %H:%M:%S")
    # 4. Processed timestamps are unique
    results["check_4_timestamps_unique"] = bool(dt_series.is_unique)
    # 5. Processed timestamps are sorted ascending
    results["check_5_timestamps_sorted_ascending"] = bool(dt_series.is_monotonic_increasing)

    # 6. Genuine timestamp gaps remain (at least 5 known gaps > 10 min)
    diffs = dt_series.diff()
    gaps_gt_10min = (diffs > pd.Timedelta(minutes=10)).sum()
    results["check_6_genuine_timestamp_gaps_remain"] = bool(gaps_gt_10min == 5)

    # 7. No interpolation occurred (max gap is still 3 days 2h 20m)
    max_gap = diffs.max()
    results["check_7_no_interpolation_occurred"] = bool(max_gap == pd.Timedelta(days=3, hours=2, minutes=20))

    # 8. No missing core values were artificially created (remains 0)
    core_cols = ["temperature_c", "pressure_hpa", "relative_humidity_pct"]
    nan_count = int(clean_df[core_cols].isna().sum().sum())
    results["check_8_no_missing_values_created"] = (nan_count == 0)

    # 9. Temperature values not clipped (min: -23.01, max: 37.28)
    t_min = float(clean_df["temperature_c"].min())
    t_max = float(clean_df["temperature_c"].max())
    raw_t_min = float(raw_df["T (degC)"].min())
    raw_t_max = float(raw_df["T (degC)"].max())
    results["check_9_temperature_not_clipped"] = bool(np.isclose(t_min, raw_t_min) and np.isclose(t_max, raw_t_max))

    # 10. Pressure values not clipped (min: 913.60, max: 1015.35)
    p_min = float(clean_df["pressure_hpa"].min())
    p_max = float(clean_df["pressure_hpa"].max())
    raw_p_min = float(raw_df["p (mbar)"].min())
    raw_p_max = float(raw_df["p (mbar)"].max())
    results["check_10_pressure_not_clipped"] = bool(np.isclose(p_min, raw_p_min) and np.isclose(p_max, raw_p_max))

    # 11. Humidity values not clipped (min: 12.95, max: 100.0)
    h_min = float(clean_df["relative_humidity_pct"].min())
    h_max = float(clean_df["relative_humidity_pct"].max())
    raw_h_min = float(raw_df["rh (%)"].min())
    raw_h_max = float(raw_df["rh (%)"].max())
    results["check_11_humidity_not_clipped"] = bool(np.isclose(h_min, raw_h_min) and np.isclose(h_max, raw_h_max))

    all_passed = all(results.values())
    logger.info(f"Jena validation: {sum(results.values())}/11 tests passed. Status: {'PASS' if all_passed else 'FAIL'}")
    return {
        "all_passed": all_passed,
        "checks": results,
    }


def validate_delhi_preprocessing(
    raw_df: pd.DataFrame,
    clean_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Execute all 14 mandatory validation tests for Delhi-NCR AWS processed data."""
    results = {}

    # 1. Raw row count = 289,728
    results["check_1_raw_row_count"] = (len(raw_df) == 289728)
    # 2. Processed row count = 289,728
    results["check_2_processed_row_count"] = (len(clean_df) == 289728)
    # 3. No timestamps removed
    results["check_3_no_timestamps_removed"] = (len(clean_df) == len(raw_df))

    dt_series = pd.to_datetime(clean_df["timestamp"], format="%Y-%m-%d %H:%M:%S")
    # 4. Timestamps are unique
    results["check_4_timestamps_unique"] = bool(dt_series.is_unique)
    # 5. Timestamp cadence remains 5 minutes
    diffs = dt_series.diff().dropna()
    results["check_5_cadence_strictly_5min"] = bool((diffs == pd.Timedelta(minutes=5)).all())

    # 6. Original missing counts are preserved
    t_nan = int(clean_df["temperature_c"].isna().sum())
    h_nan = int(clean_df["relative_humidity_pct"].isna().sum())
    p_nan = int(clean_df["pressure_hpa"].isna().sum())
    results["check_6_missing_counts_preserved"] = (t_nan == 807 and h_nan == 807 and p_nan == 811)

    # 7. temperature_missing is correct
    t_flag_correct = bool((clean_df["temperature_missing"] == clean_df["temperature_c"].isna().astype(int)).all())
    results["check_7_temperature_missing_correct"] = t_flag_correct

    # 8. humidity_missing is correct
    h_flag_correct = bool((clean_df["humidity_missing"] == clean_df["relative_humidity_pct"].isna().astype(int)).all())
    results["check_8_humidity_missing_correct"] = h_flag_correct

    # 9. pressure_missing is correct
    p_flag_correct = bool((clean_df["pressure_missing"] == clean_df["pressure_hpa"].isna().astype(int)).all())
    results["check_9_pressure_missing_correct"] = p_flag_correct

    # 10. any_core_missing is correct
    expected_any = (
        (clean_df["temperature_missing"] == 1)
        | (clean_df["humidity_missing"] == 1)
        | (clean_df["pressure_missing"] == 1)
    ).astype(int)
    results["check_10_any_core_missing_correct"] = bool((clean_df["any_core_missing"] == expected_any).all())

    # 11. missing_core_count is correct
    expected_count = clean_df["temperature_missing"] + clean_df["humidity_missing"] + clean_df["pressure_missing"]
    results["check_11_missing_core_count_correct"] = bool((clean_df["missing_core_count"] == expected_count).all())

    # 12. 42-hour outage remains missing (504 consecutive missing steps from 2022-04-05 17:45 to 2022-04-07 11:40)
    outage_mask = (clean_df["timestamp"] >= "2022-04-05 17:45:00") & (clean_df["timestamp"] <= "2022-04-07 11:40:00")
    outage_sub = clean_df.loc[outage_mask, ["temperature_c", "pressure_hpa", "relative_humidity_pct"]]
    results["check_12_42h_outage_preserved"] = bool((len(outage_sub) == 504) and (outage_sub.isna().all().all()))

    # 13. Four suspicious negative temperatures remain unchanged
    neg_sub = clean_df[clean_df["temperature_c"] < 0]
    expected_neg_indices = [1162, 1171, 1173, 1262]
    results["check_13_negative_temps_preserved"] = bool(
        len(neg_sub) == 4 and list(neg_sub.index) == expected_neg_indices
    )

    # 14. Pressure values remain unchanged (compare non-null values with raw)
    clean_p_valid = clean_df["pressure_hpa"].dropna()
    raw_p_valid = pd.to_numeric(raw_df["Atm_Pres"], errors="coerce").dropna()
    results["check_14_pressure_values_unchanged"] = bool(np.allclose(clean_p_valid, raw_p_valid))

    all_passed = all(results.values())
    logger.info(f"Delhi validation: {sum(results.values())}/14 tests passed. Status: {'PASS' if all_passed else 'FAIL'}")
    return {
        "all_passed": all_passed,
        "checks": results,
    }


def validate_global_invariants(
    pre_hashes: Dict[str, str],
    post_hashes: Dict[str, str],
) -> Dict[str, Any]:
    """Execute Global Invariant tests."""
    results = {}
    for name in pre_hashes:
        results[f"raw_hash_unchanged_{name}"] = bool(pre_hashes[name] == post_hashes[name])

    all_passed = all(results.values())
    logger.info(f"Global invariants: Status: {'PASS' if all_passed else 'FAIL'}")
    return {
        "all_passed": all_passed,
        "checks": results,
    }

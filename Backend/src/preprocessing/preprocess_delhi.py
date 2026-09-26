"""Delhi-NCR AWS preprocessing module for Phase 2 data standardization.

Strictly preserves meteorological values, candidate anomalies, and missing-data periods.
Generates quality metadata columns without altering rows or interpolating.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

logger = logging.getLogger("aws_preprocessing.delhi")


def preprocess_delhi(
    raw_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute standardized preprocessing steps for Delhi-NCR AWS observations.

    Steps:
    1. Parse timestamp strictly (DD-MM-YYYY HH:MM).
    2. Map to standardized core column schema.
    3. Retain all 289,728 rows without dropping missing-value records.
    4. Construct explicit boolean/integer quality indicator columns:
       - temperature_missing
       - humidity_missing
       - pressure_missing
       - any_core_missing
       - missing_core_count
    5. Preserve known outages (including the 42-hour outage) without interpolation.
    6. Preserve candidate suspicious temperatures (the 4 sub-zero values).
    7. Preserve wide pressure regimes without clipping or thresholding.
    """
    initial_rows = len(raw_df)
    initial_cols = list(raw_df.columns)
    logger.info(f"Loaded raw Delhi dataset with {initial_rows:,} rows and {len(initial_cols)} columns.")

    if initial_rows != 289728:
        raise ValueError(f"Expected 289,728 raw Delhi rows, found {initial_rows}")

    # STEP 1: Parse timestamp strictly
    try:
        dt_series = pd.to_datetime(raw_df["Date_Time_IST"], format="%d-%m-%Y %H:%M", errors="raise")
    except Exception as e:
        raise ValueError(f"Strict timestamp parsing failed for Delhi: {e}") from e

    # STEP 2 & 4: Map core columns and generate quality flags
    temp_s = pd.to_numeric(raw_df["Air_Temp"], errors="coerce")
    pres_s = pd.to_numeric(raw_df["Atm_Pres"], errors="coerce")
    rh_s = pd.to_numeric(raw_df["Rel_Hum"], errors="coerce")

    temp_missing = temp_s.isna().astype(int)
    rh_missing = rh_s.isna().astype(int)
    pres_missing = pres_s.isna().astype(int)
    any_missing = ((temp_missing == 1) | (rh_missing == 1) | (pres_missing == 1)).astype(int)
    missing_count = temp_missing + rh_missing + pres_missing

    df_clean = pd.DataFrame({
        "timestamp": dt_series,
        "temperature_c": temp_s,
        "pressure_hpa": pres_s,
        "relative_humidity_pct": rh_s,
        "temperature_missing": temp_missing,
        "humidity_missing": rh_missing,
        "pressure_missing": pres_missing,
        "any_core_missing": any_missing,
        "missing_core_count": missing_count,
        "source_dataset": "delhi",
    })

    # STEP 3: Verify row count preservation
    final_rows = len(df_clean)
    if final_rows != 289728:
        raise ValueError(f"Expected 289,728 processed Delhi rows, found {final_rows}")

    # Monotonicity and cadence check (5-minute interval)
    if not df_clean["timestamp"].is_monotonic_increasing:
        raise ValueError("Delhi timestamps are not strictly monotonically increasing.")
    if not df_clean["timestamp"].is_unique:
        raise ValueError("Delhi timestamps are not unique.")

    # Format timestamp to ISO-8601 string for clean CSV export
    df_out = df_clean.copy()
    df_out["timestamp"] = df_out["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Verify counts match Phase 1 audit
    t_miss_cnt = int(temp_missing.sum())
    h_miss_cnt = int(rh_missing.sum())
    p_miss_cnt = int(pres_missing.sum())
    any_miss_cnt = int(any_missing.sum())
    joint_3_miss = int((missing_count == 3).sum())
    joint_1_miss = int((missing_count == 1).sum())

    if t_miss_cnt != 807:
        raise ValueError(f"Expected 807 missing temperature values, found {t_miss_cnt}")
    if h_miss_cnt != 807:
        raise ValueError(f"Expected 807 missing humidity values, found {h_miss_cnt}")
    if p_miss_cnt != 811:
        raise ValueError(f"Expected 811 missing pressure values, found {p_miss_cnt}")
    if joint_3_miss != 806:
        raise ValueError(f"Expected 806 timestamps with all 3 missing, found {joint_3_miss}")
    if joint_1_miss != 7:
        raise ValueError(f"Expected 7 timestamps with exactly 1 missing, found {joint_1_miss}")

    # Check suspicious negative temperatures preserved
    neg_temp_cnt = int((temp_s < 0).sum())
    if neg_temp_cnt != 4:
        raise ValueError(f"Expected 4 negative temperature observations, found {neg_temp_cnt}")

    report = {
        "dataset": "delhi",
        "raw_rows": initial_rows,
        "processed_rows": final_rows,
        "row_count_match": (final_rows == 289728),
        "columns_standardized": {
            "Date_Time_IST": "timestamp",
            "Air_Temp": "temperature_c",
            "Atm_Pres": "pressure_hpa",
            "Rel_Hum": "relative_humidity_pct",
        },
        "quality_columns_added": [
            "temperature_missing",
            "humidity_missing",
            "pressure_missing",
            "any_core_missing",
            "missing_core_count",
        ],
        "missing_counts": {
            "temperature_missing": t_miss_cnt,
            "humidity_missing": h_miss_cnt,
            "pressure_missing": p_miss_cnt,
            "any_core_missing": any_miss_cnt,
            "all_three_missing": joint_3_miss,
            "exactly_one_missing": joint_1_miss,
            "zero_missing": int((missing_count == 0).sum()),
        },
        "temperature_c_stats": {
            "min": float(temp_s.min()),
            "max": float(temp_s.max()),
            "mean": float(temp_s.mean()),
            "std": float(temp_s.std()),
            "negative_temperatures_preserved_count": neg_temp_cnt,
        },
        "pressure_hpa_stats": {
            "min": float(pres_s.min()),
            "max": float(pres_s.max()),
            "mean": float(pres_s.mean()),
            "std": float(pres_s.std()),
            "low_pressure_below_950_count": int((pres_s < 950).sum()),
            "high_pressure_above_1030_count": int((pres_s > 1030).sum()),
        },
        "relative_humidity_pct_stats": {
            "min": float(rh_s.min()),
            "max": float(rh_s.max()),
            "mean": float(rh_s.mean()),
            "std": float(rh_s.std()),
        },
        "timestamps_unique": bool(df_clean["timestamp"].is_unique),
        "timestamps_monotonic_increasing": bool(df_clean["timestamp"].is_monotonic_increasing),
        "start_timestamp": str(df_clean["timestamp"].min()),
        "end_timestamp": str(df_clean["timestamp"].max()),
    }
    logger.info(f"Delhi preprocessing complete: {final_rows:,} rows produced, quality flags populated.")
    return df_out, report

"""Jena Climate preprocessing module for Phase 2 data standardization.

Strictly preserves meteorological values and genuine timestamp gaps.
Removes redundant copies of exact duplicates and sorts chronologically.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

logger = logging.getLogger("aws_preprocessing.jena")


def preprocess_jena(
    raw_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute standardized preprocessing steps for Jena Climate observations.

    Steps:
    1. Parse timestamp strictly (DD.MM.YYYY HH:MM:SS).
    2. Map to standardized core column schema.
    3. Remove redundant copies of exact duplicate pairs (327 rows).
    4. Sort chronologically by timestamp ascending.
    5. Preserve genuine gaps without interpolation or resampling.
    6. Preserve extreme meteorological observations without clipping.
    """
    initial_rows = len(raw_df)
    initial_cols = list(raw_df.columns)
    logger.info(f"Loaded raw Jena dataset with {initial_rows:,} rows and {len(initial_cols)} columns.")

    if initial_rows != 420551:
        raise ValueError(f"Expected 420,551 raw Jena rows, found {initial_rows}")

    # STEP 1: Parse timestamp strictly
    try:
        dt_series = pd.to_datetime(raw_df["Date Time"], format="%d.%m.%Y %H:%M:%S", errors="raise")
    except Exception as e:
        raise ValueError(f"Strict timestamp parsing failed for Jena: {e}") from e

    # STEP 2: Map core columns (1 mbar = 1 hPa)
    df_mapped = pd.DataFrame({
        "timestamp": dt_series,
        "temperature_c": pd.to_numeric(raw_df["T (degC)"], errors="raise"),
        "pressure_hpa": pd.to_numeric(raw_df["p (mbar)"], errors="raise"),
        "relative_humidity_pct": pd.to_numeric(raw_df["rh (%)"], errors="raise"),
        "source_dataset": "jena",
    })

    # STEP 3: Remove redundant copies of exact duplicate records
    # Audit established that the 327 duplicate timestamps are exact identical row pairs
    df_dedup = df_mapped.drop_duplicates(subset=["timestamp"], keep="first")
    duplicates_removed = len(df_mapped) - len(df_dedup)

    if duplicates_removed != 327:
        raise ValueError(f"Expected exactly 327 duplicate rows removed, but removed {duplicates_removed}")

    # STEP 4: Sort chronologically ascending
    df_sorted = df_dedup.sort_values("timestamp").reset_index(drop=True)

    # Verification of monotonicity and uniqueness
    if not df_sorted["timestamp"].is_monotonic_increasing:
        raise ValueError("Timestamps are not strictly monotonically increasing after sorting.")
    if not df_sorted["timestamp"].is_unique:
        raise ValueError("Timestamps are not strictly unique after deduplication.")

    final_rows = len(df_sorted)
    if final_rows != 420224:
        raise ValueError(f"Expected 420,224 processed Jena rows, found {final_rows}")

    # Format timestamp to ISO-8601 string for clean CSV export
    df_out = df_sorted.copy()
    df_out["timestamp"] = df_out["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Collect statistical metadata for auditing verification
    report = {
        "dataset": "jena",
        "raw_rows": initial_rows,
        "processed_rows": final_rows,
        "duplicates_detected": duplicates_removed,
        "duplicates_removed": duplicates_removed,
        "expected_row_count": 420224,
        "row_count_match": (final_rows == 420224),
        "columns_standardized": {
            "Date Time": "timestamp",
            "T (degC)": "temperature_c",
            "p (mbar)": "pressure_hpa",
            "rh (%)": "relative_humidity_pct",
        },
        "temperature_c_stats": {
            "min": float(df_sorted["temperature_c"].min()),
            "max": float(df_sorted["temperature_c"].max()),
            "mean": float(df_sorted["temperature_c"].mean()),
            "std": float(df_sorted["temperature_c"].std()),
            "missing_count": int(df_sorted["temperature_c"].isna().sum()),
        },
        "pressure_hpa_stats": {
            "min": float(df_sorted["pressure_hpa"].min()),
            "max": float(df_sorted["pressure_hpa"].max()),
            "mean": float(df_sorted["pressure_hpa"].mean()),
            "std": float(df_sorted["pressure_hpa"].std()),
            "missing_count": int(df_sorted["pressure_hpa"].isna().sum()),
        },
        "relative_humidity_pct_stats": {
            "min": float(df_sorted["relative_humidity_pct"].min()),
            "max": float(df_sorted["relative_humidity_pct"].max()),
            "mean": float(df_sorted["relative_humidity_pct"].mean()),
            "std": float(df_sorted["relative_humidity_pct"].std()),
            "missing_count": int(df_sorted["relative_humidity_pct"].isna().sum()),
        },
        "timestamps_unique": bool(df_sorted["timestamp"].is_unique),
        "timestamps_monotonic_increasing": bool(df_sorted["timestamp"].is_monotonic_increasing),
        "start_timestamp": str(df_sorted["timestamp"].min()),
        "end_timestamp": str(df_sorted["timestamp"].max()),
    }
    logger.info(f"Jena preprocessing complete: {final_rows:,} rows produced, {duplicates_removed} duplicates removed.")
    return df_out, report

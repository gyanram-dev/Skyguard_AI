"""Combine z-score and IQR views with Data-Quality context.

Per-row logic:
- ml_eligible == false  -> baseline_status DATA_QUALITY_EXCLUDED, all
  scores/flags NaN. Communication gaps never become anomalies here.
- otherwise             -> compute both views (NaN where history or input
  is insufficient), derive combined counts/flag/reason.

Combined fields:
- statistical_flags_available: variables with >= 1 computable view (0-3)
- statistical_anomaly_count:   variables with any flag == 1
- statistical_baseline_flag:   1 if count >= 1; 0 if available >= 1 and
  count == 0; NaN if available == 0
- statistical_baseline_reason: firing components, or
  multi_variable_statistical when > 1 variable fires, or
  insufficient_history / missing_input when nothing is computable.

No root-cause labels. No calibration. No ensemble scores.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.baseline.iqr_baseline import IQR_FACTOR, compute_iqr_flags
from src.baseline.zscore_baseline import (
    BASELINE_VARIABLES,
    Z_THRESHOLD,
    compute_zscore_flags,
    compute_zscores,
)
from src.features.feature_builder import CADENCE_HORIZONS

STATUS_EXCLUDED = "DATA_QUALITY_EXCLUDED"
STATUS_INSUFFICIENT = "INSUFFICIENT_HISTORY"
STATUS_COMPUTED = "COMPUTED"

BASELINE_COLUMNS = [
    "timestamp",
    "source_dataset",
    "temperature_c",
    "pressure_hpa",
    "relative_humidity_pct",
    "temperature_zscore_baseline",
    "pressure_zscore_baseline",
    "humidity_zscore_baseline",
    "temperature_zscore_flag",
    "pressure_zscore_flag",
    "humidity_zscore_flag",
    "temperature_iqr_flag",
    "pressure_iqr_flag",
    "humidity_iqr_flag",
    "statistical_flags_available",
    "statistical_anomaly_count",
    "statistical_baseline_flag",
    "statistical_baseline_reason",
    "baseline_status",
]


def baseline_window_rows(dataset_name: str, cadence_min: float | None = None) -> int:
    """2-hour causal window in rows for the dataset's native cadence."""
    if cadence_min is not None:
        from src.features.feature_builder import horizons_for_cadence

        return int(horizons_for_cadence(cadence_min)["2h"])
    key = dataset_name.lower()
    if key not in CADENCE_HORIZONS:
        raise ValueError(f"Unknown dataset '{dataset_name}'. Must be 'jena' or 'delhi'.")
    return int(CADENCE_HORIZONS[key]["2h"])


def build_statistical_baseline(
    df_feat: pd.DataFrame,
    df_quality: pd.DataFrame,
    dataset_name: str,
    z_threshold: float = Z_THRESHOLD,
    iqr_factor: float = IQR_FACTOR,
    cadence_min: float | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Build the combined statistical baseline. Return (baseline_df, summary)."""
    key = dataset_name.lower()
    if len(df_feat) != len(df_quality):
        raise ValueError(
            f"Feature/quality row mismatch: {len(df_feat)} != {len(df_quality)}"
        )
    n = len(df_feat)
    window_rows = baseline_window_rows(key, cadence_min)

    zscores = compute_zscores(df_feat)
    zflags = compute_zscore_flags(zscores, z_threshold)
    qflags = compute_iqr_flags(df_feat, window_rows, iqr_factor)

    eligible = df_quality["ml_eligible"].to_numpy(dtype=int) == 1
    quality_status = df_quality["quality_status"].astype(str).to_numpy()

    zf = {v: zflags[f"{v}_zscore_flag"].to_numpy(dtype=float) for v in BASELINE_VARIABLES}
    qf = {v: qflags[f"{v}_iqr_flag"].to_numpy(dtype=float) for v in BASELINE_VARIABLES}

    available = np.zeros(n, dtype=int)
    anomaly_count = np.zeros(n, dtype=int)
    for var in BASELINE_VARIABLES:
        z_known = ~np.isnan(zf[var])
        q_known = ~np.isnan(qf[var])
        var_available = z_known | q_known
        var_anomaly = ((zf[var] == 1.0) & z_known) | ((qf[var] == 1.0) & q_known)
        available += var_available.astype(int)
        anomaly_count += (var_anomaly & var_available).astype(int)

    combined_flag = np.full(n, np.nan, dtype=float)
    combined_flag[(anomaly_count >= 1)] = 1.0
    combined_flag[(available >= 1) & (anomaly_count == 0)] = 0.0

    # Reasons (deterministic variable order, z before iqr).
    reasons: list[str] = []
    for i in range(n):
        if not eligible[i]:
            reasons.append(f"data_quality_excluded:{quality_status[i]}")
            continue
        if available[i] == 0:
            obs_missing = bool(df_feat[["temperature_c", "pressure_hpa", "relative_humidity_pct"]].iloc[i].isna().any())
            reasons.append("missing_input" if obs_missing else "insufficient_history")
            continue
        parts: list[str] = []
        for var in BASELINE_VARIABLES:
            if not np.isnan(zf[var][i]) and zf[var][i] == 1.0:
                parts.append(f"{var}_zscore")
            if not np.isnan(qf[var][i]) and qf[var][i] == 1.0:
                parts.append(f"{var}_iqr")
        firing_vars = sorted({p.split("_")[0] for p in parts})
        if len(firing_vars) > 1:
            reasons.append("multi_variable_statistical;" + ";".join(parts))
        elif parts:
            reasons.append(";".join(parts))
        else:
            reasons.append("within_baseline_bounds")

    status = np.full(n, STATUS_COMPUTED, dtype=object)
    status[~eligible] = STATUS_EXCLUDED
    status[eligible & (available == 0)] = STATUS_INSUFFICIENT

    # Excluded rows carry no statistical decision at all.
    def _mask_excluded(arr: np.ndarray) -> np.ndarray:
        out = arr.astype(float).copy()
        out[~eligible] = np.nan
        return out

    df_out = pd.DataFrame(
        {
            "timestamp": df_feat["timestamp"].values,
            "source_dataset": df_feat["source_dataset"].values,
            "temperature_c": pd.to_numeric(df_feat["temperature_c"], errors="coerce").values,
            "pressure_hpa": pd.to_numeric(df_feat["pressure_hpa"], errors="coerce").values,
            "relative_humidity_pct": pd.to_numeric(df_feat["relative_humidity_pct"], errors="coerce").values,
            "temperature_zscore_baseline": _mask_excluded(zscores["temperature_zscore_baseline"].to_numpy(dtype=float)),
            "pressure_zscore_baseline": _mask_excluded(zscores["pressure_zscore_baseline"].to_numpy(dtype=float)),
            "humidity_zscore_baseline": _mask_excluded(zscores["humidity_zscore_baseline"].to_numpy(dtype=float)),
            "temperature_zscore_flag": _mask_excluded(zf["temperature"]),
            "pressure_zscore_flag": _mask_excluded(zf["pressure"]),
            "humidity_zscore_flag": _mask_excluded(zf["humidity"]),
            "temperature_iqr_flag": _mask_excluded(qf["temperature"]),
            "pressure_iqr_flag": _mask_excluded(qf["pressure"]),
            "humidity_iqr_flag": _mask_excluded(qf["humidity"]),
            "statistical_flags_available": np.where(eligible, available, 0).astype(int),
            "statistical_anomaly_count": np.where(eligible, anomaly_count, 0).astype(int),
            "statistical_baseline_flag": np.where(eligible, combined_flag, np.nan).astype(float),
            "statistical_baseline_reason": reasons,
            "baseline_status": status,
        }
    )
    assert list(df_out.columns) == BASELINE_COLUMNS
    assert len(df_out) == n

    summary = summarize_baseline(df_out, key, window_rows, z_threshold, iqr_factor)
    return df_out, summary


def summarize_baseline(
    df_out: pd.DataFrame,
    dataset: str,
    window_rows: int,
    z_threshold: float,
    iqr_factor: float,
) -> dict:
    """Descriptive counts only. No precision/recall/F1 (no ground truth)."""
    n = len(df_out)
    flag = df_out["statistical_baseline_flag"].to_numpy(dtype=float)
    status = df_out["baseline_status"].astype(str)
    z_any = ((df_out["temperature_zscore_flag"] == 1.0)
             | (df_out["pressure_zscore_flag"] == 1.0)
             | (df_out["humidity_zscore_flag"] == 1.0)).sum()
    q_any = ((df_out["temperature_iqr_flag"] == 1.0)
             | (df_out["pressure_iqr_flag"] == 1.0)
             | (df_out["humidity_iqr_flag"] == 1.0)).sum()
    both = (((df_out["temperature_zscore_flag"] == 1.0) & (df_out["temperature_iqr_flag"] == 1.0))
            | ((df_out["pressure_zscore_flag"] == 1.0) & (df_out["pressure_iqr_flag"] == 1.0))
            | ((df_out["humidity_zscore_flag"] == 1.0) & (df_out["humidity_iqr_flag"] == 1.0))).sum()
    flagged = int((flag == 1.0).sum())
    usable = int(((flag == 0.0) | (flag == 1.0)).sum())
    return {
        "dataset": dataset,
        "rows": int(n),
        "window_rows_2h": int(window_rows),
        "z_threshold": float(z_threshold),
        "iqr_factor": float(iqr_factor),
        "usable_rows": usable,
        "insufficient_history_rows": int((status == STATUS_INSUFFICIENT).sum()),
        "excluded_by_data_quality_rows": int((status == STATUS_EXCLUDED).sum()),
        "missing_input_rows": int((df_out["statistical_baseline_reason"] == "missing_input").sum()),
        "temperature_zscore_flags": int((df_out["temperature_zscore_flag"] == 1.0).sum()),
        "pressure_zscore_flags": int((df_out["pressure_zscore_flag"] == 1.0).sum()),
        "humidity_zscore_flags": int((df_out["humidity_zscore_flag"] == 1.0).sum()),
        "temperature_iqr_flags": int((df_out["temperature_iqr_flag"] == 1.0).sum()),
        "pressure_iqr_flags": int((df_out["pressure_iqr_flag"] == 1.0).sum()),
        "humidity_iqr_flags": int((df_out["humidity_iqr_flag"] == 1.0).sum()),
        "zscore_any_flag_rows": int(z_any),
        "iqr_any_flag_rows": int(q_any),
        "same_variable_both_views_rows": int(both),
        "combined_baseline_flags": flagged,
        "combined_flag_rate_usable": round(flagged / usable, 6) if usable else None,
        "combined_flag_rate_all": round(flagged / n, 6) if n else None,
    }

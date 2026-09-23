"""Validation for the Phase 4 statistical baseline.

Checks structural integrity, causality support, exclusion consistency,
and segment-boundary safety. Descriptive statistics live in
statistical_baseline.summarize_baseline; no detection metrics are
fabricated here (no ground-truth labels exist).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.baseline.statistical_baseline import (
    BASELINE_COLUMNS,
    STATUS_COMPUTED,
    STATUS_EXCLUDED,
    STATUS_INSUFFICIENT,
)


def validate_baseline_frame(
    df_out: pd.DataFrame,
    df_feat: pd.DataFrame,
    df_quality: pd.DataFrame,
) -> dict:
    """Run structural checks. Return {'all_passed': bool, 'checks': {...}}."""
    checks: dict[str, bool] = {}

    checks["schema_matches"] = list(df_out.columns) == BASELINE_COLUMNS
    checks["row_count_matches_input"] = len(df_out) == len(df_feat) == len(df_quality)
    checks["timestamp_unchanged"] = bool((df_out["timestamp"].astype(str) == df_feat["timestamp"].astype(str)).all())

    for col in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
        a = pd.to_numeric(df_out[col], errors="coerce")
        b = pd.to_numeric(df_feat[col], errors="coerce")
        same_nan = (a.isna() == b.isna()).all()
        same_vals = np.allclose(a.dropna().to_numpy(dtype=float), b.dropna().to_numpy(dtype=float))
        checks[f"observation_{col}_unchanged"] = bool(same_nan and same_vals)

    # Excluded rows carry no statistical decision.
    excluded = df_out["baseline_status"].astype(str) == STATUS_EXCLUDED
    ineligible = df_quality["ml_eligible"].to_numpy(dtype=int) == 0
    checks["excluded_matches_ineligible"] = bool((excluded.to_numpy() == ineligible).all())
    view_cols = [f"{v}_zscore_baseline" for v in ("temperature", "pressure", "humidity")]
    view_cols += [f"{v}_{w}" for v in ("temperature", "pressure", "humidity")
                  for w in ("zscore_flag", "iqr_flag")]
    checks["excluded_scores_all_nan"] = bool(df_out.loc[excluded, view_cols].isna().all().all())
    checks["excluded_combined_flag_nan"] = bool(df_out.loc[excluded, "statistical_baseline_flag"].isna().all())

    # Status vocabulary is closed.
    allowed_status = {STATUS_COMPUTED, STATUS_INSUFFICIENT, STATUS_EXCLUDED}
    checks["status_vocabulary_closed"] = bool(set(df_out["baseline_status"].astype(str).unique()) <= allowed_status)

    # Combined flag is consistent with counts.
    avail = df_out["statistical_flags_available"].to_numpy(dtype=int)
    count = df_out["statistical_anomaly_count"].to_numpy(dtype=int)
    flag = df_out["statistical_baseline_flag"].to_numpy(dtype=float)
    checks["flag_consistent_with_counts"] = bool(
        np.all(np.isnan(flag[avail == 0]))
        and np.all(flag[(avail > 0) & (count > 0)] == 1.0)
        and np.all(flag[(avail > 0) & (count == 0)] == 0.0)
        and np.all(count <= avail)
    )

    # Segment starts have no computable history (first window_rows rows NaN).
    seg = df_feat["segment_id"].to_numpy(dtype=int)
    starts = np.where(np.diff(seg, prepend=seg[0] - 1) != 0)[0]
    checks["segment_starts_insufficient"] = bool(
        df_out.iloc[starts]["statistical_flags_available"].eq(0).all()
    )

    all_passed = all(checks.values())
    return {"all_passed": all_passed, "checks": checks}

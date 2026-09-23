"""Method A — causal rolling z-score baseline (traditional QC).

Reuses the Phase 3 causal 2-hour rolling statistics directly:

    z(t) = (x(t) - prev_mean_2h) / prev_std_2h

Phase 3 guarantees these are computed from previous observations only
(< t) within the same segment, NaN when history is insufficient. The
baseline therefore inherits causality and gap safety without
recalculating rolling moments.

Zero-variance policy: if prev_std is zero, below epsilon, or missing,
the z-score is NaN (never silently converted into an anomaly).

Threshold |z| > 3.0 is a conventional statistical configuration, NOT a
claim of optimality for AWS sensor-fault detection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Conventional baseline threshold (configuration, not tuned here).
Z_THRESHOLD = 3.0

# Std at or below this is treated as unavailable -> z = NaN.
MIN_STD_EPS = 1e-9

# Phase 3 column mapping: baseline variable -> (observation col, prefix).
BASELINE_VARIABLES: dict[str, tuple[str, str]] = {
    "temperature": ("temperature_c", "temperature"),
    "pressure": ("pressure_hpa", "pressure"),
    "humidity": ("relative_humidity_pct", "humidity"),
}

BASELINE_HORIZON = "2h"


def compute_zscores(df_feat: pd.DataFrame) -> pd.DataFrame:
    """Compute causal z-scores reusing Phase 3 2h rolling mean/std columns."""
    out: dict[str, pd.Series] = {}
    for var, (obs_col, prefix) in BASELINE_VARIABLES.items():
        x = pd.to_numeric(df_feat[obs_col], errors="coerce").to_numpy(dtype=float)
        mean = pd.to_numeric(df_feat[f"{prefix}_prev_mean_{BASELINE_HORIZON}"], errors="coerce").to_numpy(dtype=float)
        std = pd.to_numeric(df_feat[f"{prefix}_prev_std_{BASELINE_HORIZON}"], errors="coerce").to_numpy(dtype=float)
        usable = ~np.isnan(x) & ~np.isnan(mean) & ~np.isnan(std) & (std > MIN_STD_EPS)
        z = np.full(len(df_feat), np.nan, dtype=float)
        z[usable] = (x[usable] - mean[usable]) / std[usable]
        out[f"{var}_zscore_baseline"] = pd.Series(z, index=df_feat.index, dtype=float)
    return pd.DataFrame(out, index=df_feat.index)


def compute_zscore_flags(zscores: pd.DataFrame, z_threshold: float = Z_THRESHOLD) -> pd.DataFrame:
    """Flag |z| > threshold. NaN score -> NaN flag (unknown, not normal)."""
    out: dict[str, pd.Series] = {}
    for var in BASELINE_VARIABLES:
        z = zscores[f"{var}_zscore_baseline"].to_numpy(dtype=float)
        flag = np.full(len(zscores), np.nan, dtype=float)
        known = ~np.isnan(z)
        flag[known] = (np.abs(z[known]) > z_threshold).astype(float)
        out[f"{var}_zscore_flag"] = pd.Series(flag, index=zscores.index, dtype=float)
    return pd.DataFrame(out, index=zscores.index)

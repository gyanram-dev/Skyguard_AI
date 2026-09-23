"""Multivariate consistency feature computation for AWS core variables.

Combines robust standardized deviations of temperature, pressure, and humidity to capture:
- multivariate_max_abs_robust_deviation: maximum absolute robust deviation across the triad.
- multivariate_deviation_range: maximum robust deviation minus minimum robust deviation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_multivariate_features_for_horizon(
    temp_rob_dev: pd.Series,
    pres_rob_dev: pd.Series,
    rh_rob_dev: pd.Series,
    horizon_name: str,
) -> pd.DataFrame:
    """Compute multivariate consistency features for a specific time horizon.

    Rules:
    - If any of the 3 robust deviations is NaN, returns NaN for both features.
    - max_abs = max(|z_T|, |z_P|, |z_RH|)
    - range = max(z_T, z_P, z_RH) - min(z_T, z_P, z_RH)
    """
    t_z = temp_rob_dev.to_numpy(dtype=float)
    p_z = pres_rob_dev.to_numpy(dtype=float)
    rh_z = rh_rob_dev.to_numpy(dtype=float)

    valid_mask = ~np.isnan(t_z) & ~np.isnan(p_z) & ~np.isnan(rh_z)
    n = len(temp_rob_dev)

    max_abs = np.full(n, np.nan, dtype=float)
    dev_range = np.full(n, np.nan, dtype=float)

    if np.any(valid_mask):
        t_v = t_z[valid_mask]
        p_v = p_z[valid_mask]
        rh_v = rh_z[valid_mask]

        stack_raw = np.stack([t_v, p_v, rh_v], axis=1)
        stack_abs = np.abs(stack_raw)

        max_abs[valid_mask] = np.max(stack_abs, axis=1)
        dev_range[valid_mask] = np.max(stack_raw, axis=1) - np.min(stack_raw, axis=1)

    return pd.DataFrame({
        f"multivariate_max_abs_robust_deviation_{horizon_name}": pd.Series(max_abs, index=temp_rob_dev.index, dtype=float),
        f"multivariate_deviation_range_{horizon_name}": pd.Series(dev_range, index=temp_rob_dev.index, dtype=float),
    }, index=temp_rob_dev.index)

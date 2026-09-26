"""Causal rolling baseline, local deviation, and trend feature computation.

Rules:
- Strictly causal: operates only on observations before t (< t).
- Confined to the same segment: never crosses structural timestamp gaps.
- Missing-data safe: if any value in the required history window is missing, returns NaN.
- Computes mean, std, median, MAD, deviation from median, robust deviation, and trend slope.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_causal_rolling_window_features(
    series: pd.Series,
    segment_id: pd.Series,
    window_rows: int,
    horizon_name: str,
    prefix: str,
    small_epsilon: float = 1e-6,
) -> pd.DataFrame:
    """Compute all causal rolling baseline and deviation features for a given variable and horizon.

    Features generated:
    - {prefix}_prev_mean_{horizon_name}
    - {prefix}_prev_std_{horizon_name}
    - {prefix}_prev_median_{horizon_name}
    - {prefix}_prev_mad_{horizon_name}
    - {prefix}_deviation_from_median_{horizon_name}
    - {prefix}_robust_deviation_{horizon_name}
    - {prefix}_trend_{horizon_name}
    """
    n = len(series)
    arr = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    seg_arr = segment_id.to_numpy(dtype=int)
    w = window_rows

    # Pre-allocate output arrays
    out_mean = np.full(n, np.nan, dtype=float)
    out_std = np.full(n, np.nan, dtype=float)
    out_median = np.full(n, np.nan, dtype=float)
    out_mad = np.full(n, np.nan, dtype=float)
    out_trend = np.full(n, np.nan, dtype=float)

    # Pre-compute linear trend slope weights for window w
    # slope = sum(c_i * y_i) where c_i = (x_i - mean(x)) / sum((x_i - mean(x))^2)
    x = np.arange(w, dtype=float)
    x_mean = np.mean(x)
    denom = np.sum((x - x_mean) ** 2)
    slope_weights = (x - x_mean) / denom

    # Find contiguous segment boundaries
    seg_change = np.where(np.diff(seg_arr) != 0)[0] + 1
    starts = [0] + list(seg_change)
    ends = list(seg_change) + [n]

    for start, end in zip(starts, ends):
        seg_len = end - start
        if seg_len <= w:
            continue

        seg_arr_slice = arr[start:end]

        # Shift by 1 so window ending at index k in seg_shift contains observations strictly < k
        seg_shift = np.empty(seg_len, dtype=float)
        seg_shift[0] = np.nan
        seg_shift[1:] = seg_arr_slice[:-1]

        # Construct sliding window view
        v = np.lib.stride_tricks.sliding_window_view(seg_shift, window_shape=w)
        # Check window validity: no NaNs inside the window
        valid_mask = ~np.isnan(v).any(axis=1)

        if np.any(valid_mask):
            v_valid = v[valid_mask]

            # 1. Mean
            m_valid = np.mean(v_valid, axis=1)

            # 2. Sample Standard Deviation (ddof=1)
            # When w=1 (not applicable here as w >= 3), std is 0.
            std_valid = np.std(v_valid, axis=1, ddof=1)

            # 3. Median
            med_valid = np.median(v_valid, axis=1)

            # 4. Median Absolute Deviation (MAD) = median(|x - median(x)|)
            diff_from_med = np.abs(v_valid - med_valid[:, None])
            mad_valid = np.median(diff_from_med, axis=1)

            # 5. Trend slope (linear regression)
            trend_valid = np.dot(v_valid, slope_weights)

            # Populate segment outputs
            seg_mean = np.full(len(v), np.nan, dtype=float)
            seg_std = np.full(len(v), np.nan, dtype=float)
            seg_median = np.full(len(v), np.nan, dtype=float)
            seg_mad = np.full(len(v), np.nan, dtype=float)
            seg_trend = np.full(len(v), np.nan, dtype=float)

            seg_mean[valid_mask] = m_valid
            seg_std[valid_mask] = std_valid
            seg_median[valid_mask] = med_valid
            seg_mad[valid_mask] = mad_valid
            seg_trend[valid_mask] = trend_valid

            # Align to global array: v[k] corresponds to index start + w - 1 + k
            out_mean[start + w - 1 : end] = seg_mean
            out_std[start + w - 1 : end] = seg_std
            out_median[start + w - 1 : end] = seg_median
            out_mad[start + w - 1 : end] = seg_mad
            out_trend[start + w - 1 : end] = seg_trend

    # Deviations from previous median
    # deviation = current_value - previous_median
    # robust_deviation = (current_value - previous_median) / max(previous_mad * 1.4826, epsilon)
    valid_curr = ~np.isnan(arr)
    valid_med = ~np.isnan(out_median)
    calc_mask = valid_curr & valid_med

    out_dev = np.full(n, np.nan, dtype=float)
    out_dev[calc_mask] = arr[calc_mask] - out_median[calc_mask]

    out_rob_dev = np.full(n, np.nan, dtype=float)
    denom_mad = np.maximum(out_mad * 1.4826, small_epsilon)
    out_rob_dev[calc_mask] = out_dev[calc_mask] / denom_mad[calc_mask]

    return pd.DataFrame({
        f"{prefix}_prev_mean_{horizon_name}": pd.Series(out_mean, index=series.index, dtype=float),
        f"{prefix}_prev_std_{horizon_name}": pd.Series(out_std, index=series.index, dtype=float),
        f"{prefix}_prev_median_{horizon_name}": pd.Series(out_median, index=series.index, dtype=float),
        f"{prefix}_prev_mad_{horizon_name}": pd.Series(out_mad, index=series.index, dtype=float),
        f"{prefix}_deviation_from_median_{horizon_name}": pd.Series(out_dev, index=series.index, dtype=float),
        f"{prefix}_robust_deviation_{horizon_name}": pd.Series(out_rob_dev, index=series.index, dtype=float),
        f"{prefix}_trend_{horizon_name}": pd.Series(out_trend, index=series.index, dtype=float),
    }, index=series.index)

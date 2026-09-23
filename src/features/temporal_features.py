"""Temporal and dynamic feature computation for AWS observations.

Includes:
- Timeline gap detection and segment ID assignment.
- Cyclical temporal features (hour, day of year).
- First-order rate-of-change dynamics.
- Frozen/stuck sensor indicators and rolling 2h frozen ratio.
Strictly causal: uses only current and prior observations within the same segment.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_gap_and_segments(
    dt_series: pd.Series,
    expected_interval_min: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute elapsed time since previous row, structural gap flags, and contiguous segment IDs.

    A structural gap is flagged when:
        elapsed_minutes_since_prev > expected_interval_min * 1.5
    Segment ID increments upon every structural gap.
    """
    elapsed_minutes = (dt_series - dt_series.shift(1)).dt.total_seconds() / 60.0
    gap_threshold = expected_interval_min * 1.5
    gap_before = (elapsed_minutes > gap_threshold).astype(int)
    # The very first observation has no prior gap
    gap_before.iloc[0] = 0

    segment_id = gap_before.cumsum().astype(int)
    return elapsed_minutes, gap_before, segment_id


def compute_cyclical_features(dt_series: pd.Series) -> pd.DataFrame:
    """Compute continuous cyclical encodings for hour-of-day and day-of-year."""
    # Fractional hour: hour + minute / 60.0
    frac_hour = dt_series.dt.hour + dt_series.dt.minute / 60.0
    hour_angle = 2.0 * np.pi * frac_hour / 24.0

    # Fractional day of year: dayofyear - 1 + frac_hour / 24.0
    frac_day = (dt_series.dt.dayofyear - 1) + frac_hour / 24.0
    day_angle = 2.0 * np.pi * frac_day / 365.25

    return pd.DataFrame({
        "hour_sin": np.sin(hour_angle),
        "hour_cos": np.cos(hour_angle),
        "day_of_year_sin": np.sin(day_angle),
        "day_of_year_cos": np.cos(day_angle),
    }, index=dt_series.index)


def compute_first_order_dynamics(
    series: pd.Series,
    elapsed_minutes: pd.Series,
    segment_id: pd.Series,
    prefix: str,
) -> pd.DataFrame:
    """Compute first-order delta and rate-of-change per hour.

    Rules:
    - delta = current - previous_valid
    - If previous observation belongs to another segment, is missing, or is unavailable -> NaN.
    - DO NOT fill with zero!
    """
    s = pd.to_numeric(series, errors="coerce")
    s_prev = s.shift(1)
    seg_prev = segment_id.shift(1)

    # Valid transition mask: previous must exist and be in the same segment
    valid_step = (segment_id == seg_prev) & s_prev.notna() & s.notna()

    delta = pd.Series(np.nan, index=series.index, dtype=float)
    delta[valid_step] = s[valid_step] - s_prev[valid_step]

    valid_rate = valid_step & (elapsed_minutes > 0) & elapsed_minutes.notna()
    rate_per_hour = pd.Series(np.nan, index=series.index, dtype=float)
    rate_per_hour[valid_rate] = (delta[valid_rate] / elapsed_minutes[valid_rate]) * 60.0

    abs_rate_per_hour = rate_per_hour.abs()

    return pd.DataFrame({
        f"{prefix}_delta": delta,
        f"{prefix}_rate_per_hour": rate_per_hour,
        f"{prefix}_abs_rate_per_hour": abs_rate_per_hour,
    }, index=series.index)


def compute_frozen_features(
    series: pd.Series,
    segment_id: pd.Series,
    window_rows_2h: int,
    prefix: str,
) -> pd.DataFrame:
    """Compute frozen-sensor zero delta indicators and 2-hour rolling frozen ratio.

    Rules:
    - zero_delta = 1 when current value == previous valid value inside same segment, 0 if changed, NaN if invalid.
    - zero_delta_ratio_2h = rolling mean of zero_delta over previous 2h window (< t) within same segment.
    """
    s = pd.to_numeric(series, errors="coerce")
    s_prev = s.shift(1)
    seg_prev = segment_id.shift(1)

    valid_step = (segment_id == seg_prev) & s_prev.notna() & s.notna()

    zero_delta = pd.Series(np.nan, index=series.index, dtype=float)
    zero_delta[valid_step] = (s[valid_step] == s_prev[valid_step]).astype(float)

    # Rolling ratio of zero_delta over the previous 2-hour window (< t) within the same segment
    n = len(series)
    ratio_2h = np.full(n, np.nan, dtype=float)

    seg_arr = segment_id.to_numpy()
    zd_arr = zero_delta.to_numpy()

    # Find segment slices
    seg_change = np.where(np.diff(seg_arr) != 0)[0] + 1
    starts = [0] + list(seg_change)
    ends = list(seg_change) + [n]

    w = window_rows_2h
    for start, end in zip(starts, ends):
        seg_len = end - start
        if seg_len <= w:
            continue
        # Shift zero_delta by 1 within segment so observation t uses strictly < t
        seg_zd = zd_arr[start:end]
        seg_shift = np.empty(seg_len, dtype=float)
        seg_shift[0] = np.nan
        seg_shift[1:] = seg_zd[:-1]

        v = np.lib.stride_tricks.sliding_window_view(seg_shift, window_shape=w)
        # We require all w steps in the window to be valid (not NaN)
        valid_mask = ~np.isnan(v).any(axis=1)
        if np.any(valid_mask):
            seg_res = np.full(len(v), np.nan, dtype=float)
            seg_res[valid_mask] = np.mean(v[valid_mask], axis=1)
            ratio_2h[start + w - 1 : end] = seg_res

    return pd.DataFrame({
        f"{prefix}_zero_delta": zero_delta,
        f"{prefix}_zero_delta_ratio_2h": pd.Series(ratio_2h, index=series.index, dtype=float),
    }, index=series.index)

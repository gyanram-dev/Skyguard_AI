"""Method B — causal rolling IQR baseline (traditional QC).

Phase 3 stores median/MAD but not quartiles, so this module adds the
smallest necessary calculation: causal rolling Q1/Q3 over the previous
2-hour window, mirroring Phase 3 rolling semantics exactly:

- strictly previous observations (< t)
- confined to the same segment (windows never cross gaps)
- full valid window required, else NaN (no partial-history statistics)

Bounds: lower = Q1 - 1.5*IQR, upper = Q3 + 1.5*IQR.
Flag 1 = outside bounds, 0 = inside, NaN = insufficient history.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Conventional Tukey factor (configuration, not tuned here).
IQR_FACTOR = 1.5


def causal_rolling_quartiles(
    series: pd.Series,
    segment_id: pd.Series,
    window_rows: int,
) -> tuple[pd.Series, pd.Series]:
    """Causal Q1/Q3 over the previous `window_rows` observations (< t).

    Requires all `window_rows` values valid and in-segment, else NaN.
    """
    n = len(series)
    arr = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    seg_arr = segment_id.to_numpy(dtype=int)
    w = window_rows

    out_q1 = np.full(n, np.nan, dtype=float)
    out_q3 = np.full(n, np.nan, dtype=float)

    seg_change = np.where(np.diff(seg_arr) != 0)[0] + 1
    starts = [0] + list(seg_change)
    ends = list(seg_change) + [n]

    for start, end in zip(starts, ends):
        seg_len = end - start
        if seg_len <= w:
            continue
        seg_slice = arr[start:end]
        seg_shift = np.empty(seg_len, dtype=float)
        seg_shift[0] = np.nan
        seg_shift[1:] = seg_slice[:-1]
        v = np.lib.stride_tricks.sliding_window_view(seg_shift, window_shape=w)
        valid_mask = ~np.isnan(v).any(axis=1)
        if np.any(valid_mask):
            v_valid = v[valid_mask]
            seg_q1 = np.full(len(v), np.nan, dtype=float)
            seg_q3 = np.full(len(v), np.nan, dtype=float)
            seg_q1[valid_mask] = np.quantile(v_valid, 0.25, axis=1)
            seg_q3[valid_mask] = np.quantile(v_valid, 0.75, axis=1)
            out_q1[start + w - 1 : end] = seg_q1
            out_q3[start + w - 1 : end] = seg_q3

    return (
        pd.Series(out_q1, index=series.index, dtype=float),
        pd.Series(out_q3, index=series.index, dtype=float),
    )


def compute_iqr_flags(
    df_feat: pd.DataFrame,
    window_rows: int,
    iqr_factor: float = IQR_FACTOR,
) -> pd.DataFrame:
    """Compute causal IQR flags for temperature, pressure, humidity."""
    from src.baseline.zscore_baseline import BASELINE_VARIABLES

    out: dict[str, pd.Series] = {}
    seg = df_feat["segment_id"]
    for var, (obs_col, _prefix) in BASELINE_VARIABLES.items():
        x = pd.to_numeric(df_feat[obs_col], errors="coerce")
        q1, q3 = causal_rolling_quartiles(x, seg, window_rows)
        iqr = q3 - q1
        lower = q1 - iqr_factor * iqr
        upper = q3 + iqr_factor * iqr
        flag = pd.Series(np.nan, index=df_feat.index, dtype=float)
        # NaN only when history is missing. A zero-width IQR (frozen
        # context) still yields a valid Tukey comparison: equal -> 0,
        # different -> 1. No division is involved, so no epsilon is needed.
        computable = x.notna() & q1.notna() & q3.notna()
        below_or_above = (x < lower) | (x > upper)
        flag[computable] = below_or_above[computable].astype(float)
        out[f"{var}_iqr_flag"] = flag
    return pd.DataFrame(out, index=df_feat.index)

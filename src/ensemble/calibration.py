"""Train-only ECDF calibration for heterogeneous detector scores.

calibrated(x) = fraction of clean-training scores <= x
(searchsorted, side="right", divided by n). Range [0,1]; higher means more
unusual relative to clean training. NOT a probability.

Ties: equal values share one rank (all training mass at/below the value).
Edges: below the minimum -> 0.0; above the maximum -> 1.0. NaN input is
never calibrated (unavailable stays missing, never zero-filled).
"""

from __future__ import annotations

import numpy as np


def fit_ecdf(train_scores: np.ndarray) -> np.ndarray:
    """Freeze the sorted clean-training score distribution."""
    scores = np.asarray(train_scores, dtype=float)
    scores = scores[np.isfinite(scores)]
    if len(scores) == 0:
        raise ValueError("ECDF needs a non-empty finite training distribution")
    return np.sort(scores)


def calibrate(scores: np.ndarray, train_sorted: np.ndarray) -> np.ndarray:
    """Map raw scores onto the frozen [0,1] evidence scale."""
    raw = np.asarray(scores, dtype=float)
    out = np.full(raw.shape, np.nan)
    finite = np.isfinite(raw)
    ranked = np.searchsorted(train_sorted, raw[finite], side="right")
    out[finite] = ranked / len(train_sorted)
    return out


def z_evidence(frame) -> tuple[np.ndarray, np.ndarray]:
    """Continuous z evidence = max |z| over available T/P/RH z-scores."""
    import pandas as pd

    cols = ["temperature_zscore", "pressure_zscore", "humidity_zscore"]
    if not set(cols) <= set(frame.columns):
        cols = ["temperature_zscore_baseline", "pressure_zscore_baseline",
                "humidity_zscore_baseline"]
    mat = np.stack([pd.to_numeric(frame[c], errors="coerce").to_numpy(dtype=float)
                    for c in cols], axis=1)
    available = np.isfinite(mat).any(axis=1)
    raw = np.full(len(mat), np.nan)
    with np.errstate(all="ignore"):
        raw[available] = np.nanmax(np.abs(mat[available]), axis=1)
    raw[~available] = np.nan
    return raw, available


def iqr_evidence(frame) -> tuple[np.ndarray, np.ndarray]:
    """IQR evidence from stored combined flags (binary: 0/1).

    The frozen Phase 4/6 artifacts store IQR decisions, not a continuous
    distance, so the calibrated evidence has two levels: P(train = 0) for
    normal rows and 1.0 for flagged rows. Documented limitation, not a
    silent substitution.
    """
    import pandas as pd

    col = "iqr_combined_flag" if "iqr_combined_flag" in frame.columns else None
    if col is None:
        parts = ["temperature_iqr_flag", "pressure_iqr_flag", "humidity_iqr_flag"]
        mat = np.stack([pd.to_numeric(frame[c], errors="coerce").to_numpy(dtype=float)
                        for c in parts], axis=1)
        available = np.isfinite(mat).any(axis=1)
        raw = np.full(len(mat), np.nan)
        with np.errstate(all="ignore"):
            raw[available] = np.nanmax(mat[available], axis=1)
        raw[~available] = np.nan
        return raw, available
    raw = pd.to_numeric(frame[col], errors="coerce").to_numpy(dtype=float)
    return raw, np.isfinite(raw)

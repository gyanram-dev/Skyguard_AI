"""Transparent combination of calibrated evidence (no learned weights).

Methods (reported side by side, never selected by test labels):
- mean: equal-weight average of available calibrated components.
- median: median of available calibrated components (robust to one
  divergent detector).

Availability policy over the three primary components
(statistical, isolation forest, lstm):
- 3 available -> FULL_EVIDENCE
- 2 available -> PARTIAL_EVIDENCE
- < 2 available -> INSUFFICIENT_EVIDENCE (score NaN, never zero-filled;
  a missing detector is not evidence of normality).
"""

from __future__ import annotations

import numpy as np

FULL_EVIDENCE = "FULL_EVIDENCE"
PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def combine(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Combine calibrated components; return (mean, median, availability).

    matrix: (n_rows, n_components) with NaN for unavailable evidence.
    """
    mat = np.asarray(matrix, dtype=float)
    n_avail = np.isfinite(mat).sum(axis=1)
    mean = np.full(len(mat), np.nan)
    median = np.full(len(mat), np.nan)
    ok = n_avail > 0
    with np.errstate(all="ignore"):
        mean[ok] = np.nanmean(mat[ok], axis=1)
        median[ok] = np.nanmedian(mat[ok], axis=1)
    mean[n_avail < 2] = np.nan
    median[n_avail < 2] = np.nan
    availability = np.full(len(mat), INSUFFICIENT_EVIDENCE, dtype=object)
    availability[n_avail == 2] = PARTIAL_EVIDENCE
    availability[n_avail >= 3] = FULL_EVIDENCE
    return mean, median, availability


def statistical_component(z_cal: np.ndarray, iqr_cal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """One statistical vote: mean of available calibrated z/iqr evidence."""
    mat = np.stack([np.asarray(z_cal, dtype=float), np.asarray(iqr_cal, dtype=float)], axis=1)
    n_avail = np.isfinite(mat).sum(axis=1)
    out = np.full(len(mat), np.nan)
    ok = n_avail > 0
    with np.errstate(all="ignore"):
        out[ok] = np.nanmean(mat[ok], axis=1)
    out[n_avail == 0] = np.nan
    return out, n_avail

"""Neighbor reference values: median reference, MAD dispersion.

Reference (per variable, per timestamp):
    reference = median of available neighbor observations   (needs >= 1)
    difference = target - reference
Dispersion (needs >= 2 available neighbor observations):
    MAD = median(|neighbor_i - median(neighbors)|)
Scores and confidence live in scoring.py.
"""

from __future__ import annotations

import numpy as np


def neighbor_median(values: np.ndarray) -> float:
    """Median of available neighbor values; NaN when none are available."""
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return float("nan")
    return float(np.median(vals))


def neighbor_mad(values: np.ndarray) -> float:
    """Median absolute deviation; NaN with fewer than 2 available values."""
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) < 2:
        return float("nan")
    return float(np.median(np.abs(vals - np.median(vals))))

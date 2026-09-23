"""Traditional Statistical QC Baseline for SkyGuard AI (Phase 4).

NOT an AI/ML model. A conventional rolling-statistics reference that
future context-aware detectors will be compared against.

Two preserved views: causal rolling z-score and causal rolling IQR rule.
Strictly causal: previous observations only, same-segment only.
"""

from src.baseline.iqr_baseline import IQR_FACTOR, compute_iqr_flags
from src.baseline.zscore_baseline import (
    MIN_STD_EPS,
    Z_THRESHOLD,
    compute_zscore_flags,
    compute_zscores,
)

__all__ = [
    "Z_THRESHOLD",
    "MIN_STD_EPS",
    "IQR_FACTOR",
    "compute_zscores",
    "compute_zscore_flags",
    "compute_iqr_flags",
]

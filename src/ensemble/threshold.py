"""Ensemble decision thresholds from clean-training ensemble scores.

99th percentile of the clean-training ensemble-score distribution, one
threshold per aggregation method. Frozen before any benchmark split is
touched; never adjusted on ID/OOD, fault-type, or event performance.
Reuses the frozen Phase 7 quantile methodology.
"""

from __future__ import annotations

from src.isolation_forest.threshold import THRESHOLD_QUANTILE, fit_threshold

THRESHOLD_METHOD = (
    f"{THRESHOLD_QUANTILE:.0%} percentile of clean-training ensemble scores"
)

__all__ = ["THRESHOLD_QUANTILE", "THRESHOLD_METHOD", "fit_threshold"]

"""Train-only threshold: 99th percentile of clean-training target errors.

Reuses the frozen Phase 7 quantile methodology on LSTM reconstruction
errors. The threshold is computed before any test split is touched and is
never adjusted using ID/OOD performance.
"""

from __future__ import annotations

from src.isolation_forest.threshold import THRESHOLD_QUANTILE, fit_threshold

THRESHOLD_METHOD = f"{THRESHOLD_QUANTILE:.0%} percentile of eligible clean-training target MSE"

__all__ = ["THRESHOLD_QUANTILE", "THRESHOLD_METHOD", "fit_threshold"]

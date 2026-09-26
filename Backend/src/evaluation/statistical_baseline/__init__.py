"""Evaluation of the Traditional Statistical QC Baseline on the fault benchmark (Phase 6).

NOT a model. Measures the frozen Phase 4 baseline (recomputed causally on
each benchmark split's actual signal) against Phase 5 ground truth.
"""

from src.evaluation.statistical_baseline.metrics import (
    OFFICIAL_IQR_FACTOR,
    OFFICIAL_Z_THRESHOLD,
    confusion_counts,
    prf_metrics,
)

__all__ = [
    "OFFICIAL_Z_THRESHOLD",
    "OFFICIAL_IQR_FACTOR",
    "confusion_counts",
    "prf_metrics",
]

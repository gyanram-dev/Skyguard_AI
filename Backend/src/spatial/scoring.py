"""Robust spatial scores and context-confidence classification.

Score (per variable, per timestamp):
    absolute_difference = |target - neighbor_median|
    spatial_robust_score = absolute_difference / MAD
Higher = stronger spatial inconsistency. NOT a probability. NaN whenever
fewer than 2 neighbor observations are available or MAD is 0 (degenerate
agreement carries no gradient information, so no score is manufactured).

Confidence reflects observable data availability only, never anomaly
probability:
    UNAVAILABLE   no target value, or 0 available neighbors
    LOW_CONTEXT   1 available neighbor, or degenerate (MAD == 0) dispersion
    MEDIUM_CONTEXT  >= 2 available neighbors but fewer than expected
    HIGH_CONTEXT  all expected neighbors available with a valid score
"""

from __future__ import annotations

import numpy as np

from src.spatial.reference import neighbor_mad, neighbor_median

MIN_NEIGHBORS_FOR_SCORE = 2


def score_variable(target: float, neighbor_values: np.ndarray,
                   expected_count: int) -> dict:
    """Robust evidence record for one variable at one timestamp."""
    n_available = int(np.isfinite(np.asarray(neighbor_values, dtype=float)).sum())
    target_missing = not np.isfinite(float(target)) if target is not None else True
    ref = neighbor_median(neighbor_values)
    mad = neighbor_mad(neighbor_values)
    if target_missing or n_available == 0:
        return {"reference": float("nan"), "difference": float("nan"),
                "abs_difference": float("nan"), "robust_score": float("nan"),
                "n_available": n_available, "context": "UNAVAILABLE"}
    diff = float(target) - ref
    if n_available < MIN_NEIGHBORS_FOR_SCORE or not np.isfinite(mad) or mad == 0.0:
        return {"reference": ref, "difference": diff,
                "abs_difference": abs(diff), "robust_score": float("nan"),
                "n_available": n_available, "context": "LOW_CONTEXT"}
    score = abs(diff) / mad
    context = "HIGH_CONTEXT" if n_available >= expected_count else "MEDIUM_CONTEXT"
    return {"reference": ref, "difference": diff, "abs_difference": abs(diff),
            "robust_score": float(score), "n_available": n_available,
            "context": context}

"""UNKNOWN / MIXED decision application (frozen rules, no test tuning).

- UNKNOWN: max class probability < UNKNOWN_PROBA (insufficient evidence).
- MIXED: top >= UNKNOWN_PROBA AND second >= MIXED_SECOND_PROBA AND
  (top - second) <= MIXED_GAP (confident yet split across two patterns;
  cutoffs chosen so the condition is reachable under unit-sum
  probabilities). Never assigned merely because two classes have
  non-zero probability.
"""

from __future__ import annotations

import numpy as np

from src.root_cause.confidence import MIXED, MIXED_GAP, MIXED_SECOND_PROBA, UNKNOWN, UNKNOWN_PROBA


def decide(probas: np.ndarray, classes: list[str],
           unknown_proba: float = UNKNOWN_PROBA,
           mixed_second: float = MIXED_SECOND_PROBA,
           mixed_gap: float = MIXED_GAP) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply the frozen decision rules. Return (labels, confidence, runner_up)."""
    probas = np.asarray(probas, dtype=float)
    order = np.argsort(-probas, axis=1)
    top = probas[np.arange(len(probas)), order[:, 0]]
    second = np.where(probas.shape[1] > 1,
                      probas[np.arange(len(probas)), order[:, 1]], 0.0)
    labels = np.array([classes[i] for i in order[:, 0]], dtype=object)
    runner = np.array([classes[i] if probas.shape[1] > 1 else "" for i in order[:, 1]],
                      dtype=object)
    mixed = (top >= unknown_proba) & (second >= mixed_second) & ((top - second) <= mixed_gap)
    labels[mixed] = MIXED
    unknown = top < unknown_proba
    labels[unknown] = UNKNOWN
    return labels, top, runner

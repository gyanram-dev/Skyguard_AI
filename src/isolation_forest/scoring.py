"""SkyGuard score convention: HIGHER anomaly score = MORE anomalous.

sklearn's decision_function is oriented the other way (higher = more
normal), so the raw score is its negation:

    if_raw_score = -decision_function(X)

Normalized score: frozen ECDF of the training raw distribution,

    if_anomaly_score = searchsorted(train_raw_sorted, raw) / n_train  in [0, 1]

i.e. the fraction of training scores at or below the observation.
NOT a probability; 0.9 never means "90% probability of failure".

Official flag: raw >= frozen 99th-percentile training threshold
(equivalently score >= 0.99).
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


def raw_scores(model: IsolationForest, X: np.ndarray) -> np.ndarray:
    """Higher = more anomalous."""
    return (-model.decision_function(X)).astype(float)


def normalize_scores(raw: np.ndarray, train_raw_sorted: np.ndarray) -> np.ndarray:
    """ECDF against the frozen training distribution. Range [0, 1]."""
    ranked = np.searchsorted(train_raw_sorted, np.asarray(raw, dtype=float), side="right")
    return (ranked / max(1, len(train_raw_sorted))).astype(float)


def flag_scores(raw: np.ndarray, threshold_raw: float) -> np.ndarray:
    """Binary flags at the frozen threshold. No NaN input expected."""
    return (np.asarray(raw, dtype=float) >= float(threshold_raw)).astype(int)

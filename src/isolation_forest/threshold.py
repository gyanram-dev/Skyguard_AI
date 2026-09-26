"""Operational threshold from clean training scores only.

Method: 99th percentile of the eligible training raw-score distribution.
Frozen at train time; ID/OOD benchmark performance never moves it.

Also reports the above-threshold training fraction as a diagnostic
(~1% by construction, larger only with ties at the cut point).
"""

from __future__ import annotations

import numpy as np

THRESHOLD_QUANTILE = 0.99


def fit_threshold(train_raw: np.ndarray, quantile: float = THRESHOLD_QUANTILE) -> tuple[float, dict]:
    """Return (threshold_raw, diagnostics). Benchmark labels never involved."""
    scores = np.asarray(train_raw, dtype=float)
    if len(scores) == 0 or not np.isfinite(scores).all():
        raise ValueError("Threshold needs a non-empty finite training score distribution")
    threshold = float(np.quantile(scores, quantile))
    above = int((scores >= threshold).sum())
    return threshold, {
        "method": f"{quantile:.0%} percentile of eligible training raw scores",
        "quantile": float(quantile),
        "n_train_scores": int(len(scores)),
        "n_above_threshold": above,
        "fraction_above_threshold": above / len(scores),
    }

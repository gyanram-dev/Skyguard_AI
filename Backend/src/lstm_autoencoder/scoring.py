"""Reconstruction-error scoring (HIGHER = MORE anomalous, never a probability).

Official score: final-timestep MSE between the scaled input sequence and
its reconstruction. Rationale: causal event localization — the decision at
timestamp t reflects how badly the model reconstructs observation t given
the 12-step history ending at t. Full-sequence MSE is reported
diagnostically alongside it.
"""

from __future__ import annotations

import numpy as np


def reconstruction_errors(X: np.ndarray, X_hat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (target_step_mse, full_sequence_mse) per sequence."""
    se = (X.astype(np.float64) - X_hat.astype(np.float64)) ** 2
    target_mse = se[:, -1, :].mean(axis=1)
    full_mse = se.mean(axis=(1, 2))
    return target_mse.astype(float), full_mse.astype(float)


def flag_scores(target_mse: np.ndarray, threshold: float) -> np.ndarray:
    """Binary flags at the frozen threshold (no NaN input expected)."""
    return (np.asarray(target_mse, dtype=float) >= float(threshold)).astype(int)

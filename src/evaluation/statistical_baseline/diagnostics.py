"""Threshold sensitivity diagnostics (display only — official settings frozen).

Z thresholds: 2.0, 2.5, 3.0, 3.5, 4.0 (official 3.0).
IQR factors:  1.0, 1.5, 2.0, 2.5      (official 1.5).

Reuses stored z-scores for the Z sweep. Recomputes IQR flags per factor
with the existing Phase 4 function (no duplicated algorithm). Nothing
here may rewrite Phase 4 or select an OOD-tuned threshold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.baseline.iqr_baseline import compute_iqr_flags
from src.evaluation.statistical_baseline.metrics import confusion_counts, prf_metrics

Z_SWEEP = (2.0, 2.5, 3.0, 3.5, 4.0)
IQR_SWEEP = (1.0, 1.5, 2.0, 2.5)

Z_SCORE_COLS = ("temperature_zscore", "pressure_zscore", "humidity_zscore")


def _eligible_xy(rows: pd.DataFrame, pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = rows["evaluation_eligible"].to_numpy(dtype=int) == 1
    return rows["ground_truth_anomaly"].to_numpy(dtype=int)[mask], pred[mask]


def z_threshold_diagnostics(rows: pd.DataFrame, dataset: str, split: str) -> list[dict]:
    """Sweep Z thresholds over the stored causal z-scores (all variables)."""
    out: list[dict] = []
    scores = np.stack([rows[c].to_numpy(dtype=float) for c in Z_SCORE_COLS])
    for thr in Z_SWEEP:
        pred = (np.nan_to_num(np.abs(scores), nan=0.0) > thr).any(axis=0).astype(int)
        y_true, y_pred = _eligible_xy(rows, pred)
        cc = confusion_counts(y_true, y_pred)
        out.append({"dataset": dataset, "split": split, "method": "zscore",
                    "threshold": thr, **cc, **prf_metrics(**{k: cc[k] for k in ("tp", "fp", "tn", "fn")})})
    return out


def iqr_factor_diagnostics(
    features: pd.DataFrame,
    window_rows: int,
    rows: pd.DataFrame,
    dataset: str,
    split: str,
) -> list[dict]:
    """Recompute IQR flags per factor with the Phase 4 function."""
    out: list[dict] = []
    for factor in IQR_SWEEP:
        flags = compute_iqr_flags(features, window_rows, factor)
        mat = np.stack([np.nan_to_num(flags[c].to_numpy(dtype=float), nan=0.0)
                        for c in ("temperature_iqr_flag", "pressure_iqr_flag", "humidity_iqr_flag")])
        pred = (mat == 1.0).any(axis=0).astype(int)
        y_true, y_pred = _eligible_xy(rows, pred)
        cc = confusion_counts(y_true, y_pred)
        out.append({"dataset": dataset, "split": split, "method": "iqr",
                    "threshold": factor, **cc, **prf_metrics(**{k: cc[k] for k in ("tp", "fp", "tn", "fn")})})
    return out

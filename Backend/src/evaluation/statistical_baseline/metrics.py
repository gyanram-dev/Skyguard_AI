"""Metric equations for benchmark evaluation.

Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2PR / (P + R)
FPR       = FP / (FP + TN)
FNR       = FN / (TP + FN)

A zero denominator yields NaN (documented, never silently zero).
"""

from __future__ import annotations

import math

# Official frozen baseline settings (Phase 4). Diagnostics may sweep other
# values but must never rewrite these.
OFFICIAL_Z_THRESHOLD = 3.0
OFFICIAL_IQR_FACTOR = 1.5


def _safe_div(num: float, den: float) -> float:
    if den == 0:
        return math.nan
    return num / den


def confusion_counts(y_true: list[int] | object, y_pred: list[int] | object) -> dict[str, int]:
    """Count TP/FP/TN/FN from aligned binary label/prediction sequences."""
    import numpy as np

    t = np.asarray(list(y_true), dtype=int)
    p = np.asarray(list(y_pred), dtype=int)
    tp = int(((t == 1) & (p == 1)).sum())
    fp = int(((t == 0) & (p == 1)).sum())
    tn = int(((t == 0) & (p == 0)).sum())
    fn = int(((t == 1) & (p == 0)).sum())
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "n": int(len(t))}


def prf_metrics(tp: int, fp: int, tn: int, fn: int) -> dict[str, float]:
    """Precision/Recall/F1/FPR/FNR from confusion counts (NaN if undefined)."""
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    if math.isnan(precision) or math.isnan(recall) or (precision + recall) == 0:
        f1 = math.nan
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": _safe_div(fp, fp + tn),
        "fnr": _safe_div(fn, tp + fn),
    }

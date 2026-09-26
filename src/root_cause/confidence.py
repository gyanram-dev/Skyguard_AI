"""Train-derived confidence evidence for the UNKNOWN / MIXED rules.

Procedure (internal train-validation only, never ID/OOD):
1. Chronological last-20% slice of the labeled train fault rows.
2. Class probabilities from the fitted classifier.
3. Confidence distribution for correctly vs wrongly classified rows.
4. Freeze UNKNOWN_PROBA = 0.60 (recommended initial value; the validation
   distribution is reported alongside to show it separates correct from
   wrong predictions) and the MIXED cutoffs (second >= 0.35 with a top gap
   <= 0.25: reachable under unit-sum probabilities, unlike tighter gaps
   that would make MIXED mathematically impossible).
"""

from __future__ import annotations

import numpy as np

UNKNOWN_PROBA = 0.60
MIXED_SECOND_PROBA = 0.35
MIXED_GAP = 0.25

UNKNOWN = "UNKNOWN"
MIXED = "MIXED"

VAL_FRACTION = 0.20


def chronological_validation_split(n: int, val_fraction: float = VAL_FRACTION):
    """Last-fraction positions for internal validation (chronological)."""
    cut = int(n * (1.0 - val_fraction))
    idx = np.arange(n)
    return idx[:cut], idx[cut:]


def validation_confidence_stats(model, X_val, y_val) -> dict:
    """Confidence distribution on internal validation (correct vs wrong)."""
    from src.root_cause.classifier import predict_proba

    probas = predict_proba(model, X_val)
    order = np.argsort(-probas, axis=1)
    top = probas[np.arange(len(probas)), order[:, 0]]
    pred = np.array([model.classes_[i] for i in order[:, 0]], dtype=object)
    correct = pred == np.asarray(y_val, dtype=object)
    stats = {"n": int(len(y_val)), "accuracy": float(correct.mean()) if len(y_val) else float("nan"),
             "unknown_threshold": UNKNOWN_PROBA,
             "mixed_second_threshold": MIXED_SECOND_PROBA,
             "mixed_gap_threshold": MIXED_GAP}
    for name, mask in (("correct", correct), ("wrong", ~correct)):
        vals = top[mask]
        stats[f"{name}_n"] = int(mask.sum())
        stats[f"{name}_median_confidence"] = float(np.median(vals)) if len(vals) else float("nan")
        stats[f"{name}_frac_below_threshold"] = float((vals < UNKNOWN_PROBA).mean()) if len(vals) else float("nan")
    return stats

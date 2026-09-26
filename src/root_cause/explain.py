"""Human-readable explanations from actual evidence values + SHAP.

Every sentence cites measured feature/evidence values. SHAP contributions
are worded as "contributing to the classifier's prediction", never as
causal proof. A NOAA sentence is added only when spatial context is
actually available (Delhi only); missing context is never presented as
normal evidence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SHAP_TOP_K = 5


def template_explanation(label: str, row: pd.Series) -> str:
    """Class template instantiated with the row's measured values."""
    z = float(row["z_maxabs"])
    mse = float(row["lstm_target_mse"])
    freeze = max(float(row["temperature_zero_delta_ratio_2h"]),
                 float(row["pressure_zero_delta_ratio_2h"]),
                 float(row["humidity_zero_delta_ratio_2h"]))
    trend = max(abs(float(row["temperature_trend_2h"])),
                abs(float(row["pressure_trend_2h"])),
                abs(float(row["humidity_trend_2h"])))
    multi = float(row["multivariate_max_abs_robust_deviation_2h"])
    if label == "SPIKE":
        return (f"Sudden-change pattern: max|z|={z:.2f} with elevated reconstruction "
                f"error (target MSE={mse:.3f}); consistent with a large instantaneous deviation.")
    if label == "FROZEN":
        return (f"Stability pattern: freeze ratio={freeze:.2f} with weak temporal movement "
                f"(max|z|={z:.2f}); consistent with a prolonged unchanged signal.")
    if label == "DRIFT":
        return (f"Gradual-departure pattern: 2h trend magnitude={trend:.4f}/h with max|z|={z:.2f}; "
                "consistent with a sustained directional change.")
    if label == "CROSS":
        return (f"Multivariate-inconsistency pattern: max robust deviation={multi:.2f}; "
                "one variable disagrees with related signals.")
    if label == "MIXED":
        return ("Multi-pattern evidence: classifier confidence is split across two fault "
                "patterns (see runner-up class and probabilities); consistent with a combined fault.")
    return ("Insufficient/conflicting evidence: classifier confidence below the frozen "
            "threshold or context too sparse to support a known class.")


def shap_top_features(shap_values: np.ndarray, feature_names: list[str],
                      row_values: np.ndarray, k: int = SHAP_TOP_K) -> list[dict]:
    """Top-k contributors by absolute SHAP value, with values and direction."""
    order = np.argsort(-np.abs(np.asarray(shap_values, dtype=float)))[:k]
    out = []
    for i in order:
        value = float(shap_values[i])
        out.append({"feature": feature_names[int(i)],
                    "shap_value": value,
                    "feature_value": float(row_values[int(i)]),
                    "direction": "increases predicted-class support"
                    if value >= 0 else "decreases predicted-class support"})
    return out


def compose_explanation(label: str, row: pd.Series, top_features: list[dict],
                        noaa_sentence: str = "") -> str:
    """Full explanation: template + SHAP contributors + optional NOAA context."""
    parts = [template_explanation(label, row)]
    feats = "; ".join(f"{t['feature']}={t['feature_value']:.3f} "
                      f"(SHAP {t['shap_value']:+.3f}, {t['direction']})" for t in top_features)
    parts.append(f"Top features contributing to the classifier's prediction: {feats}.")
    if noaa_sentence:
        parts.append(noaa_sentence)
    return " ".join(parts)


def noaa_sentence_for(timestamp: str, noaa_lookup: dict) -> str:
    """Spatial-context sentence, or empty when context is unavailable."""
    info = noaa_lookup.get(str(timestamp))
    if not info:
        return ""
    return (f"Spatial context (not ground truth): nearby NOAA stations' median "
            f"temperature differs by {info['temp_diff']:+.2f}C from the target "
            f"({info['n']} stations available).")

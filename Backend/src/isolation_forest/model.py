"""Isolation Forest construction, fitting, and persistence."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

# Deterministic configuration (spec verbatim; no benchmark tuning).
MODEL_SEED = 26073
IF_PARAMS: dict = {
    "n_estimators": 200,
    "max_samples": "auto",
    "contamination": "auto",
    "max_features": 1.0,
    "bootstrap": False,
    "random_state": MODEL_SEED,
    "n_jobs": -1,
}


def build_model() -> IsolationForest:
    """Construct the configured (unfitted) model."""
    return IsolationForest(**IF_PARAMS)


def fit_model(X: np.ndarray) -> IsolationForest:
    """Fit on eligible, feature-complete training rows only."""
    model = build_model()
    model.fit(X)
    return model


def save_artifact(payload: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, path)


def load_artifact(path: str | Path) -> dict:
    return joblib.load(path)

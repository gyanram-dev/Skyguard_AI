"""Transparent tree-based root-cause classifier (RandomForest, fixed config)."""

from __future__ import annotations

import logging

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger("aws_root_cause.classifier")

RF_PARAMS: dict = {
    "n_estimators": 300,
    "max_features": "sqrt",
    "min_samples_leaf": 3,
    "class_weight": "balanced_subsample",
    "random_state": 26073,
    "n_jobs": -1,
}
MODEL_SEED = 26073


def build_classifier():
    """Construct the unfitted classifier (configuration frozen)."""
    from sklearn.ensemble import RandomForestClassifier

    return RandomForestClassifier(**RF_PARAMS)


def fit_classifier(X: pd.DataFrame, y: pd.Series):
    """Fit on labeled sensor-fault rows only; return (model, train_info)."""
    model = build_classifier()
    model.fit(X, y)
    info = {"n_rows": int(len(X)), "classes": list(model.classes_),
            "class_counts": {str(k): int((y == k).sum()) for k in model.classes_}}
    logger.info("Fitted root-cause RF on %d rows: %s", len(X), info["class_counts"])
    return model, info


def predict_proba(model, X: pd.DataFrame) -> np.ndarray:
    """Class probabilities in model.classes_ order."""
    return np.asarray(model.predict_proba(X), dtype=float)


def save_artifact(obj, path: str) -> None:
    """Persist a model artifact (parents created)."""
    import pathlib

    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, path)


def load_artifact(path: str):
    """Load a model artifact."""
    return joblib.load(path)

"""Clean-only training: frozen scaler, chronological split, early stopping.

Scaler: StandardScaler fitted ONLY on eligible, feature-complete CLEAN
training rows, stored and frozen. Chronological fit/validation split:
first 90% of valid clean sequences for fitting, final 10% for validation.
Early stopping monitors clean validation loss exclusively (patience 5,
restore best). ID/OOD data never influences training, scaler, or stopping.
"""

from __future__ import annotations

import logging

import joblib
import numpy as np

from src.lstm_autoencoder import model as M

logger = logging.getLogger("aws_lstm.training")

VAL_FRACTION = 0.10
EARLY_STOP_PATIENCE = 5


def fit_scaler(matrix: np.ndarray, mask: np.ndarray):
    """Fit StandardScaler on clean-train eligible+finite rows only."""
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    scaler.fit(matrix[mask])
    return scaler


def chronological_split(n: int, val_fraction: float = VAL_FRACTION) -> tuple[np.ndarray, np.ndarray]:
    """First (1-f) positions for fit, final f for validation (chronological)."""
    cut = int(n * (1.0 - val_fraction))
    idx = np.arange(n)
    return idx[:cut], idx[cut:]


def train_autoencoder(X: np.ndarray, seed: int = M.MODEL_SEED) -> tuple[object, dict]:
    """Fit the autoencoder; return (model, history_info with actual epochs)."""
    import tensorflow as tf

    M.set_global_seeds(seed)
    n_features = X.shape[2]
    model = M.build_model(n_features)
    n = len(X)
    fit_idx, val_idx = chronological_split(n)
    callbacks = [tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=EARLY_STOP_PATIENCE,
        restore_best_weights=True, verbose=1)]
    history = model.fit(
        X[fit_idx], X[fit_idx],
        validation_data=(X[val_idx], X[val_idx]),
        epochs=M.EPOCHS, batch_size=M.BATCH_SIZE, verbose=2, shuffle=False,
        callbacks=callbacks)
    info = {
        "epochs_requested": M.EPOCHS,
        "epochs_actual": len(history.history["loss"]),
        "early_stopped": len(history.history["loss"]) < M.EPOCHS,
        "n_train_sequences": int(len(fit_idx)),
        "n_val_sequences": int(len(val_idx)),
        "final_train_loss": float(history.history["loss"][-1]),
        "final_val_loss": float(history.history["val_loss"][-1]),
        "best_val_loss": float(min(history.history["val_loss"])),
    }
    logger.info("Trained %d epochs (requested %d); best val_loss=%.6f",
                info["epochs_actual"], M.EPOCHS, info["best_val_loss"])
    return model, info


def save_scaler(scaler, feature_order: list[str], path: str) -> None:
    """Persist the frozen scaler with its feature order."""
    import pathlib

    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"scaler": scaler, "feature_order": list(feature_order),
                 "scaler_type": type(scaler).__name__}, path)


def load_scaler(path: str) -> dict:
    """Load a frozen scaler bundle."""
    return joblib.load(path)

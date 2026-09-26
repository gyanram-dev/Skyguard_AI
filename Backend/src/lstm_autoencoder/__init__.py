"""LSTM sequence-aware anomaly detector for SkyGuard AI (Phase 9).

Clean-train -> causal 12-step sequences -> reconstruction error.
Server-side only. No ensemble, root-cause, SHAP, or API work here.
"""

from src.lstm_autoencoder.model import MODEL_SEED

__all__ = ["MODEL_SEED"]

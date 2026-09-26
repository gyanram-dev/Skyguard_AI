"""First ML anomaly detector for SkyGuard AI: per-dataset Isolation Forest (Phase 7).

Server-side only. No LSTM, no spatial reasoning, no ensemble, no SHAP.
Trained on chronological benchmark-train sensor values (labels never used).
"""

from src.isolation_forest.model import IF_PARAMS, MODEL_SEED, build_model

__all__ = ["IF_PARAMS", "MODEL_SEED", "build_model"]

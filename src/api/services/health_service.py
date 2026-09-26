"""Health reporting over actually-loaded model artifacts."""

from __future__ import annotations

API_VERSION = "1.0.0-phase12"


def report(store) -> dict:
    """Health payload; a model is 'loaded' only if it loaded successfully."""
    return {"status": "ok" if all(v == "loaded" for v in store.model_status.values()) else "degraded",
            "service": "skyguard-api",
            "version": API_VERSION,
            "data_mode": "historical_replay",
            "model_status": dict(store.model_status)}

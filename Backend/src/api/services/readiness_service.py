"""Demo readiness: lightweight capability check, no ML inference.

Reports whether the judge demo can run (replay source, probe models,
evaluation evidence) and exactly which capability is missing when not.
Only filesystem presence is checked; models are NOT loaded here.
"""

from __future__ import annotations

DEFAULT_STATION = "DEL-01"
DEFAULT_SPLIT = "OOD"

PROBE_MODEL_FILES = [
    "models/isolation_forest/{ds}_isolation_forest.joblib",
    "models/ensemble/{ds}_calibration.joblib",
    "models/lstm_autoencoder/{ds}_lstm_autoencoder.keras",
    "models/lstm_autoencoder/{ds}_scaler.joblib",
    "models/root_cause/{ds}_root_cause.joblib",
    "models/root_cause/{ds}_root_cause_explainer.joblib",
]

EVALUATION_FILES = [
    "reports/ensemble/ensemble_metrics.csv",
    "reports/ensemble/event_metrics.csv",
    "reports/ensemble/ood_metrics.csv",
    "reports/ensemble/phase6_phase7_phase9_comparison.csv",
    "reports/root_cause/root_cause_metrics.csv",
    "reports/replay/performance.json",
]


def _dataset_for(store, frontend_id: str) -> str | None:
    entry = next((m for m in store.mapping
                  if m.get("frontend_station_id") == frontend_id), None)
    if entry is None:
        return None
    backend_id = entry.get("backend_station_id")
    return backend_id if backend_id == "delhi" else None


def check(store) -> dict:
    """Capability flags for the default demo scenario (no inference)."""
    root = store.root
    ds = _dataset_for(store, DEFAULT_STATION)
    station_ok = ds is not None
    replay_ok = bool(ds) and (root / "data" / "benchmark" / ds
                              / "test_generalization.csv").is_file()
    probe_ok = bool(ds) and all(
        (root / rel.format(ds=ds)).is_file() for rel in PROBE_MODEL_FILES)
    evaluation_ok = all((root / rel).is_file() for rel in EVALUATION_FILES)
    missing = []
    if not station_ok:
        missing.append(f"default station '{DEFAULT_STATION}' has no detector coverage")
    if station_ok and not replay_ok:
        missing.append(f"replay source test_generalization.csv for '{ds}' is absent")
    if station_ok and not probe_ok:
        missing.append(f"probe model artifacts for '{ds}' are absent")
    if not evaluation_ok:
        missing.append("evaluation evidence artifacts are absent")
    ready = station_ok and replay_ok and probe_ok and evaluation_ok
    return {"ready": ready, "data_mode": "historical_replay",
            "default_station": DEFAULT_STATION if station_ok else None,
            "default_split": DEFAULT_SPLIT,
            "replay_available": replay_ok, "probe_available": probe_ok,
            "evaluation_available": evaluation_ok, "missing": missing}

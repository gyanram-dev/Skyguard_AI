"""Read-only data access layer: cached frozen artifacts, indexed frames.

Everything is loaded once at application startup (or safe lazy init in
tests). Request handlers never touch the filesystem, never train, never
scan full datasets per request beyond indexed lookups.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("skyguard.datastore")

API_VERSION = "1.0.0-phase12"

REQUIRED_FILES = [
    "data/api/station_mapping.json",
    "data/processed/delhi_clean.csv",
    "data/ensemble/delhi_ensemble_predictions.csv",
    "data/root_cause/delhi_root_cause_predictions.csv",
    # NOTE (Phase 21B): benchmark evaluation tables
    # (reports/ensemble/*_event_results.csv,
    # reports/root_cause/end_to_end_diagnosis.csv) are deliberately NOT
    # required to serve: operational alerts derive from frozen detector
    # outputs only, never from labels or event tables.
    "data/noaa/processed/spatial_consistency.csv",
    "data/noaa/metadata/neighbor_graph.csv",
    "models/isolation_forest/delhi_isolation_forest.joblib",
    "models/lstm_autoencoder/delhi_lstm_autoencoder.keras",
    "models/lstm_autoencoder/delhi_scaler.joblib",
    "models/ensemble/delhi_calibration.joblib",
    "models/root_cause/delhi_root_cause.joblib",
    "models/root_cause/delhi_root_cause_explainer.joblib",
]

# Jena artifacts remain available to offline benchmark/regression jobs only.
PIPELINE_DATASETS = ("delhi",)


class DataStore:
    """Cached backend state. Use DataStore.load(root) once, then read."""

    def __init__(self) -> None:
        self.root: Path | None = None
        self.mapping: list[dict] = []
        self.pipeline: dict = {}
        self.noaa_obs: dict = {}
        self.noaa_spatial: dict = {}
        self.alerts: list[dict] = []
        self.alert_index: dict = {}
        self.model_status: dict = {}
        self.model_detail: dict = {}

    @classmethod
    def load(cls, root: str | Path) -> DataStore:
        """Load and validate every artifact; fail fast with exact causes."""
        store = cls()
        store.root = Path(root).resolve()
        missing = [rel for rel in REQUIRED_FILES if not (store.root / rel).exists()]
        if missing:
            raise RuntimeError(f"Missing required artifacts: {missing}")
        store.mapping = [entry for entry in json.loads(
            (store.root / "data" / "api" / "station_mapping.json")
            .read_text(encoding="utf-8"))["stations"]
                         if entry.get("backend_station_id") != "jena"]
        for ds in PIPELINE_DATASETS:
            store.pipeline[ds] = store._load_pipeline(ds)
        store._load_noaa()
        store._build_alerts()
        store._load_models()
        logger.info("DataStore ready: %d stations, %d alerts",
                    len(store.mapping), len(store.alerts))
        return store

    def _load_pipeline(self, ds: str) -> dict:
        obs = pd.read_csv(self.root / "data" / "processed" / f"{ds}_clean.csv",
                          usecols=["timestamp", "temperature_c", "pressure_hpa",
                                   "relative_humidity_pct"])
        ens = pd.read_csv(self.root / "data" / "ensemble" / f"{ds}_ensemble_predictions.csv")
        rc_path = self.root / "data" / "root_cause" / f"{ds}_root_cause_predictions.csv"
        rc = pd.read_csv(rc_path)
        ens_idx = {str(t): i for i, t in enumerate(ens["timestamp"].astype(str))}
        rc_idx = {str(t): i for i, t in enumerate(rc["timestamp"].astype(str))}
        return {"obs": obs, "ens": ens, "rc": rc,
                "ens_idx": ens_idx, "rc_idx": rc_idx,
                "latest": str(obs["timestamp"].iloc[-1])}

    def _load_noaa(self) -> None:
        needed = {m["backend_station_id"] for m in self.mapping
                  if m.get("backend_station_id") and m["source_dataset"] == "noaa_ghcnh"}
        spatial = pd.read_csv(self.root / "data" / "noaa" / "processed" / "spatial_consistency.csv")
        for sid in needed:
            obs = pd.read_csv(self.root / "data" / "noaa" / "processed" / f"{sid}_2022_2024.csv",
                              usecols=["timestamp_utc", "temperature_c",
                                       "relative_humidity_pct", "altimeter_setting_hpa"])
            sub = spatial[spatial["station_id"] == sid].reset_index(drop=True)
            self.noaa_obs[sid] = obs
            self.noaa_spatial[sid] = {str(t): i for i, t in
                                      enumerate(sub["timestamp_utc"].astype(str))}
            self.noaa_spatial[sid + ":frame"] = sub

    def _build_alerts(self) -> None:
        from src.api.services import anomaly_service

        self.alerts = anomaly_service.build_alerts(self)
        self.alert_index = {a["alert_id"]: a for a in self.alerts}

    def _load_models(self) -> None:
        import joblib

        checks = {
            "statistical": lambda: True,
            "isolation_forest": lambda: [joblib.load(
                self.root / f"models/isolation_forest/{ds}_isolation_forest.joblib")
                for ds in PIPELINE_DATASETS],
            "lstm_autoencoder": self._load_lstm,
            "ensemble": lambda: [joblib.load(
                self.root / f"models/ensemble/{ds}_calibration.joblib")
                for ds in PIPELINE_DATASETS],
            "root_cause": lambda: [joblib.load(
                self.root / f"models/root_cause/{ds}_root_cause.joblib")
                for ds in PIPELINE_DATASETS] + [joblib.load(
                self.root / f"models/root_cause/{ds}_root_cause_explainer.joblib")
                for ds in PIPELINE_DATASETS],
        }
        for name, loader in checks.items():
            try:
                loader()
                self.model_status[name] = "loaded"
            except Exception as exc:  # noqa: BLE001 - recorded, reported
                logger.error("Model %s failed to load: %s", name, exc)
                self.model_status[name] = "unavailable"
                self.model_detail[name] = str(exc)[:300]

    def _load_lstm(self):
        import tensorflow as tf

        return [tf.keras.models.load_model(
            self.root / f"models/lstm_autoencoder/{ds}_lstm_autoencoder.keras")
            for ds in PIPELINE_DATASETS] + [__import__("joblib").load(
            self.root / f"models/lstm_autoencoder/{ds}_scaler.joblib")
            for ds in PIPELINE_DATASETS]

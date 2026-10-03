"""Read-only data access layer: cached frozen artifacts, indexed frames.

Data artifacts are read once at application startup (or safe lazy init in
tests). Inference artifacts are only checked for presence here and load
lazily on first use (see _load_models). Request handlers never touch the
filesystem, never train, never scan full datasets per request beyond
indexed lookups.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("skyguard.datastore")

API_VERSION = "1.0.0-phase12"

# Data artifacts read once at startup.
DATA_FILES = [
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
]

# Jena artifacts remain available to offline benchmark/regression jobs only.
PIPELINE_DATASETS = ("delhi",)

# Frozen inference artifacts grouped by the health-visible family name.
# The DataStore records their presence only: loading belongs to the single
# lazy owner (src.api.services.scoring.get_models, which caches per dataset).
MODEL_ARTIFACTS = {
    # Deterministic in-process rules: no artifact exists or is needed.
    "statistical": (),
    "isolation_forest": tuple(
        f"models/isolation_forest/{ds}_isolation_forest.joblib"
        for ds in PIPELINE_DATASETS),
    "lstm_autoencoder": tuple(
        f"models/lstm_autoencoder/{ds}_lstm_autoencoder.keras"
        for ds in PIPELINE_DATASETS) + tuple(
        f"models/lstm_autoencoder/{ds}_scaler.joblib" for ds in PIPELINE_DATASETS),
    "ensemble": tuple(
        f"models/ensemble/{ds}_calibration.joblib" for ds in PIPELINE_DATASETS),
    "root_cause": tuple(
        f"models/root_cause/{ds}_root_cause.joblib" for ds in PIPELINE_DATASETS)
        + tuple(f"models/root_cause/{ds}_root_cause_explainer.joblib"
                for ds in PIPELINE_DATASETS),
}

# Fail-fast gate: every artifact the API needs to serve, data and models.
REQUIRED_FILES = DATA_FILES + [rel for rels in MODEL_ARTIFACTS.values() for rel in rels]

# spatial_consistency.csv is streamed in bounded chunks: serving keeps only
# one row per station (see _load_noaa), never the full 448k-row table.
SPATIAL_ROWS_PER_CHUNK = 50_000


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
        """Observations per mapped station + one spatial row per station.

        Serving reads exactly one spatial_consistency row per station: the row
        whose timestamp_utc equals that station's latest observation (see
        station_service.noaa_snapshot). The frozen table is therefore streamed
        in bounded chunks and only the matching rows are retained, instead of
        holding the 448k-row frame plus a duplicated per-station slice each.
        """
        needed = {m["backend_station_id"] for m in self.mapping
                  if m.get("backend_station_id") and m["source_dataset"] == "noaa_ghcnh"}
        latest: dict[str, str] = {}
        for sid in needed:
            obs = pd.read_csv(self.root / "data" / "noaa" / "processed" / f"{sid}_2022_2024.csv",
                              usecols=["timestamp_utc", "temperature_c",
                                       "relative_humidity_pct", "altimeter_setting_hpa"])
            self.noaa_obs[sid] = obs
            if len(obs):
                latest[sid] = str(obs["timestamp_utc"].iloc[-1])
        spatial_path = (self.root / "data" / "noaa" / "processed"
                        / "spatial_consistency.csv")
        columns = list(pd.read_csv(spatial_path, nrows=0).columns)
        wanted = {f"{sid}\0{ts}" for sid, ts in latest.items()}
        matched: dict[str, list[pd.DataFrame]] = {}
        chunk = None
        for chunk in pd.read_csv(spatial_path, chunksize=SPATIAL_ROWS_PER_CHUNK):
            key = (chunk["station_id"].astype(str) + "\0"
                   + chunk["timestamp_utc"].astype(str))
            mask = key.isin(wanted)
            if bool(mask.any()):
                hits = chunk.loc[mask]
                for sid, part in hits.groupby(hits["station_id"].astype(str), sort=False):
                    matched.setdefault(str(sid), []).append(part)
        del chunk
        for sid in needed:
            parts = matched.get(sid)
            sub = (pd.concat(parts, ignore_index=True) if parts
                   else pd.DataFrame(columns=columns))
            ts = latest.get(sid)
            # The index maps the only timestamp serving can look up (that
            # station's latest observation) to its retained row; empty when no
            # spatial row matches, which is the existing 'unavailable' path.
            self.noaa_spatial[sid] = {ts: 0} if (parts and ts is not None) else {}
            self.noaa_spatial[sid + ":frame"] = sub

    def _build_alerts(self) -> None:
        from src.api.services import anomaly_service

        self.alerts = anomaly_service.build_alerts(self)
        self.alert_index = {a["alert_id"]: a for a in self.alerts}

    def _load_models(self) -> None:
        """Record inference-artifact availability; loading is deferred.

        Startup used to joblib/TensorFlow-load every artifact only to discard
        the returned objects and report a status string: measured +261 MiB
        resident at boot (184 MiB of it the TensorFlow import alone) against a
        512 MiB instance budget, while the real inference path already loads
        and caches the same bundle lazily (src.api.services.scoring.get_models,
        the only model cache). Status values:
        'deferred' — artifact present, loads on first inference;
        'unavailable' — required artifact missing;
        'loaded' — the deterministic statistical rules need no artifact and
        are always usable in-process.
        """
        for name, artifacts in MODEL_ARTIFACTS.items():
            missing = [rel for rel in artifacts if not (self.root / rel).is_file()]
            if missing:
                logger.error("Model %s artifacts missing: %s", name, ", ".join(missing))
                self.model_status[name] = "unavailable"
                self.model_detail[name] = "missing artifacts: " + ", ".join(missing)
            else:
                self.model_status[name] = "deferred" if artifacts else "loaded"

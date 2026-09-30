"""Historical station timeline service (obs + existing detector events).

Reads the artifacts written by ``src.showcase.build_timeline`` (frozen
ensemble output for Delhi, the calibrated station detector for GHCNh
stations) and never computes a verdict at request time. When no artifact
exists for a station, the service still returns the station's real
observations but declares ``detector.available = false`` so the UI can
state HISTORICAL DATA — DETECTOR VERDICT UNAVAILABLE instead of implying
a verdict it does not have.
"""

from __future__ import annotations

import json
import logging
import math

from src.api.services import station_service as SS

logger = logging.getLogger("skyguard.timeline")

ARTIFACT_DIR = "data/showcase/timeline"
MAX_EVENTS_DEFAULT = 400
MAX_POINTS_DEFAULT = 900

_CACHE: dict[str, dict] = {}


def load_artifact(store, station_id: str) -> dict | None:
    """Cached timeline artifact for a station (None when not built)."""
    path = store.root / ARTIFACT_DIR / f"{station_id}.json"
    if not path.is_file():
        return None
    if station_id not in _CACHE:
        try:
            _CACHE[station_id] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - absence is honest
            logger.warning("timeline artifact unreadable for %s: %s",
                           station_id, exc)
            return None
    return _CACHE[station_id]


def reset_cache() -> None:
    """Drop cached artifacts (used by tests after a rebuild)."""
    _CACHE.clear()


def _downsample(series: dict, max_points: int) -> dict:
    stamps = series.get("timestamps") or []
    n = len(stamps)
    if n <= max_points:
        return series
    step = int(math.ceil(n / max_points))
    idx = list(range(0, n, step))
    out = {"timestamps": [stamps[i] for i in idx]}
    for key in ("temperature", "humidity", "pressure"):
        values = series.get(key) or []
        out[key] = [values[i] if i < len(values) else None for i in idx]
    out["stride"] = step
    out["reported_points"] = len(idx)
    return out


def _fallback_series(store, entry: dict, max_points: int) -> dict:
    """Real observations, strided, when no artifact covers the station."""
    import pandas as pd

    frame, ts_col, _basis = _frames(store, entry)
    n = len(frame)
    step = max(1, int(math.ceil(n / max_points)))
    idx = list(range(0, n, step))
    values = {
        "temperature": "temperature_c",
        "humidity": "relative_humidity_pct",
        "pressure": ("altimeter_setting_hpa"
                     if entry["source_dataset"] == "noaa_ghcnh"
                     else "pressure_hpa"),
    }
    out = {"timestamps": [str(frame[ts_col].iloc[i]) for i in idx],
           "stride": step, "reported_points": len(idx)}
    for name, column in values.items():
        out[name] = [_finite(pd.to_numeric(frame[column], errors="coerce").iloc[i])
                     for i in idx]
    return out


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _frames(store, entry: dict):
    if entry["source_dataset"] == "noaa_ghcnh":
        return store.noaa_obs[entry["backend_station_id"]], "timestamp_utc", "UTC"
    return store.pipeline[entry["backend_station_id"]]["obs"], "timestamp", "IST"


def timeline(store, station_id: str, max_points: int = MAX_POINTS_DEFAULT,
             max_events: int = MAX_EVENTS_DEFAULT) -> dict:
    """Historical timeline: observations + existing detector events."""
    entry = SS.get_mapping(store, station_id)
    if entry is None:
        raise KeyError(station_id)
    artifact = load_artifact(store, station_id)
    if artifact is None:
        frame, ts_col, _basis = _frames(store, entry)
        stamps = frame[ts_col].astype(str)
        detector = SS.detector_registry_entry(store, entry)
        coverage = "FROZEN_ENSEMBLE" if entry["source_dataset"] == "delhi_clean" \
            else ("CALIBRATED_STATISTICAL" if detector is not None else "UNAVAILABLE")
        return {
            "station_id": station_id,
            "city": entry["city"],
            "pressure_basis": SS.pressure_basis(entry),
            "period": {"start": str(stamps.iloc[0]), "end": str(stamps.iloc[-1])},
            "observations": int(len(frame)),
            "cadence_min": None,
            "series": _fallback_series(store, entry, max_points),
            "events": [],
            "events_returned": 0,
            "detector": {"available": False, "coverage": "UNAVAILABLE",
                         "detector_type": None, "flags_total": 0,
                         "note": "HISTORICAL DATA — DETECTOR VERDICT UNAVAILABLE: "
                                 "no stored detector output covers this station."},
            "data_source": SS.data_source_label(entry),
            "note": ("Only real recorded observations are shown; no anomaly "
                     "verdict is invented for this station."),
        }
    events = artifact.get("events", [])
    detector = artifact.get("detector", {})
    return {
        "station_id": artifact["station_id"],
        "city": artifact["city"],
        "pressure_basis": artifact.get("pressure_basis"),
        "period": artifact.get("period"),
        "observations": artifact.get("observations"),
        "cadence_min": artifact.get("cadence_min"),
        "series": _downsample(artifact.get("series", {}), max_points),
        "events": events[:max_events],
        "events_returned": min(len(events), max_events),
        "events_total": len(events),
        "detector": detector,
        "data_source": SS.data_source_label(entry),
        "note": detector.get("note"),
    }


def default_anchor(store, station_id: str) -> str | None:
    """Latest detector-flagged observation for a station (or None).

    Used as the investigation anchor so a judge lands on a flagged
    observation when one exists, and on the latest observation when the
    station has no detector events at all.
    """
    artifact = load_artifact(store, station_id)
    if not artifact:
        return None
    events = artifact.get("events") or []
    if not events:
        return None
    return max(str(e.get("timestamp")) for e in events)

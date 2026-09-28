"""Station lookup, snapshots, and history over frozen datasets."""

from __future__ import annotations

import math

import pandas as pd

EVIDENCE_COMPLETENESS = {"FULL_EVIDENCE": 1.0, "PARTIAL_EVIDENCE": 0.67,
                         "LOW_CONTEXT": 0.33, "INSUFFICIENT_EVIDENCE": None}

VARIABLE_COLUMNS = {"temperature": "temperature_c", "humidity": "relative_humidity_pct",
                    "pressure": "pressure_hpa"}
NOAA_VARIABLE_COLUMNS = {"temperature": "temperature_c", "humidity": "relative_humidity_pct",
                         "pressure": "altimeter_setting_hpa"}


def get_mapping(store, frontend_id: str) -> dict | None:
    """Mapping entry for a frontend station ID (case-sensitive)."""
    for entry in store.mapping:
        if entry["frontend_station_id"] == frontend_id:
            return entry
    return None


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def pipeline_snapshot(store, backend_id: str) -> dict:
    """Latest observation + frozen pipeline outputs for Jena/Delhi."""
    bundle = store.pipeline[backend_id]
    obs = bundle["obs"]
    latest = str(obs["timestamp"].iloc[-1])
    row = obs.iloc[-1]
    ens_row = None
    if latest in bundle["ens_idx"]:
        ens_row = bundle["ens"].iloc[bundle["ens_idx"][latest]]
    rc_row = None
    if latest in bundle["rc_idx"]:
        rc_row = bundle["rc"].iloc[bundle["rc_idx"][latest]]
    return {"timestamp": latest, "obs": row, "ens": ens_row, "rc": rc_row}


def pipeline_status(ens_row) -> str:
    """healthy / review / anomaly from frozen ensemble outputs."""
    if ens_row is None:
        return "review"
    if int(ens_row["ens_median_flag"]) == 1:
        return "anomaly"
    if str(ens_row["availability"]) != "FULL_EVIDENCE":
        return "review"
    return "healthy"


def noaa_snapshot(store, backend_id: str) -> dict | None:
    """Latest NOAA observation + spatial evidence row (or None)."""
    obs = store.noaa_obs.get(backend_id)
    if obs is None or len(obs) == 0:
        return None
    latest = str(obs["timestamp_utc"].iloc[-1])
    frame = store.noaa_spatial[backend_id + ":frame"]
    idx = store.noaa_spatial[backend_id]
    return {"timestamp": latest, "obs": obs.iloc[-1],
            "spatial": frame.iloc[idx[latest]] if latest in idx else None}


def noaa_max_score(spatial_row) -> tuple[float | None, str | None]:
    """Largest available spatial robust score and its variable."""
    if spatial_row is None:
        return None, None
    best, which = None, None
    for prefix in ("temp", "rh", "pres"):
        value = _num(spatial_row.get(f"{prefix}_robust_score"))
        if value is not None and (best is None or value > best):
            best, which = value, prefix
    return best, which


def history_series(store, mapping: dict, variable: str, hours: int) -> list[dict]:
    """Timestamp/value pairs; missing values preserved as null."""
    backend_id = mapping["backend_station_id"]
    if mapping["source_dataset"] == "noaa_ghcnh":
        frame = store.noaa_obs[backend_id]
        ts_col, col = "timestamp_utc", NOAA_VARIABLE_COLUMNS[variable]
    else:
        frame = store.pipeline[backend_id]["obs"]
        ts_col, col = "timestamp", VARIABLE_COLUMNS[variable]
    ts = pd.to_datetime(frame[ts_col])
    cutoff = ts.max() - pd.Timedelta(hours=hours)
    mask = ts >= cutoff
    points = []
    for stamp, value in zip(frame.loc[mask, ts_col].astype(str), frame.loc[mask, col]):
        points.append({"timestamp": stamp, variable: _num(value)})
    return points


def history_range(store, mapping: dict, variable: str, end: str,
                  hours: int) -> list[dict]:
    """Timestamp/value pairs for the window ending at an event timestamp.

    Investigation history is anchored at the SELECTED alert/event time,
    never at the dataset latest: rows later than the event cannot inform
    a decision about it. String-domain comparison inside one dataset
    frame keeps naive-local (Delhi/Jena) and UTC (NOAA) frames in their
    native basis with no fabricated offsets.
    """
    backend_id = mapping["backend_station_id"]
    if mapping["source_dataset"] == "noaa_ghcnh":
        frame = store.noaa_obs[backend_id]
        ts_col, col = "timestamp_utc", NOAA_VARIABLE_COLUMNS[variable]
    else:
        frame = store.pipeline[backend_id]["obs"]
        ts_col, col = "timestamp", VARIABLE_COLUMNS[variable]
    stamps = frame[ts_col].astype(str)
    end_key = str(end)
    start_key = str(pd.Timestamp(end_key) - pd.Timedelta(hours=hours))
    mask = (stamps <= end_key) & (stamps >= start_key)
    points = []
    for stamp, value in zip(frame.loc[mask, ts_col].astype(str), frame.loc[mask, col]):
        points.append({"timestamp": stamp, variable: _num(value)})
    return points

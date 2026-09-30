"""Station lookup, snapshots, and history over frozen datasets."""

from __future__ import annotations

import logging
import math

import pandas as pd

logger = logging.getLogger("skyguard.station_service")

# Trailing window scanned for the signal-health indicator (rows are bounded
# by the window so a station page never scans a full multi-year history).
SIGNAL_HEALTH_WINDOW_DAYS = 90
_SIGNAL_HEALTH_CACHE: dict[str, dict] = {}

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


INDIAN_OPERATIONAL = "indian_operational"
BENCHMARK_INTERNAL = "benchmark_internal"
OFFLINE_SCOPE = "offline"


def operational_scope(entry: dict) -> str:
    """Explicit scope: Jena is benchmark-only, never Indian-operational."""
    if not entry.get("backend_station_id"):
        return OFFLINE_SCOPE
    if entry.get("backend_station_id") == "jena":
        return BENCHMARK_INTERNAL
    return INDIAN_OPERATIONAL


def probe_capable(entry: dict) -> bool:
    """True only for stations the interactive probe can actually score.

    Mirrors probe_service.resolve_dataset: contextual-only GHCNh stations
    have no detector models, so probing them would dead-end. The UI uses
    this flag to keep the demo reliable instead of discovering a 422.
    """
    from src.api.dependencies import PIPELINE_DATASETS

    backend_id = entry.get("backend_station_id")
    return (bool(backend_id)
            and entry.get("source_dataset") != "noaa_ghcnh"
            and backend_id in PIPELINE_DATASETS)


def maintenance_review(store, entry: dict, current_anomalous: bool) -> dict:
    """Evidence-based maintenance signal (longitudinal, no prediction).

    Counts operational alert episodes for the station in the trailing 30
    days: >=3 (or a current anomaly with prior episodes) recommends a
    review; 1-2 is an elevated watch; 0 needs no action. Stations with
    no detector coverage report NOT_APPLICABLE. Conventions are fixed
    and documented, not fitted. This is NOT a failure prediction.
    """
    backend_id = entry.get("backend_station_id")
    if not backend_id or entry.get("source_dataset") == "noaa_ghcnh":
        return {"state": "NOT_APPLICABLE",
                "reason": "No detector-covered history for this station.",
                "episodes_30d": 0, "currently_anomalous": bool(current_anomalous)}
    frontend = entry.get("frontend_station_id", "")
    cutoff = None
    recent = 0
    for alert in getattr(store, "alerts", []):
        if alert.get("station_id") != frontend:
            continue
        try:
            import pandas as pd

            stamp = pd.Timestamp(str(alert.get("timestamp")))
            if cutoff is None:
                latest = max(pd.Timestamp(str(a.get("timestamp")))
                             for a in store.alerts
                             if a.get("station_id") == frontend)
                cutoff = latest - pd.Timedelta(days=30)
            if stamp >= cutoff:
                recent += 1
        except (TypeError, ValueError):
            continue
    if recent >= 3 or (current_anomalous and recent >= 1):
        state = "MAINTENANCE_REVIEW_RECOMMENDED"
    elif recent >= 1 or current_anomalous:
        state = "ELEVATED_WATCH"
    else:
        state = "NO_ACTION_INDICATED"
    return {"state": state,
            "reason": ("Evidence-based review flag from trailing alert "
                       "history; not a failure prediction."),
            "episodes_30d": int(recent),
            "currently_anomalous": bool(current_anomalous)}


def _detector_cadence(store, backend_id: str) -> float:
    """Registry cadence for a station, or the documented 30-min default."""
    try:
        from src.detection import registry as REG

        entry = REG.get(getattr(store, "root", ".") or ".", backend_id)
        if entry is not None:
            return float(entry.get("cadence", 30))
    except Exception:  # noqa: BLE001 - documented default is acceptable
        pass
    return 30.0


def signal_health(store, entry: dict) -> dict:
    """Longitudinal signal-health indicator from the station's loaded history.

    Descriptive facts over a trailing window: confirmed flatline runs
    (>= 6 consecutive identical readings, causal; relative humidity at
    0/100 excluded) plus a documented watch level. Explicitly **not** a
    failure prediction or remaining-useful-life estimate; the measured
    rule and benchmark validation live in ``src.detection.freeze``.
    """
    from src.detection import freeze as FE
    from src.features.feature_builder import CADENCE_HORIZONS

    backend_id = entry.get("backend_station_id")
    if not backend_id:
        return {"state": "UNAVAILABLE",
                "reason": "No backend station is mapped for this station."}
    if backend_id in _SIGNAL_HEALTH_CACHE:
        return _SIGNAL_HEALTH_CACHE[backend_id]
    result: dict = {"state": "UNAVAILABLE",
                    "reason": "No loaded history for this station."}
    try:
        data = None
        cadence = 30.0
        if entry.get("source_dataset") == "noaa_ghcnh":
            frame = store.noaa_obs.get(backend_id)
            if frame is not None and len(frame):
                cadence = _detector_cadence(store, backend_id)
                data = pd.DataFrame({
                    "timestamp": frame["timestamp_utc"].astype(str),
                    "temperature_c": pd.to_numeric(frame["temperature_c"],
                                                   errors="coerce"),
                    "pressure_hpa": pd.to_numeric(frame["altimeter_setting_hpa"],
                                                  errors="coerce"),
                    "relative_humidity_pct": pd.to_numeric(
                        frame["relative_humidity_pct"], errors="coerce")})
        else:
            bundle = store.pipeline.get(backend_id)
            cadence = float(CADENCE_HORIZONS[backend_id]["expected_interval_min"])
            if bundle:
                data = bundle["obs"][["timestamp", "temperature_c",
                                       "pressure_hpa",
                                       "relative_humidity_pct"]].copy()
        if data is not None and len(data):
            window_rows = max(96, int(SIGNAL_HEALTH_WINDOW_DAYS * 24 * 60 / cadence))
            total = int(len(data))
            window = data.tail(window_rows).reset_index(drop=True)
            result = FE.summarise(window, cadence)
            result.update({
                "window_days": SIGNAL_HEALTH_WINDOW_DAYS,
                "window_start": str(window["timestamp"].iloc[0]),
                "window_end": str(window["timestamp"].iloc[-1]),
                "rows_in_window": int(len(window)),
                "rows_available": total,
                "cadence_min": float(cadence)})
    except Exception as exc:  # noqa: BLE001 - absence stays honest
        logger.warning("signal health unavailable for %s: %s", backend_id, exc)
        result = {"state": "UNAVAILABLE",
                  "reason": "Signal-health scan failed; no indicator reported."}
    _SIGNAL_HEALTH_CACHE[backend_id] = result
    return result


def capability_notes(store, entry: dict) -> list[str]:
    """Honest capability limitations for display (no fake health)."""
    notes: list[str] = []
    if operational_scope(entry) == BENCHMARK_INTERNAL:
        notes.append("Internal benchmark only; not an Indian operational station.")
    if entry.get("source_dataset") == "noaa_ghcnh":
        # A calibrated station detector changes what is true about the station:
        # it does have a detector, just a partial (T/P/RH) one with no probe.
        if detector_registry_entry(store, entry) is not None:
            notes.append("Calibrated station-specific detector (PARTIAL): "
                         "temperature, pressure and relative humidity, with "
                         "this station's own calibrated thresholds.")
        else:
            notes.append("Historical context observations; no detector models "
                         "cover it.")
    if not entry.get("backend_station_id"):
        notes.append("No backend data; offline placeholder.")
    return notes


def available_variables(store, entry: dict) -> list[str]:
    """Variables with at least one measured value in the loaded station data."""
    backend_id = entry.get("backend_station_id")
    if not backend_id:
        return []
    if entry.get("source_dataset") == "noaa_ghcnh":
        frame = store.noaa_obs.get(backend_id)
        columns = {"temperature": "temperature_c",
                   "pressure": "altimeter_setting_hpa",
                   "relative_humidity": "relative_humidity_pct"}
    else:
        bundle = store.pipeline.get(backend_id)
        frame = bundle["obs"] if bundle else None
        columns = {"temperature": "temperature_c",
                   "pressure": "pressure_hpa",
                   "relative_humidity": "relative_humidity_pct"}
    if frame is None:
        return []
    return [name for name, column in columns.items()
            if column in frame and pd.to_numeric(frame[column], errors="coerce").notna().any()]


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


# ---------------------------------------------------------------------------
# Phase 25 — explicit station data-capability model.
#
# detector_capability:
#   FULL_TPR      T + P + RH genuinely available AND the frozen detector
#                 pipeline covers the station (Delhi only).
#   PARTIAL       detector-covered but some T/P/RH variables are missing.
#   CONTEXT_ONLY  real observations carried for network/spatial context;
#                 no detector models cover the station, so NO anomaly
#                 verdict exists for it (GHCNh stations today).
#   UNAVAILABLE   no usable observation stream.
#
# data_mode is REPORTED, never inferred from provider configuration: the
# serving mode is historical_replay, and live connectivity is a separate
# measured fact (see network_service.live_connected_count).
# ---------------------------------------------------------------------------
DETECTOR_CAPABILITY_FULL_TPR = "FULL_TPR"
DETECTOR_CAPABILITY_PARTIAL = "PARTIAL"
DETECTOR_CAPABILITY_CONTEXT_ONLY = "CONTEXT_ONLY"
DETECTOR_CAPABILITY_UNAVAILABLE = "UNAVAILABLE"

# Serving truth: one historical dataset is instrumented as replay for the
# detector pipeline; the network layer as a whole serves historical data.
DATA_MODE_HISTORICAL = "HISTORICAL"
DATA_MODE_REPLAY = "REPLAY"
DATA_MODE_UNAVAILABLE = "LIVE_UNAVAILABLE"


def observation_counts(store, entry: dict) -> int:
    """Rows actually loaded for the station (measured, never claimed)."""
    backend_id = entry.get("backend_station_id")
    if not backend_id:
        return 0
    if entry.get("source_dataset") == "noaa_ghcnh":
        frame = store.noaa_obs.get(backend_id)
        return int(len(frame)) if frame is not None else 0
    bundle = store.pipeline.get(backend_id)
    return int(len(bundle["obs"])) if bundle else 0


def observation_period(store, entry: dict) -> dict:
    """Measured first/last timestamps for the station (None when no data)."""
    backend_id = entry.get("backend_station_id")
    if not backend_id:
        return {"start_time": None, "end_time": None}
    if entry.get("source_dataset") == "noaa_ghcnh":
        frame = store.noaa_obs.get(backend_id)
        ts_col = "timestamp_utc"
    else:
        bundle = store.pipeline.get(backend_id)
        frame = bundle["obs"] if bundle else None
        ts_col = "timestamp"
    if frame is None or len(frame) == 0:
        return {"start_time": None, "end_time": None}
    stamps = frame[ts_col].astype(str)
    return {"start_time": str(stamps.iloc[0]), "end_time": str(stamps.iloc[-1])}


def station_state_name(entry: dict, city: str) -> str | None:
    """Indian state/UT for the station city (display metadata only)."""
    states = {
        "Delhi": "Delhi", "Delhi (Safdarjung)": "Delhi",
        "Jaipur": "Rajasthan", "Lucknow": "Uttar Pradesh",
        "Mumbai": "Maharashtra", "Bhopal": "Madhya Pradesh",
        "Bengaluru": "Karnataka", "Chennai": "Tamil Nadu",
        "Kolkata": "West Bengal", "Guwahati": "Assam",
        "Chandigarh": "Chandigarh", "Pune": "Maharashtra",
        "Hyderabad": "Telangana", "Thiruvananthapuram": "Kerala",
    }
    return states.get(city)


def data_source_label(entry: dict) -> str:
    """Visible provenance label (Phase 12); never generic 'real-time data'."""
    dataset = entry.get("source_dataset")
    if dataset == "delhi_clean":
        return "Historical AWS dataset (repository bulk)"
    if dataset == "noaa_ghcnh":
        return "NOAA GHCNh (doi:10.25921/jp3d-3v19)"
    return "Controlled demonstration"


def pressure_basis(entry: dict) -> str | None:
    """Documented pressure basis so GHCNh is never conflated with AWS."""
    if entry.get("source_dataset") == "delhi_clean":
        return "station_level_hpa"
    if entry.get("source_dataset") == "noaa_ghcnh":
        return "altimeter_qnh_hpa"
    return None


def detector_registry_entry(store, entry: dict) -> dict | None:
    """Calibrated detector declaration for a station, or None.

    Read from the single detector registry written by
    ``src.detection.calibrate``; a missing registry/artifact means the
    station genuinely has no station-level detector.
    """
    backend_id = entry.get("backend_station_id")
    if not backend_id:
        return None
    try:
        from src.detection import registry as REG

        return REG.get(getattr(store, "root", ".") or ".", backend_id)
    except Exception:  # noqa: BLE001 - absence means no detector
        return None


def detector_capability(store, entry: dict, variables: list[str]) -> str:
    """Classify the station per the explicit capability rules."""
    if not entry.get("backend_station_id"):
        return DETECTOR_CAPABILITY_UNAVAILABLE
    variables_set = set(variables)
    if probe_capable(entry):
        if {"temperature", "pressure", "relative_humidity"} <= variables_set:
            return DETECTOR_CAPABILITY_FULL_TPR
        return DETECTOR_CAPABILITY_PARTIAL
    if entry.get("source_dataset") == "noaa_ghcnh":
        # A calibrated station-specific statistical detector promotes the
        # station from context-only to PARTIAL (honest, measured coverage).
        if detector_registry_entry(store, entry) is not None:
            if {"temperature", "pressure", "relative_humidity"} <= variables_set:
                return DETECTOR_CAPABILITY_PARTIAL
        # Real observations carried for context; spatial evidence is the
        # neighbour layer's job, not a station-level detector verdict.
        return DETECTOR_CAPABILITY_CONTEXT_ONLY
    return DETECTOR_CAPABILITY_UNAVAILABLE


def detector_state(store, entry: dict) -> dict | None:
    """Serving detector state for one station (registry-backed, or None)."""
    reg_entry = detector_registry_entry(store, entry)
    if reg_entry is None:
        return None
    from src.detection.registry import ENTRY_FIELDS

    state = {field: reg_entry.get(field) for field in ENTRY_FIELDS}
    state.update({"backend_station_id": reg_entry.get("backend_station_id"),
                  "source": "calibrated station-specific statistical detector"})
    return state


def spatial_context_capability(entry: dict) -> str:
    """Whether the station can contribute spatial/context evidence."""
    if entry.get("backend_station_id") == "delhi":
        # Delhi aligns mapped GHCNh neighbours causally (scoring._serving_neighbors).
        return "AVAILABLE"
    if entry.get("source_dataset") == "noaa_ghcnh":
        return "CONTEXT_NEIGHBOR"
    return "UNAVAILABLE"


def station_data_mode(store, entry: dict) -> str:
    """Reported data mode (never inferred from a configured provider)."""
    if not entry.get("backend_station_id"):
        return DATA_MODE_UNAVAILABLE
    if probe_capable(entry):
        return DATA_MODE_REPLAY
    return DATA_MODE_HISTORICAL


def capability_profile(store, entry: dict) -> dict:
    """One additive capability block per station (Phase 2 contract)."""
    variables = available_variables(store, entry)
    return {
        "station_name": entry.get("station_name")
        or ("Delhi-NCR AWS" if entry.get("source_dataset") == "delhi_clean"
            else entry.get("city")),
        "city": entry.get("city"),
        "state": station_state_name(entry, entry.get("city", "")),
        "country": "India",
        "data_source": data_source_label(entry),
        "pressure_basis": pressure_basis(entry),
        "data_mode": station_data_mode(store, entry),
        "observation_count": observation_counts(store, entry),
        **observation_period(store, entry),
        "variables_available": variables,
        "detector_capability": detector_capability(store, entry, variables),
        "spatial_context_capability": spatial_context_capability(entry),
        "detector": detector_state(store, entry),
    }

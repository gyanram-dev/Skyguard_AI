"""Station-aware canonical normalization for bulk Indian observations.

One station at a time, always: partition -> chronological sort ->
duplicate/out-of-order accounting -> verified unit conversion ->
canonical frame with original values preserved alongside. Timestamps
are UTC internally (Delhi naive-local IST is shifted explicitly, as in
the existing spatial evaluator). Unknown units invalidate the variable,
never guess. Dew point is never humidity; MSL is never station
pressure.
"""

from __future__ import annotations

import pandas as pd

IST_OFFSET = pd.Timedelta(hours=5, minutes=30)

# Verified conversions only.
TEMP_UNITS = {"c": 0.0, "celsius": 0.0, "degc": 0.0}
PRESSURE_UNITS = {"hpa": 1.0, "hectopascal": 1.0, "pa": 0.01, "pascal": 0.01}


def to_celsius(value, units: str | None) -> float | None:
    """Verified temperature conversion; None when unknown/unusable."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    import math

    if not math.isfinite(number):
        return None
    unit = str(units or "c").strip().lower()
    if unit in TEMP_UNITS:
        return number + TEMP_UNITS[unit]
    if unit in ("f", "fahrenheit", "degf"):
        return (number - 32.0) * 5.0 / 9.0
    return None


def to_hpa(value, units: str | None) -> float | None:
    """Verified pressure conversion; None when unknown/unusable."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    import math

    if not math.isfinite(number):
        return None
    unit = str(units or "hpa").strip().lower()
    if unit in PRESSURE_UNITS:
        return number * PRESSURE_UNITS[unit]
    return None


def normalize_station_frame(station_id: str, frame: pd.DataFrame,
                            mapping: dict, source: str,
                            native_tz: str = "UTC") -> pd.DataFrame:
    """Canonicalize one station's raw frame (deterministic).

    ``mapping`` names the raw columns: timestamp/temperature/humidity/
    pressure (+ optional *_unit columns). Returns canonical columns plus
    ``original_*`` provenance columns, sorted chronologically with a
    fresh RangeIndex (original order never leaks).
    """
    work = frame.copy()
    ts_raw = work[mapping["timestamp"]].astype(str)
    if native_tz.upper() == "IST":
        stamps = pd.to_datetime(ts_raw, errors="coerce") - IST_OFFSET
    else:
        stamps = pd.to_datetime(ts_raw, errors="coerce", utc=True)
    temp_unit = work[mapping["temperature_unit"]] \
        if mapping.get("temperature_unit") in work.columns else "c"
    pres_unit = work[mapping["pressure_unit"]] \
        if mapping.get("pressure_unit") in work.columns else "hpa"
    out = pd.DataFrame({
        "station_id": station_id,
        "timestamp": stamps.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "temperature_c": [to_celsius(v, u) for v, u in
                          zip(work[mapping["temperature"]].tolist(),
                              temp_unit.tolist() if hasattr(temp_unit, "tolist")
                              else [temp_unit] * len(work))],
        "relative_humidity_pct": pd.to_numeric(
            work[mapping["humidity"]], errors="coerce")
        if mapping.get("humidity") in work.columns else None,
        "pressure_hpa": [to_hpa(v, u) for v, u in
                         zip(work[mapping["pressure"]].tolist(),
                             pres_unit.tolist() if hasattr(pres_unit, "tolist")
                             else [pres_unit] * len(work))]
        if mapping.get("pressure") in work.columns else None,
        "source": source,
        "original_timestamp": ts_raw,
        "original_temperature": work[mapping["temperature"]].astype(str),
    })
    out["original_relative_humidity"] = work[mapping["humidity"]].astype(str) \
        if mapping.get("humidity") in work.columns else None
    out["original_pressure"] = work[mapping["pressure"]].astype(str) \
        if mapping.get("pressure") in work.columns else None
    out["pressure_basis"] = mapping.get("pressure_basis", "unknown")
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out


def normalize_multistation(frame: pd.DataFrame, station_col: str,
                           per_station: dict, source: str) -> pd.DataFrame:
    """Station-aware bulk normalization (partition, never mixed)."""
    parts = []
    for station in sorted(frame[station_col].astype(str).unique().tolist()):
        sub = frame[frame[station_col].astype(str) == station]
        cfg = per_station.get(station, per_station.get("*", {}))
        parts.append(normalize_station_frame(
            station, sub, cfg.get("mapping", {}), source,
            native_tz=cfg.get("native_tz", "UTC")))
    return pd.concat(parts, ignore_index=True) if parts \
        else pd.DataFrame()

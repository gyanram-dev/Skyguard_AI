"""Per-station quality audit and multi-station overlap analysis (Phase 8A).

Audit only: flags integrity problems, never deletes or alters observations.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.noaa import config as C

logger = logging.getLogger("aws_noaa.audit")

MAPPED_VALUE_COLUMNS = [
    "temperature_c",
    "station_level_pressure_hpa",
    "sea_level_pressure_hpa",
    "altimeter_setting_hpa",
    "relative_humidity_pct",
    "dew_point_temperature_c",
]

# A jump larger than this in 30 minutes is reported as a candidate
# discontinuity for human review, never as a confirmed fault.
DISCONTINUITY_DELTA_C = 15.0


def _longest_missing_run(mask: np.ndarray) -> int:
    """Length of the longest consecutive True run."""
    best = cur = 0
    for flag in mask:
        cur = cur + 1 if flag else 0
        best = max(best, cur)
    return int(best)


def audit_station(frame: pd.DataFrame, station: dict) -> dict:
    """Audit one processed station frame. Return a JSON-serializable record."""
    sid = station["ghcnh_id"]
    ts = pd.to_datetime(frame["timestamp_utc"], utc=True)
    deltas = ts.sort_values().diff().dropna()
    median_minutes = float(deltas.median().total_seconds() / 60.0) if len(deltas) else float("nan")
    out_of_order = int((ts.diff().dropna() < pd.Timedelta(0)).sum())
    rec: dict = {
        "station_id": sid,
        "station_name": station["name"],
        "rows": int(len(frame)),
        "first_timestamp": str(ts.min()),
        "last_timestamp": str(ts.max()),
        "duplicate_timestamps": int(frame["duplicate_timestamp"].sum()),
        "out_of_order_rows": out_of_order,
        "median_cadence_minutes": round(median_minutes, 2),
        "cadence_minutes_p10": round(float(deltas.quantile(0.10).total_seconds() / 60.0), 2),
        "cadence_minutes_p90": round(float(deltas.quantile(0.90).total_seconds() / 60.0), 2),
    }
    for col in MAPPED_VALUE_COLUMNS:
        vals = pd.to_numeric(frame[col], errors="coerce")
        missing = vals.isna()
        lo, hi = C.PHYSICAL_BOUNDS.get(col, (None, None)) if col in C.PHYSICAL_BOUNDS else (None, None)
        outside = ((vals < lo) | (vals > hi)).sum() if lo is not None else 0
        non_finite = int((~np.isfinite(vals.to_numpy(dtype=float, na_value=np.nan))
                          & ~missing.to_numpy()).sum())
        rec[f"{col}_missing"] = int(missing.sum())
        rec[f"{col}_missing_fraction"] = round(float(missing.mean()), 4)
        rec[f"{col}_longest_missing_run"] = _longest_missing_run(missing.to_numpy())
        rec[f"{col}_non_finite"] = non_finite
        rec[f"{col}_outside_physical_bounds"] = int(outside)
        rec[f"{col}_min"] = (None if vals.dropna().empty else round(float(vals.min()), 2))
        rec[f"{col}_max"] = (None if vals.dropna().empty else round(float(vals.max()), 2))
    temp = pd.to_numeric(frame["temperature_c"], errors="coerce")
    dew = pd.to_numeric(frame["dew_point_temperature_c"], errors="coerce")
    rec["dewpoint_above_temperature"] = int(((dew > temp) & dew.notna() & temp.notna()).sum())
    jumps = temp.sort_index().diff().abs()
    rec["temperature_jumps_gt_15C_per_step"] = int((jumps > DISCONTINUITY_DELTA_C).sum())
    logger.info("%s: %d rows, %s -> %s", sid, len(frame), rec["first_timestamp"],
                rec["last_timestamp"])
    return rec


def overlap_analysis(frames: dict[str, pd.DataFrame]) -> dict:
    """Common overlap period plus hourly temperature-coverage statistics."""
    firsts = {sid: pd.to_datetime(f["timestamp_utc"], utc=True).min() for sid, f in frames.items()}
    lasts = {sid: pd.to_datetime(f["timestamp_utc"], utc=True).max() for sid, f in frames.items()}
    start, end = max(firsts.values()), min(lasts.values())
    hours = pd.date_range(start.floor("h"), end.ceil("h"), freq="h", tz="UTC")
    reporting: dict[str, set] = {}
    for sid, frame in frames.items():
        ok = frame[pd.to_numeric(frame["temperature_c"], errors="coerce").notna()]
        reporting[sid] = set(pd.to_datetime(ok["timestamp_utc"], utc=True).dt.floor("h"))
    counts = np.array([sum(h in reporting[sid] for sid in frames) for h in hours])
    n = len(hours)
    return {
        "common_start": start.isoformat(),
        "common_end": end.isoformat(),
        "common_hours": int(n),
        "hours_with_ge2_stations_temp": int((counts >= 2).sum()),
        "hours_with_ge5_stations_temp": int((counts >= 5).sum()),
        "hours_with_all_stations_temp": int((counts == len(frames)).sum()),
        "fraction_ge2": round(float((counts >= 2).mean()), 4),
        "fraction_ge5": round(float((counts >= 5).mean()), 4),
        "fraction_all": round(float((counts == len(frames)).mean()), 4),
        "per_station": {sid: {"first": firsts[sid].isoformat(), "last": lasts[sid].isoformat(),
                              "rows": int(len(frames[sid]))} for sid in frames},
    }

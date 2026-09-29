"""Standardize GHCNh parquet files into per-station processed CSVs.

No imputation, no interpolation, no clipping, no row deletion. Timestamps
are parsed as UTC (GHCNh DATE is UTC per documentation). The -9999 provider
sentinel becomes NaN. Duplicate timestamps are flagged, never dropped.
"""

from __future__ import annotations

import logging

import pandas as pd

from src.noaa import config as C

logger = logging.getLogger("aws_noaa.process")

# Raw parquet columns consumed (values + provider quality codes of primaries).
RAW_COLUMNS = [
    "STATION", "Station_name", "DATE",
    "temperature", "temperature_Quality_Code",
    "dew_point_temperature",
    "station_level_pressure", "station_level_pressure_Quality_Code",
    "sea_level_pressure", "sea_level_pressure_Quality_Code",
    "altimeter",
    "relative_humidity", "relative_humidity_Quality_Code",
]

PROCESSED_COLUMNS = [
    "timestamp_utc", "ghcnh_station_id", "station_name",
    "temperature_c", "temperature_qc",
    "dew_point_temperature_c",
    "station_level_pressure_hpa", "station_level_pressure_qc",
    "sea_level_pressure_hpa", "sea_level_pressure_qc",
    "altimeter_setting_hpa",
    "relative_humidity_pct", "relative_humidity_qc",
    "duplicate_timestamp", "source_file",
]


def _numeric(series: pd.Series) -> pd.Series:
    """Numeric values with the provider sentinel mapped to NaN."""
    vals = pd.to_numeric(series, errors="coerce")
    return vals.mask(vals == C.MISSING_SENTINEL)


def standardize_station_frame(raw: pd.DataFrame, station_id: str,
                              source_file: str) -> pd.DataFrame:
    """Map one station's raw year-concatenated frame to the SkyGuard schema."""
    missing = [c for c in RAW_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"{station_id}: raw file lacks columns {missing}")
    ids = raw["STATION"].astype(str).unique().tolist()
    if ids != [station_id]:
        raise ValueError(f"{station_id}: file mixes station IDs {ids}")
    try:
        parsed_ts = pd.to_datetime(raw["DATE"], format="mixed", utc=True)
    except (ValueError, TypeError) as exc:
        bad = pd.Series(raw["DATE"].astype(str)).unique().tolist()
        raise ValueError(f"{station_id}: unparseable timestamps {bad[:5]}") from exc
    out = pd.DataFrame({
        "timestamp_utc": parsed_ts,
        "ghcnh_station_id": station_id,
        "station_name": raw["Station_name"].astype(str),
        "temperature_c": _numeric(raw["temperature"]),
        "temperature_qc": raw["temperature_Quality_Code"].astype(str),
        "dew_point_temperature_c": _numeric(raw["dew_point_temperature"]),
        "station_level_pressure_hpa": _numeric(raw["station_level_pressure"]),
        "station_level_pressure_qc": raw["station_level_pressure_Quality_Code"].astype(str),
        "sea_level_pressure_hpa": _numeric(raw["sea_level_pressure"]),
        "sea_level_pressure_qc": raw["sea_level_pressure_Quality_Code"].astype(str),
        "altimeter_setting_hpa": _numeric(raw["altimeter"]),
        "relative_humidity_pct": _numeric(raw["relative_humidity"]),
        "relative_humidity_qc": raw["relative_humidity_Quality_Code"].astype(str),
        "source_file": source_file,
    })
    if out["timestamp_utc"].isna().any():
        bad = raw.loc[out["timestamp_utc"].isna(), "DATE"].unique().tolist()
        raise ValueError(f"{station_id}: unparseable timestamps {bad[:5]}")
    out = out.sort_values("timestamp_utc").reset_index(drop=True)
    out["duplicate_timestamp"] = out["timestamp_utc"].duplicated(keep=False)
    return out[PROCESSED_COLUMNS]


def build_processed_station(station_id: str, raw_paths: list[str],
                            dest_path: str) -> pd.DataFrame:
    """Concatenate a station's year files and write the processed CSV."""
    frames = []
    for path in raw_paths:
        raw = pd.read_parquet(path, columns=RAW_COLUMNS)
        frames.append(standardize_station_frame(raw, station_id, path.split("/")[-1]))
    full = pd.concat(frames, ignore_index=True)
    full = full.sort_values("timestamp_utc").reset_index(drop=True)
    full["duplicate_timestamp"] = full["timestamp_utc"].duplicated(keep=False)
    full[PROCESSED_COLUMNS].to_csv(dest_path, index=False)
    logger.info("%s: %d processed rows -> %s", station_id, len(full), dest_path)
    return full

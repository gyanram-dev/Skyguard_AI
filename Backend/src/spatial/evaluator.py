"""Spatial-consistency evaluation: consistency frames, AWS validation, metrics.

Conventions:
- All comparisons in UTC. The Delhi AWS series is stored in IST
  (source column Date_Time_IST); it is converted IST -> UTC (-5:30) before
  any alignment. NOAA GHCNh DATE is already UTC.
- One output row per target native observation; no resampling, no fill.
- Pressure basis is altimeter_setting_hpa ONLY (universal coverage per the
  Phase 8A audit). station_level_pressure and sea_level_pressure never
  enter a comparison.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.spatial.alignment import align_neighbor

logger = logging.getLogger("aws_spatial.evaluator")

# Output variable prefix -> processed column. Kept separate end to end.
VARIABLES = (
    ("temp", "temperature_c"),
    ("rh", "relative_humidity_pct"),
    ("pres", "altimeter_setting_hpa"),
)

AWS_IST_OFFSET = pd.Timedelta(hours=5, minutes=30)


def _neighbor_value_matrix(target_times: pd.Series,
                           neighbor_frames: dict[str, pd.DataFrame],
                           selected: list[str], column: str) -> np.ndarray:
    """Aligned neighbor values, shape (n_target, n_selected); NaN = unavailable."""
    n, k = len(target_times), len(selected)
    mat = np.full((n, k), np.nan)
    for j, nid in enumerate(selected):
        frame = neighbor_frames[nid]
        pos = align_neighbor(target_times, frame["timestamp_utc"])
        ok = pos.to_numpy() >= 0
        vals = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        mat[ok, j] = vals[pos.to_numpy()[ok]]
    return mat


def build_consistency_frame(station_id: str, target: pd.DataFrame,
                            neighbor_frames: dict[str, pd.DataFrame],
                            selected: list[str]) -> pd.DataFrame:
    """Per-observation spatial evidence for one target station."""
    times = pd.to_datetime(target["timestamp_utc"], utc=True)
    expected = len(selected)
    out: dict[str, object] = {
        "station_id": station_id,
        "timestamp_utc": times.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "expected_neighbor_count": expected,
    }
    mats: dict[str, np.ndarray] = {}
    for prefix, column in VARIABLES:
        mat = _neighbor_value_matrix(times, neighbor_frames, selected, column)
        mats[prefix] = mat
        tgt = pd.to_numeric(target[column], errors="coerce").to_numpy(dtype=float)
        n_avail = np.isfinite(mat).sum(axis=1)
        ref = np.full(len(target), np.nan)
        has_any = n_avail >= 1
        ref[has_any] = np.nanmedian(mat[has_any], axis=1)
        diff = tgt - ref
        abs_diff = np.abs(diff)
        mad = np.full(len(target), np.nan)
        has_two = n_avail >= 2
        mad[has_two] = np.nanmedian(np.abs(mat[has_two] - ref[has_two, None]), axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            score = abs_diff / mad
        score[~(mad > 0)] = np.nan
        tgt_missing = ~np.isfinite(tgt)
        context = np.full(len(target), "MEDIUM_CONTEXT", dtype=object)
        context[(n_avail == 0) | tgt_missing] = "UNAVAILABLE"
        low = ((n_avail == 1) & ~tgt_missing) | ((n_avail >= 2) & ~(mad > 0) & ~tgt_missing)
        context[low] = "LOW_CONTEXT"
        context[(n_avail >= expected) & (expected > 0) & np.isfinite(score)] = "HIGH_CONTEXT"
        out[f"{prefix}_target"] = tgt
        out[f"{prefix}_neighbor_median"] = ref
        out[f"{prefix}_difference"] = np.where(tgt_missing, np.nan, diff)
        out[f"{prefix}_abs_difference"] = np.where(tgt_missing, np.nan, abs_diff)
        out[f"{prefix}_robust_score"] = score
        out[f"{prefix}_neighbor_count"] = n_avail
        out[f"{prefix}_context"] = context
    stacked = np.stack(
        [np.isfinite(mats[prefix]) for prefix, _ in VARIABLES], axis=2)  # n x k x v
    avail_any = stacked.any(axis=2).sum(axis=1)
    out["available_neighbor_count"] = avail_any
    status = np.full(len(target), "NO_ALIGNMENT", dtype=object)
    status[(avail_any > 0) & (avail_any < expected)] = "PARTIAL_ALIGNMENT"
    status[(avail_any >= expected) & (expected > 0)] = "FULL_ALIGNMENT"
    out["temporal_alignment_status"] = status
    return pd.DataFrame(out)


def build_aws_validation(aws_path: str, context_frames: dict[str, pd.DataFrame],
                         context_ids: list[str]) -> pd.DataFrame:
    """Delhi AWS readings versus NOAA Delhi-context medians (offline only).

    NOAA is contextual comparison, never ground truth; no label is derived.
    AWS station pressure is reported for reference but never differenced
    against altimeter (different physical quantities).
    """
    aws = pd.read_csv(aws_path, usecols=["timestamp", "temperature_c",
                                         "pressure_hpa", "relative_humidity_pct"])
    aws_utc = pd.to_datetime(aws["timestamp"]) - AWS_IST_OFFSET
    aws_utc = aws_utc.dt.tz_localize("UTC")
    expected = len(context_ids)
    out: dict[str, object] = {
        "timestamp_ist": aws["timestamp"].astype(str).values,
        "timestamp_utc": aws_utc.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "aws_temperature_c": pd.to_numeric(aws["temperature_c"], errors="coerce").values,
        "aws_relative_humidity_pct": pd.to_numeric(
            aws["relative_humidity_pct"], errors="coerce").values,
        "aws_pressure_hpa_station": pd.to_numeric(
            aws["pressure_hpa"], errors="coerce").values,
        "expected_context_stations": expected,
    }
    for prefix, column, aws_col in (
            ("temp", "temperature_c", "aws_temperature_c"),
            ("rh", "relative_humidity_pct", "aws_relative_humidity_pct")):
        mat = _neighbor_value_matrix(aws_utc, context_frames, context_ids, column)
        tgt = out[aws_col].astype(float)
        n_avail = np.isfinite(mat).sum(axis=1)
        ref = np.full(len(aws), np.nan)
        has_any = n_avail >= 1
        ref[has_any] = np.nanmedian(mat[has_any], axis=1)
        diff = tgt - ref
        mad = np.full(len(aws), np.nan)
        has_two = n_avail >= 2
        mad[has_two] = np.nanmedian(np.abs(mat[has_two] - ref[has_two, None]), axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            score = np.abs(diff) / mad
        score[~(mad > 0)] = np.nan
        tgt_missing = ~np.isfinite(tgt)
        context = np.full(len(aws), "MEDIUM_CONTEXT", dtype=object)
        context[(n_avail == 0) | tgt_missing] = "UNAVAILABLE"
        low = ((n_avail == 1) & ~tgt_missing) | ((n_avail >= 2) & ~(mad > 0) & ~tgt_missing)
        context[low] = "LOW_CONTEXT"
        context[(n_avail >= expected) & (expected > 0) & np.isfinite(score)] = "HIGH_CONTEXT"
        out[f"ctx_{prefix}_median"] = ref
        out[f"ctx_{prefix}_difference"] = np.where(tgt_missing, np.nan, diff)
        out[f"ctx_{prefix}_robust_score"] = score
        out[f"ctx_{prefix}_station_count"] = n_avail
        out[f"ctx_{prefix}_context"] = context
    alt = _neighbor_value_matrix(aws_utc, context_frames, context_ids,
                                "altimeter_setting_hpa")
    alt_med = np.full(len(aws), np.nan)
    alt_any = np.isfinite(alt).sum(axis=1) >= 1
    alt_med[alt_any] = np.nanmedian(alt[alt_any], axis=1)
    out["ctx_altimeter_median_hpa"] = alt_med
    out["ctx_altimeter_station_count"] = np.isfinite(alt).sum(axis=1)
    return pd.DataFrame(out)

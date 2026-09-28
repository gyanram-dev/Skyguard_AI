"""Historical batch validation over Phase 2 cleaned datasets.

Reads data/processed/*_clean.csv (read-only) and emits one quality row
per observation with the flags listed in the Phase 2.5 specification.
Vectorized and deterministic: same input -> byte-identical output.

Does NOT modify inputs, does NOT interpolate, does NOT fabricate values.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data_quality.freeze_checks import (
    detect_frozen_runs_with_threshold,
    freeze_threshold_rows,
)
from src.data_quality.physical_checks import is_physical_sanity_fault
from src.data_quality.quality_engine import (
    COMMUNICATION_GAP,
    DATA_AVAILABILITY_EVENT,
    DATA_INTEGRITY_FAULT,
    PASS,
    PHYSICAL_SANITY_FAULT,
    POSSIBLE_FREEZE,
)
from src.data_quality.timeline_checks import (
    compute_elapsed_minutes,
    detect_batch_timestamp_flags,
    detect_communication_gap,
    gap_threshold_minutes,
)

QUALITY_COLUMNS = [
    "timestamp",
    "source_dataset",
    "timestamp_valid",
    "timestamp_duplicate",
    "timestamp_out_of_order",
    "elapsed_minutes_since_prev",
    "communication_gap",
    "gap_duration_minutes",
    "temperature_missing",
    "humidity_missing",
    "pressure_missing",
    "any_core_missing",
    "missing_core_count",
    "temperature_possible_freeze",
    "pressure_possible_freeze",
    "humidity_possible_freeze",
    "physical_sanity_fault",
    "quality_status",
    "quality_reason",
    "ml_eligible",
]


def validate_dataframe(df_clean: pd.DataFrame, dataset_name: str,
                       cadence_min: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Validate a Phase 2 cleaned dataframe. Return (quality_df, summary).

    An explicit cadence (minutes, e.g. inferred from uploaded data) drives
    gap/freeze thresholds instead of the frozen dataset table; existing
    callers pass nothing and are unaffected.
    """
    key = dataset_name.lower()
    if key not in ("jena", "delhi"):
        raise ValueError(f"Unknown dataset '{dataset_name}'. Must be 'jena' or 'delhi'.")
    n = len(df_clean)
    threshold = gap_threshold_minutes(key, cadence_min)
    freeze_threshold = freeze_threshold_rows(key, cadence_min)

    # --- Timestamps (strict parse; cleaned data is ISO-8601 strings) ---
    dt_series = pd.to_datetime(df_clean["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    timestamp_valid = (~dt_series.isna()).astype(int)

    ts_flags = detect_batch_timestamp_flags(dt_series)
    ts_dup = ts_flags["timestamp_duplicate"].astype(int)
    ts_ooo = ts_flags["timestamp_out_of_order"].astype(int)

    elapsed = compute_elapsed_minutes(dt_series)
    gap_df = detect_communication_gap(elapsed, threshold)
    comm_gap = gap_df["communication_gap"].astype(int)
    gap_duration = gap_df["gap_duration_minutes"].astype(float)

    # --- Missingness from actual NaN state (equals Phase 2 flags for Delhi) ---
    t_miss = df_clean["temperature_c"].isna().astype(int)
    h_miss = df_clean["relative_humidity_pct"].isna().astype(int)
    p_miss = df_clean["pressure_hpa"].isna().astype(int)
    any_miss = ((t_miss + h_miss + p_miss) > 0).astype(int)
    miss_count = (t_miss + h_miss + p_miss).astype(int)

    # --- Frozen runs (gap rows break runs) ---
    is_gap_bool = comm_gap.astype(bool)
    t_froz, t_events = detect_frozen_runs_with_threshold(
        df_clean["temperature_c"], is_gap_bool, freeze_threshold
    )
    p_froz, p_events = detect_frozen_runs_with_threshold(
        df_clean["pressure_hpa"], is_gap_bool, freeze_threshold
    )
    h_froz, h_events = detect_frozen_runs_with_threshold(
        df_clean["relative_humidity_pct"], is_gap_bool, freeze_threshold
    )

    # --- Physical sanity (vectorized RH bounds + non-finite scan) ---
    rh = pd.to_numeric(df_clean["relative_humidity_pct"], errors="coerce")
    temp_num = pd.to_numeric(df_clean["temperature_c"], errors="coerce")
    pres_num = pd.to_numeric(df_clean["pressure_hpa"], errors="coerce")
    sanity_fault = (
        ((rh < 0) | (rh > 100)).fillna(False)
        | temp_num.apply(lambda v: bool(np.isinf(v)) if pd.notna(v) else False)
        | pres_num.apply(lambda v: bool(np.isinf(v)) if pd.notna(v) else False)
        | rh.apply(lambda v: bool(np.isinf(v)) if pd.notna(v) else False)
    ).astype(int)

    # --- Status via deterministic priority (vectorized) ---
    integrity = ((timestamp_valid == 0) | (ts_dup == 1) | (ts_ooo == 1))
    gap_m = comm_gap == 1
    avail_m = any_miss == 1
    san_m = sanity_fault == 1
    froz_m = (t_froz == 1) | (p_froz == 1) | (h_froz == 1)

    conditions = [integrity, gap_m, avail_m, san_m, froz_m]
    choices = [
        DATA_INTEGRITY_FAULT,
        COMMUNICATION_GAP,
        DATA_AVAILABILITY_EVENT,
        PHYSICAL_SANITY_FAULT,
        POSSIBLE_FREEZE,
    ]
    status = np.select(conditions, choices, default=PASS)
    ml_eligible = np.where(froz_m & ~(integrity | gap_m | avail_m | san_m), 1,
                    np.where((status == PASS) | (status == POSSIBLE_FREEZE), 1, 0)).astype(int)

    # --- Reasons (vectorized string assembly, deterministic order) ---
    reason = pd.Series([""] * n, index=df_clean.index, dtype=object)
    def _append(mask: pd.Series, text_fn) -> None:
        nonlocal reason
        m = mask.fillna(False).astype(bool) if isinstance(mask, pd.Series) else mask
        add = pd.Series([""] * n, index=df_clean.index, dtype=object)
        idx = df_clean.index[m]
        vals = text_fn(idx)
        add.loc[idx] = vals
        sep = ((reason != "") & (add != "")).map(lambda b: ";" if b else "")
        reason = reason + sep + add

    _append(timestamp_valid == 0, lambda idx: pd.Series(["timestamp_invalid_or_missing"] * len(idx), index=idx))
    _append(ts_dup == 1, lambda idx: pd.Series(["timestamp_duplicate"] * len(idx), index=idx))
    _append(ts_ooo == 1, lambda idx: pd.Series(["timestamp_out_of_order"] * len(idx), index=idx))
    _append(gap_m, lambda idx: pd.Series(
        ["communication_gap_{:.1f}min".format(v) for v in gap_duration.loc[idx]], index=idx))
    _append(avail_m, lambda idx: pd.Series(
        ["missing_core_count_{}".format(int(v)) for v in miss_count.loc[idx]], index=idx))
    _append(san_m, lambda idx: pd.Series([_sanity_reason(i, df_clean) for i in idx], index=idx))
    _append((t_froz == 1), lambda idx: pd.Series(["possible_freeze_temperature"] * len(idx), index=idx))
    _append((p_froz == 1), lambda idx: pd.Series(["possible_freeze_pressure"] * len(idx), index=idx))
    _append((h_froz == 1), lambda idx: pd.Series(["possible_freeze_humidity"] * len(idx), index=idx))
    reason = reason.mask(reason == "", "all_checks_passed")

    quality_df = pd.DataFrame(
        {
            "timestamp": df_clean["timestamp"],
            "source_dataset": df_clean["source_dataset"],
            "timestamp_valid": timestamp_valid,
            "timestamp_duplicate": ts_dup,
            "timestamp_out_of_order": ts_ooo,
            "elapsed_minutes_since_prev": elapsed.astype(float),
            "communication_gap": comm_gap,
            "gap_duration_minutes": gap_duration,
            "temperature_missing": t_miss,
            "humidity_missing": h_miss,
            "pressure_missing": p_miss,
            "any_core_missing": any_miss,
            "missing_core_count": miss_count,
            "temperature_possible_freeze": t_froz.astype(int),
            "pressure_possible_freeze": p_froz.astype(int),
            "humidity_possible_freeze": h_froz.astype(int),
            "physical_sanity_fault": sanity_fault,
            "quality_status": status,
            "quality_reason": reason.values,
            "ml_eligible": ml_eligible,
        }
    )
    assert list(quality_df.columns) == QUALITY_COLUMNS
    assert len(quality_df) == n

    ts_strings = df_clean["timestamp"].astype(str)
    summary = {
        "dataset": key,
        "rows": int(n),
        "gap_threshold_minutes": float(threshold),
        "freeze_threshold_rows": int(freeze_threshold),
        "status_counts": {str(k): int(v) for k, v in pd.Series(status).value_counts().items()},
        "ml_eligible": int((ml_eligible == 1).sum()),
        "ml_not_eligible": int((ml_eligible == 0).sum()),
        "communication_gap_rows": int(comm_gap.sum()),
        "availability_rows": int(((status == DATA_AVAILABILITY_EVENT)).sum()),
        "integrity_rows": int(((status == DATA_INTEGRITY_FAULT)).sum()),
        "sanity_rows": int(((status == PHYSICAL_SANITY_FAULT)).sum()),
        "freeze_rows": int(((status == POSSIBLE_FREEZE)).sum()),
        "freeze_events": _attach_event_timestamps(
            {"temperature": t_events, "pressure": p_events, "humidity": h_events},
            ts_strings,
        ),
    }
    return quality_df, summary


def _sanity_reason(idx_label, df_clean: pd.DataFrame) -> str:
    fault, reason = is_physical_sanity_fault(
        df_clean.loc[idx_label, "temperature_c"],
        df_clean.loc[idx_label, "pressure_hpa"],
        df_clean.loc[idx_label, "relative_humidity_pct"],
    )
    return reason if fault else "physical_sanity_fault"


def _attach_event_timestamps(events: dict, ts_strings: pd.Series) -> dict:
    out: dict = {}
    for var, ev_list in events.items():
        enriched = []
        for ev in ev_list:
            enriched.append(
                {
                    "affected_variable": var,
                    "run_length": ev["run_length"],
                    "start_timestamp": str(ts_strings.iloc[ev["start_pos"]]),
                    "end_timestamp": str(ts_strings.iloc[ev["end_pos"]]),
                }
            )
        out[var] = enriched
    return out

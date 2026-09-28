"""Timeline integrity checks: timestamps, cadence, communication gaps.

Pure, deterministic helpers shared by the batch validator and the
streaming quality engine. No ML, no Phase 3 imports.
"""

from __future__ import annotations

import pandas as pd

# Single source of truth for sampling cadence (minutes).
EXPECTED_INTERVAL_MIN = {
    "jena": 10,
    "delhi": 5,
}

# A communication gap is flagged when elapsed time exceeds
# expected_interval * GAP_FACTOR (i.e. Jena > 15 min, Delhi > 7.5 min).
GAP_FACTOR = 1.5


def gap_threshold_minutes(dataset_name: str, cadence_min: float | None = None) -> float:
    """Return the communication-gap threshold in minutes for a dataset.

    An explicit cadence (e.g. inferred from uploaded data) overrides the
    frozen dataset table; existing callers pass nothing and are unaffected.
    """
    if cadence_min is not None:
        if not cadence_min > 0:
            raise ValueError(f"Invalid cadence '{cadence_min}'. Must be positive.")
        return float(cadence_min) * GAP_FACTOR
    key = dataset_name.lower()
    if key not in EXPECTED_INTERVAL_MIN:
        raise ValueError(f"Unknown dataset '{dataset_name}'. Must be 'jena' or 'delhi'.")
    return EXPECTED_INTERVAL_MIN[key] * GAP_FACTOR


def parse_timestamp_strict(value: object) -> pd.Timestamp | None:
    """Parse a timestamp value; return None when missing or invalid.

    Never raises, never coerces silently: unparseable input is reported
    as a timestamp integrity fault by the caller.
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        return pd.to_datetime(text, errors="raise")
    except Exception:
        return None


def detect_batch_timestamp_flags(dt_series: pd.Series) -> pd.DataFrame:
    """Detect duplicate and out-of-order timestamps in a batch series.

    duplicate: timestamp value already seen earlier in the batch.
    out_of_order: timestamp earlier than the immediately previous row.
    Both are evaluated in row order (no sorting).
    """
    n = len(dt_series)
    is_dup = [False] * n
    is_ooo = [False] * n
    seen: set = set()
    prev = None
    for i, ts in enumerate(dt_series):
        if pd.isna(ts):
            prev = None
            continue
        key = str(ts)
        if key in seen:
            is_dup[i] = True
        else:
            seen.add(key)
        if prev is not None and ts < prev:
            is_ooo[i] = True
        prev = ts
    return pd.DataFrame(
        {"timestamp_duplicate": is_dup, "timestamp_out_of_order": is_ooo}
    )


def compute_elapsed_minutes(dt_series: pd.Series) -> pd.Series:
    """Minutes elapsed since the previous row (NaN for the first row)."""
    return (dt_series - dt_series.shift(1)).dt.total_seconds() / 60.0


def detect_communication_gap(elapsed_minutes: pd.Series, threshold: float) -> pd.DataFrame:
    """Flag rows whose elapsed time exceeds the gap threshold.

    gap_duration_minutes records the elapsed time for gap rows, else 0.0.
    The first row (NaN elapsed) is never a gap.
    """
    is_gap = (elapsed_minutes > threshold).fillna(False).astype(bool)
    duration = elapsed_minutes.where(is_gap, 0.0).fillna(0.0).astype(float)
    return pd.DataFrame(
        {"communication_gap": is_gap.astype(int), "gap_duration_minutes": duration}
    )

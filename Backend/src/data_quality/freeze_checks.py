"""Integrity-level frozen-value (stuck sensor) detection.

A single repeated value is NOT a freeze. A POSSIBLE_FREEZE requires a
run of identical consecutive readings spanning a physical duration:

    FREEZE_DURATION_HOURS = 6 (configuration constant)

converted to row counts by dataset cadence:

    Jena  (10-min): 6 * 60 / 10 = 36 consecutive readings
    Delhi (5-min):  6 * 60 / 5  = 72 consecutive readings

Thresholds are derived, never hard-coded per dataset outside config.
NaN breaks a run. A communication-gap row starts a new run (values on
either side of an outage must not be joined into one freeze event).

A possible freeze is a CANDIDATE flag, never a confirmed fault, and
remains ML eligible so the ML layer can confirm severity later.
"""

from __future__ import annotations

import pandas as pd

from src.data_quality.timeline_checks import EXPECTED_INTERVAL_MIN

# Physical-duration threshold for a possible freeze (hours).
FREEZE_DURATION_HOURS = 6


def freeze_threshold_rows(dataset_name: str, cadence_min: float | None = None) -> int:
    """Consecutive identical readings spanning FREEZE_DURATION_HOURS.

    An explicit cadence (e.g. inferred from uploaded data) overrides the
    frozen dataset table; existing callers pass nothing and are unaffected.
    """
    if cadence_min is not None:
        if not cadence_min > 0:
            raise ValueError(f"Invalid cadence '{cadence_min}'. Must be positive.")
        return max(2, int(round(FREEZE_DURATION_HOURS * 60 / cadence_min)))
    key = dataset_name.lower()
    if key not in EXPECTED_INTERVAL_MIN:
        raise ValueError(f"Unknown dataset '{dataset_name}'. Must be 'jena' or 'delhi'.")
    return int(FREEZE_DURATION_HOURS * 60 / EXPECTED_INTERVAL_MIN[key])


def detect_frozen_runs_with_threshold(
    values: pd.Series,
    is_gap_row: pd.Series,
    threshold_rows: int,
) -> tuple[pd.Series, list[dict]]:
    """Flag rows in identical-value runs with length >= threshold_rows."""
    n = len(values)
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    gap = is_gap_row.to_numpy(dtype=bool) if len(is_gap_row) == n else [False] * n

    run_id = [-1] * n
    run_len_at_row: list[int] = [0] * n
    # Monotonic run counter: ids are never reused, so NaN/gap resets can
    # never merge runs from different parts of the timeline.
    next_id = 0
    cur_id = -1
    cur_len = 0
    prev_val: float | None = None

    for i in range(n):
        v = arr[i]
        if pd.isna(v):
            # Missing values terminate the current run and start no run.
            cur_id = -1
            cur_len = 0
            prev_val = None
            run_len_at_row[i] = 0
            continue
        if gap[i]:
            # A gap row starts a fresh run: values across an outage must
            # not be joined into one freeze event.
            cur_id = next_id
            next_id += 1
            cur_len = 1
            prev_val = v
            run_id[i] = cur_id
            run_len_at_row[i] = cur_len
            continue
        if prev_val is not None and v == prev_val:
            cur_len += 1
            run_id[i] = cur_id
            run_len_at_row[i] = cur_len
        else:
            cur_id = next_id
            next_id += 1
            cur_len = 1
            prev_val = v
            run_id[i] = cur_id
            run_len_at_row[i] = cur_len

    # Final run lengths per run id.
    max_len: dict[int, int] = {}
    for i in range(n):
        if run_id[i] >= 0:
            max_len[run_id[i]] = max(max_len.get(run_id[i], 0), run_len_at_row[i])

    flags = [0] * n
    for i in range(n):
        if run_id[i] >= 0 and max_len[run_id[i]] >= threshold_rows:
            flags[i] = 1

    events: list[dict] = []
    for rid, total in sorted(max_len.items()):
        if total >= threshold_rows:
            members = [i for i in range(n) if run_id[i] == rid]
            events.append(
                {
                    "run_length": int(total),
                    "start_pos": int(members[0]),
                    "end_pos": int(members[-1]),
                }
            )
    return pd.Series(flags, index=values.index, dtype=int), events

"""Causal seasonal context: same-hour history as a readable reference.

For a decision timestamp, summarize what the station itself reported at
the same hour of day on strictly earlier days (median/MAD/day count).
Read-only and causal: only rows before the target timestamp enter, so a
probe or replay decision can never be informed by its own future. This
is a descriptive reference, not a detector and not a seasonal model —
the learned seasonal response remains the cyclical encodings plus the
trained detectors. Delhi pipeline history only.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

HOUR_WINDOW = 1  # same hour ±1h
MIN_DAYS = 3


def same_hour_context(obs: pd.DataFrame, target_ts: str,
                      column: str = "temperature_c") -> dict:
    """Same-hour historical reference for one variable (causal)."""
    base = {"available": False, "same_hour_median": None, "mad": None,
            "n_days": 0, "deviation": None,
            "note": "Seasonal reference unavailable for this timestamp."}
    try:
        target = pd.Timestamp(str(target_ts))
    except (TypeError, ValueError):
        return base
    frame = obs.copy()
    frame["_ts"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    past = frame[frame["_ts"] < target]
    if len(past) == 0:
        return base
    hour_match = (past["_ts"].dt.hour - target.hour).abs() <= HOUR_WINDOW
    day = past[hour_match]["_ts"].dt.date.nunique()
    vals = pd.to_numeric(past.loc[hour_match, column],
                         errors="coerce").dropna().to_numpy(dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0 or day < MIN_DAYS:
        base["n_days"] = int(day)
        return base
    median = float(np.median(vals))
    mad = float(np.median(np.abs(vals - median)))
    current = pd.to_numeric(
        frame.loc[frame["_ts"] == target, column],
        errors="coerce").dropna()
    deviation = (float(current.iloc[0]) - median
                 if len(current) else None)
    if deviation is not None and not math.isfinite(deviation):
        deviation = None
    return {"available": True, "same_hour_median": median,
            "mad": mad if math.isfinite(mad) else None,
            "n_days": int(day), "deviation": deviation,
            "note": (f"Same-hour (±{HOUR_WINDOW}h) station history over "
                     f"{int(day)} earlier days; descriptive reference only.")}

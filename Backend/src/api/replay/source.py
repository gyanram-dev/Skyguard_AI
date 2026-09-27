"""Replay source: real held-out benchmark observations, chronological.

Preferred demo source is the OOD split (test_generalization): held-out
observations beyond the training parameter range, exercising anomaly
generalization. The ID split (test_in_distribution) is also supported.

Frames are served as stored: chronological order preserved, nothing
shuffled, nothing interpolated, gaps untouched. Label columns travel
with the frame for test verification only and are never selected by
prepare_split (sensor values feed inference, exactly like offline eval).
"""

from __future__ import annotations

import pandas as pd

from src.features.feature_builder import CADENCE_HORIZONS

SPLITS = {
    "ID": "test_in_distribution",
    "OOD": "test_generalization",
}

DEFAULT_SPLIT = "OOD"
DEFAULT_STATION = "DEL-01"


def split_filename(split: str) -> str:
    """Benchmark CSV name for a split key (ID/OOD)."""
    key = str(split).upper()
    if key not in SPLITS:
        raise ValueError(f"Unknown split '{split}' (ID|OOD)")
    return f"{SPLITS[key]}.csv"


def load_source(store, ds: str, split: str) -> pd.DataFrame:
    """Benchmark frame for a pipeline dataset, chronology verified."""
    frame = pd.read_csv(store.root / "data" / "benchmark" / ds / split_filename(split))
    stamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    if bool(stamps.isna().any()):
        raise ValueError(f"{ds}/{split}: unparseable timestamps in replay source")
    if not bool(stamps.is_monotonic_increasing):
        raise ValueError(f"{ds}/{split}: replay source is not chronological")
    return frame.reset_index(drop=True)


def cadence_minutes(ds: str) -> int:
    """Native cadence for a pipeline dataset."""
    return int(CADENCE_HORIZONS[ds]["expected_interval_min"])

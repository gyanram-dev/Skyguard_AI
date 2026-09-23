"""Chronological 60/20/20 splitter with valid-observation boundaries."""

from __future__ import annotations

import pandas as pd

from src.benchmark.config import CORE_VARS, SPLIT_FRACTIONS


def compute_splits(df: pd.DataFrame) -> list[dict]:
    """Split the timeline chronologically; boundaries land on valid rows.

    Returns [{name, start_idx, end_idx_excl, start_timestamp, end_timestamp, rows}].
    Boundary rows are adjusted forward to the nearest row where all core
    variables are present (never into missing/outage data).
    """
    n = len(df)
    present = df[list(CORE_VARS)].notna().all(axis=1).to_numpy()
    names = ["train", "test_in_distribution", "test_generalization"]
    fracs = [SPLIT_FRACTIONS[k] for k in names]
    raw_bounds = [0, int(n * fracs[0]), int(n * (fracs[0] + fracs[1])), n]

    def _advance_to_valid(i: int) -> int:
        while i < n and not present[i]:
            i += 1
        return min(i, n - 1 if n else 0)

    bounds = [raw_bounds[0]] + [_advance_to_valid(b) for b in raw_bounds[1:-1]] + [raw_bounds[-1]]
    # Guard ordering after adjustment.
    for k in range(1, len(bounds) - 1):
        bounds[k] = max(bounds[k], bounds[k - 1] + 1)
        bounds[k] = min(bounds[k], n - 1)

    splits = []
    for j, name in enumerate(names):
        s, e = bounds[j], bounds[j + 1]
        splits.append({
            "name": name,
            "start_idx": int(s),
            "end_idx_excl": int(e),
            "start_timestamp": str(df["timestamp"].iloc[s]),
            "end_timestamp": str(df["timestamp"].iloc[e - 1]),
            "rows": int(e - s),
        })
    return splits

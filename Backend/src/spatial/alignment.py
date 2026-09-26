"""Temporal alignment without fabrication.

For a target timestamp, a neighbor observation qualifies only when a real
recorded observation exists within +/- TIME_TOLERANCE (nearest such record
wins). No interpolation, no forward/backward fill. A missing neighbor is
reported as unavailable through an honest availability mask.
"""

from __future__ import annotations

import pandas as pd

TIME_TOLERANCE = pd.Timedelta(minutes=30)


def align_neighbor(target_times: pd.Series, neighbor_times: pd.Series,
                   tolerance: pd.Timedelta = TIME_TOLERANCE) -> pd.Series:
    """Positional index of the nearest neighbor row within tolerance.

    Returns -1 where no qualifying observation exists. Both series must be
    timezone-aware UTC. Deterministic: merge_asof on sorted keys is a pure
    function of its inputs, so identical inputs always yield identical matches.
    """
    left = pd.DataFrame({"_t": pd.to_datetime(target_times, utc=True),
                         "_pos": range(len(target_times))}).sort_values("_t")
    right = pd.DataFrame({"_t": pd.to_datetime(neighbor_times, utc=True),
                          "_rpos": range(len(neighbor_times))}).sort_values("_t")
    matched = pd.merge_asof(left, right, on="_t", tolerance=tolerance,
                            direction="nearest")
    out = pd.Series(-1, index=range(len(target_times)), dtype=int)
    hit = matched.dropna(subset=["_rpos"])
    out[hit["_pos"].to_numpy(dtype=int)] = hit["_rpos"].to_numpy(dtype=int)
    return out

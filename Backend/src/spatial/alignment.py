"""Temporal alignment without fabrication.

For a target timestamp, a neighbor observation qualifies only when a real
recorded observation exists at or before the target within TIME_TOLERANCE
(nearest such record wins). A neighbor timestamp later than the target is
NEVER selected: online decisions must not depend on future observations.
No interpolation, no forward/backward fill. A missing neighbor is
reported as unavailable through an honest availability mask.

The tolerance window is therefore one-sided (target - tolerance, target].
No delayed-spatial policy exists anywhere; if one is ever required it
must be explicit and must expose its delay.
"""

from __future__ import annotations

import pandas as pd

TIME_TOLERANCE = pd.Timedelta(minutes=30)


def align_neighbor(target_times: pd.Series, neighbor_times: pd.Series,
                   tolerance: pd.Timedelta = TIME_TOLERANCE) -> pd.Series:
    """Positional index of the latest neighbor row at/before each target.

    Returns -1 where no qualifying observation exists. Both series must be
    timezone-aware UTC. Deterministic: merge_asof on sorted keys is a pure
    function of its inputs, so identical inputs always yield identical matches.
    Prefix-invariant: truncating neighbor history after a target's decision
    time cannot change that decision.
    """
    left = pd.DataFrame({"_t": pd.to_datetime(target_times, utc=True),
                         "_pos": range(len(target_times))}).sort_values("_t")
    right = pd.DataFrame({"_t": pd.to_datetime(neighbor_times, utc=True),
                          "_rpos": range(len(neighbor_times))}).sort_values("_t")
    out = pd.Series(-1, index=range(len(target_times)), dtype=int)
    if len(left) == 0 or len(right) == 0:
        return out
    try:
        matched = pd.merge_asof(left, right, on="_t", tolerance=tolerance,
                                direction="backward")
    except (ValueError, pd.errors.MergeError):
        # Incomparable resolutions/empties: no qualifying observation.
        return out
    hit = matched.dropna(subset=["_rpos"])
    out[hit["_pos"].to_numpy(dtype=int)] = hit["_rpos"].to_numpy(dtype=int)
    return out

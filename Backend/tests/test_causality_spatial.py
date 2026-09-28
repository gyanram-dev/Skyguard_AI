"""Phase 21B causality tests: spatial alignment never uses the future.

A neighbor observation qualifies only at or before the target timestamp
within tolerance. Truncating neighbor history after a decision time
cannot change that decision.
"""

from __future__ import annotations

import pandas as pd

from src.spatial.alignment import TIME_TOLERANCE, align_neighbor


def _ts(values):
    return pd.Series(pd.to_datetime(values))


# 1. Exact timestamp match.
def test_1_exact_match():
    tgt = _ts(["2022-06-01 12:00+00:00"])
    near = _ts(["2022-06-01 12:00+00:00"])
    assert int(align_neighbor(tgt, near).iloc[0]) == 0


# 2. Previous observation within tolerance wins.
def test_2_previous_observation():
    tgt = _ts(["2022-06-01 12:00+00:00"])
    near = _ts(["2022-06-01 11:50+00:00", "2022-06-01 10:00+00:00"])
    assert int(align_neighbor(tgt, near).iloc[0]) == 0


# 3. Future observation rejected even when it is the nearest record.
def test_3_future_rejected():
    tgt = _ts(["2022-06-01 12:00+00:00"])
    near = _ts(["2022-06-01 12:05+00:00"])
    assert int(align_neighbor(tgt, near).iloc[0]) == -1
    mixed = _ts(["2022-06-01 11:50+00:00", "2022-06-01 12:01+00:00"])
    assert int(align_neighbor(tgt, mixed).iloc[0]) == 0


# 4. No valid historical neighbor.
def test_4_no_history():
    tgt = _ts(["2022-06-01 12:00+00:00"])
    assert int(align_neighbor(tgt, _ts([])).iloc[0]) == -1
    assert int(align_neighbor(tgt, _ts(["2022-06-01 13:00+00:00"])).iloc[0]) == -1


# 5. Stale neighbor (outside tolerance) is unavailable.
def test_5_stale():
    tgt = _ts(["2022-06-01 12:00+00:00"])
    stale = _ts(["2022-06-01 11:00+00:00"])
    assert int(align_neighbor(tgt, stale).iloc[0]) == -1
    assert TIME_TOLERANCE == pd.Timedelta(minutes=30)


# 6. Multiple targets match their own latest qualifying neighbor.
def test_6_multiple():
    tgt = _ts(["2022-06-01 12:00+00:00", "2022-06-01 12:10+00:00"])
    near = _ts(["2022-06-01 11:55+00:00", "2022-06-01 12:05+00:00"])
    pos = align_neighbor(tgt, near)
    assert int(pos.iloc[0]) == 0
    assert int(pos.iloc[1]) == 1


# 7. Deterministic ordering: identical inputs, identical matches.
def test_7_deterministic():
    tgt = _ts(["2022-06-01 12:00+00:00", "2022-06-01 12:10+00:00"])
    near = _ts(["2022-06-01 12:10+00:00", "2022-06-01 11:55+00:00"])
    first = align_neighbor(tgt, near).tolist()
    second = align_neighbor(tgt, near).tolist()
    assert first == second == [1, 0]


# 8. Prefix invariance: later neighbor arrivals never rewrite matches.
def test_8_prefix_invariance():
    tgt = _ts(["2022-06-01 12:00+00:00", "2022-06-01 12:10+00:00"])
    early = _ts(["2022-06-01 11:55+00:00"])
    late = _ts(["2022-06-01 11:55+00:00", "2022-06-01 12:20+00:00"])
    assert align_neighbor(tgt, early).tolist() == align_neighbor(tgt, late).tolist()


# 9. Adding future neighbor data cannot change a previous decision.
def test_9_future_data_irrelevant():
    tgt = _ts(["2022-06-01 12:00+00:00"])
    before = int(align_neighbor(tgt, _ts(["2022-06-01 11:50+00:00"])).iloc[0])
    after = int(align_neighbor(
        tgt, _ts(["2022-06-01 11:50+00:00", "2022-06-01 12:30+00:00"])).iloc[0])
    assert (before, after) == (0, 0)

"""Phase 21B causality tests: freeze detection must be prefix-invariant.

An observation may only be marked frozen from evidence available at its
own time. Appending future rows extends flags forward and never rewrites
earlier decisions; batch and streaming paths share these semantics.
"""

from __future__ import annotations

import pandas as pd

from src.data_quality.batch_validator import validate_dataframe
from src.data_quality.freeze_checks import (
    detect_frozen_runs_with_threshold,
    freeze_threshold_rows,
)
from src.data_quality.quality_engine import StreamingQualityEngine


def _series(values, start="2024-01-01 00:00", step_min=10):
    base = pd.Timestamp(start)
    return pd.Series(values), pd.Series(
        [(base + pd.Timedelta(minutes=step_min * i)).strftime("%Y-%m-%d %H:%M:%S")
         for i in range(len(values))])


def _flags(values, threshold=6):
    series, _ = _series(values)
    flags, _ = detect_frozen_runs_with_threshold(
        series, pd.Series([False] * len(values)), threshold)
    return flags.tolist()


# 1. Prefix invariance: truncating the future never changes past flags.
def test_1_prefix_invariance():
    full = _flags([1.0] * 10 + [2.0] * 10, threshold=6)
    assert full == [0] * 5 + [1] * 5 + [0] * 5 + [1] * 5
    for cut in (6, 10, 12, 16):
        prefix = _flags(([1.0] * 10 + [2.0] * 10)[:cut], threshold=6)
        assert prefix == full[:cut]


# 2. Short frozen sequence: nothing flags, event never starts early.
def test_2_short_sequence():
    assert _flags([7.0] * 5, threshold=6) == [0] * 5


# 3. Threshold-length run: only the final row flags at the boundary.
def test_3_threshold_boundary():
    assert _flags([7.0] * 6, threshold=6) == [0] * 5 + [1]


# 4. Long run: detection starts exactly at threshold, start preserved.
def test_4_long_run_detection_pos():
    series, _ = _series([7.0] * 10)
    flags, events = detect_frozen_runs_with_threshold(
        series, pd.Series([False] * 10), 6)
    assert flags.tolist() == [0] * 5 + [1] * 5
    assert len(events) == 1
    assert events[0]["start_pos"] == 0
    assert events[0]["detection_pos"] == 5
    assert events[0]["end_pos"] == 9


# 5. Future rows appended do not change earlier decisions.
def test_5_future_rows_stable():
    before = _flags([3.0] * 8, threshold=6)
    after = _flags([3.0] * 8 + [3.0] * 4, threshold=6)
    assert after[:8] == before
    assert before == [0] * 5 + [1] * 3
    assert after == [0] * 5 + [1] * 7


# 6. Replay and batch use the same causal semantics as streaming.
def test_6_batch_matches_streaming():
    values = [9.0] * 40
    batch = _flags(values, threshold=36)
    engine = StreamingQualityEngine("jena")
    assert freeze_threshold_rows("jena") == 36
    stream = []
    ts = pd.Timestamp("2024-01-01 00:00")
    for i, value in enumerate(values):
        stamp = (ts + pd.Timedelta(minutes=10 * i)).strftime("%Y-%m-%d %H:%M:%S")
        out = engine.check({"timestamp": stamp, "temperature_c": value,
                            "pressure_hpa": 1000.0 + i * 0.01,
                            "relative_humidity_pct": 50.0})
        stream.append(out["temperature_possible_freeze"])
    assert batch == stream == [0] * 35 + [1] * 5


def _clean_frame(rows, dataset):
    frame = pd.DataFrame(rows)
    frame["source_dataset"] = dataset
    if dataset == "delhi":
        for col in ("temperature_missing", "humidity_missing", "pressure_missing",
                    "any_core_missing", "missing_core_count"):
            frame[col] = 0
    return frame


# Batch parity: a 40-row identical run flags only its causal tail.
def test_7_batch_causal_tail():
    base = pd.Timestamp("2024-01-01 00:00")
    rows = [{"timestamp": (base + pd.Timedelta(minutes=10 * i)).strftime("%Y-%m-%d %H:%M:%S"),
             "temperature_c": 20.0, "pressure_hpa": 1000.0 + i * 0.01,
             "relative_humidity_pct": 50.0} for i in range(40)]
    qdf, _ = validate_dataframe(_clean_frame(rows, "jena"), "jena")
    assert qdf["temperature_possible_freeze"].tolist() == [0] * 35 + [1] * 5
    assert qdf.iloc[-1]["quality_status"] == "POSSIBLE_FREEZE"
    assert int(qdf.iloc[-1]["ml_eligible"]) == 1

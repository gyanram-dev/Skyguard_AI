"""Phase 2.5 Data Quality Layer tests.

Tiny in-memory fixtures ONLY. Nothing here touches production datasets
or claims ground truth about real observations.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data_quality.batch_validator import QUALITY_COLUMNS, validate_dataframe
from src.data_quality.freeze_checks import freeze_threshold_rows
from src.data_quality.quality_engine import (
    COMMUNICATION_GAP,
    DATA_AVAILABILITY_EVENT,
    DATA_INTEGRITY_FAULT,
    PASS,
    PHYSICAL_SANITY_FAULT,
    POSSIBLE_FREEZE,
    StreamingQualityEngine,
    classify_quality_status,
)
from src.data_quality.timeline_checks import gap_threshold_minutes


# ==============================================================================
# Fixture builders (A-K)
# ==============================================================================

def _reading(ts: str, t: float | None = 25.0, p: float | None = 1000.0,
             rh: float | None = 50.0) -> dict:
    return {"timestamp": ts, "temperature_c": t, "pressure_hpa": p,
            "relative_humidity_pct": rh}


def _seq(start: str, periods: int, freq_min: int, **overrides) -> list[dict]:
    base = pd.Timestamp(start)
    return [_reading((base + pd.Timedelta(minutes=i * freq_min)).strftime("%Y-%m-%d %H:%M:%S"),
                     **overrides) for i in range(periods)]


def _run_engine(dataset: str, readings: list[dict]) -> list[dict]:
    engine = StreamingQualityEngine(dataset)
    return [engine.check(r) for r in readings]


def _clean_frame(rows: list[dict], dataset: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["source_dataset"] = dataset
    return df[["timestamp", "temperature_c", "pressure_hpa",
               "relative_humidity_pct", "source_dataset"]]


# A. normal cadence
def fixture_normal_jenna() -> list[dict]:
    return _seq("2024-01-01 00:00", 5, 10)


def fixture_normal_delhi() -> list[dict]:
    return _seq("2024-01-01 00:00", 5, 5)


# ==============================================================================
# 1-4. Timestamp integrity
# ==============================================================================

def test_1_valid_timestamp_passes():
    res = _run_engine("delhi", fixture_normal_delhi())
    assert res[-1]["timestamp_valid"] == 1
    assert res[-1]["quality_status"] == PASS


def test_2_invalid_timestamp_detected():
    res = _run_engine("delhi", [_reading("not-a-date")])
    assert res[0]["timestamp_valid"] == 0
    assert res[0]["quality_status"] == DATA_INTEGRITY_FAULT
    assert res[0]["ml_eligible"] == 0


def test_3_duplicate_timestamp_detected():
    readings = [_reading("2024-01-01 00:00"), _reading("2024-01-01 00:05"),
                _reading("2024-01-01 00:05")]
    res = _run_engine("delhi", readings)
    assert res[1]["timestamp_duplicate"] == 0
    assert res[2]["timestamp_duplicate"] == 1
    assert res[2]["quality_status"] == DATA_INTEGRITY_FAULT
    assert res[2]["ml_eligible"] == 0


def test_4_out_of_order_timestamp_detected():
    readings = [_reading("2024-01-01 00:00"), _reading("2024-01-01 00:05"),
                _reading("2024-01-01 00:02")]
    res = _run_engine("delhi", readings)
    assert res[2]["timestamp_out_of_order"] == 1
    assert res[2]["quality_status"] == DATA_INTEGRITY_FAULT
    assert res[2]["ml_eligible"] == 0


# ==============================================================================
# 5-8. Cadence / gaps
# ==============================================================================

def test_5_normal_jena_cadence_not_flagged():
    res = _run_engine("jena", fixture_normal_jenna())
    assert all(r["communication_gap"] == 0 for r in res)
    assert res[-1]["quality_status"] == PASS


def test_6_normal_delhi_cadence_not_flagged():
    res = _run_engine("delhi", fixture_normal_delhi())
    assert all(r["communication_gap"] == 0 for r in res)
    assert res[-1]["quality_status"] == PASS


def test_7_jenna_gap_over_15min_detected():
    assert gap_threshold_minutes("jena") == 15.0
    readings = [_reading("2024-01-01 00:00"), _reading("2024-01-01 00:30")]
    res = _run_engine("jena", readings)
    assert res[1]["communication_gap"] == 1
    assert res[1]["gap_duration_minutes"] == pytest.approx(30.0)
    assert res[1]["quality_status"] == COMMUNICATION_GAP


def test_8_delhi_gap_over_7p5min_detected():
    assert gap_threshold_minutes("delhi") == 7.5
    readings = [_reading("2024-01-01 00:00"), _reading("2024-01-01 00:15")]
    res = _run_engine("delhi", readings)
    assert res[1]["communication_gap"] == 1
    assert res[1]["quality_status"] == COMMUNICATION_GAP


# ==============================================================================
# 9-10. Missing data
# ==============================================================================

def test_9_missing_temperature_is_availability_event():
    readings = [_reading("2024-01-01 00:00", t=None)]
    res = _run_engine("delhi", readings)
    assert res[0]["temperature_missing"] == 1
    assert res[0]["any_core_missing"] == 1
    assert res[0]["missing_core_count"] == 1
    assert res[0]["quality_status"] == DATA_AVAILABILITY_EVENT
    assert res[0]["ml_eligible"] == 0


def test_10_all_three_missing_is_availability_event():
    readings = [_reading("2024-01-01 00:00", t=None, p=None, rh=None)]
    res = _run_engine("delhi", readings)
    assert res[0]["missing_core_count"] == 3
    assert res[0]["quality_status"] == DATA_AVAILABILITY_EVENT
    assert res[0]["ml_eligible"] == 0


# ==============================================================================
# 11-14. Physical sanity
# ==============================================================================

def test_11_rh_above_100_is_sanity_fault():
    res = _run_engine("delhi", [_reading("2024-01-01 00:00", rh=105.0)])
    assert res[0]["physical_sanity_fault"] == 1
    assert res[0]["quality_status"] == PHYSICAL_SANITY_FAULT
    assert res[0]["ml_eligible"] == 0


def test_12_rh_below_0_is_sanity_fault():
    res = _run_engine("delhi", [_reading("2024-01-01 00:00", rh=-2.0)])
    assert res[0]["physical_sanity_fault"] == 1
    assert res[0]["quality_status"] == PHYSICAL_SANITY_FAULT


def test_13_temperature_55c_not_rejected():
    res = _run_engine("delhi", _seq("2024-01-01 00:00", 3, 5, t=55.0))
    # 55 C repeated 3x is not a freeze and not a sanity fault.
    assert res[-1]["physical_sanity_fault"] == 0
    assert res[-1]["quality_status"] == PASS
    assert res[-1]["ml_eligible"] == 1


def test_14_unusual_delhi_pressure_not_rejected():
    for unusual in (860.0, 1086.0):
        res = _run_engine("delhi", [_reading("2024-01-01 00:00", p=unusual)])
        assert res[0]["physical_sanity_fault"] == 0
        assert res[0]["quality_status"] == PASS
        assert res[0]["ml_eligible"] == 1


# ==============================================================================
# 15-18. Freeze checks
# ==============================================================================

def test_15_short_repeats_do_not_trigger_freeze():
    readings = _seq("2024-01-01 00:00", 5, 10)  # identical values, only 5 rows
    res = _run_engine("jena", readings)
    assert all(r["temperature_possible_freeze"] == 0 for r in res)
    assert res[-1]["quality_status"] == PASS


def test_16_36_identical_jena_values_trigger_possible_freeze():
    # Phase 21B: causal flags — a 40-row run with threshold 36 flags only
    # rows 36..40 (previously the whole run was marked using future rows).
    assert freeze_threshold_rows("jena") == 36
    rows = []
    base = pd.Timestamp("2024-01-01 00:00")
    for i in range(40):
        ts = (base + pd.Timedelta(minutes=10 * i)).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": ts, "temperature_c": 20.0,
                     "pressure_hpa": 1000.0 + i * 0.01,
                     "relative_humidity_pct": 50.0 + (i % 3) * 0.1})
    qdf, _ = validate_dataframe(_clean_frame(rows, "jena"), "jena")
    assert int(qdf["temperature_possible_freeze"].sum()) == 5
    assert int(qdf["pressure_possible_freeze"].sum()) == 0
    last = qdf.iloc[-1]
    assert last["quality_status"] == POSSIBLE_FREEZE
    assert int(last["ml_eligible"]) == 1


def test_17_72_identical_delhi_values_trigger_possible_freeze():
    # Phase 21B causal flags: an 80-row run with threshold 72 flags rows 72..80.
    assert freeze_threshold_rows("delhi") == 72
    rows = []
    base = pd.Timestamp("2024-01-01 00:00")
    for i in range(80):
        ts = (base + pd.Timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": ts, "temperature_c": 25.0 + (i % 2) * 0.1,
                     "pressure_hpa": 990.0,
                     "relative_humidity_pct": 60.0 + (i % 5) * 0.1})
    qdf, _ = validate_dataframe(_clean_frame(rows, "delhi"), "delhi")
    assert int(qdf["pressure_possible_freeze"].sum()) == 9
    last = qdf.iloc[-1]
    assert last["quality_status"] == POSSIBLE_FREEZE
    assert int(last["ml_eligible"]) == 1


def test_17b_nan_separates_freeze_runs_without_id_collision():
    """40 identical + NaN + 5 identical (threshold 36): causal flags mark
    rows 36..40 of the first run only (previously all 40 rows)."""
    import numpy as np

    base = pd.Timestamp("2024-01-01 00:00")
    temps = [20.0] * 40 + [np.nan] * 2 + [20.0] * 5
    rows = []
    for i, t in enumerate(temps):
        ts = (base + pd.Timedelta(minutes=10 * i)).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"timestamp": ts, "temperature_c": t,
                     "pressure_hpa": 1000.0 + i * 0.01,
                     "relative_humidity_pct": 50.0 + (i % 3) * 0.1})
    qdf, summary = validate_dataframe(_clean_frame(rows, "jena"), "jena")
    assert int(qdf["temperature_possible_freeze"].sum()) == 5
    assert int(qdf.iloc[-1]["temperature_possible_freeze"]) == 0
    # Availability rows for the NaN pair take priority over nothing else.
    assert int((qdf["quality_status"] == DATA_AVAILABILITY_EVENT).sum()) == 2
    assert len(summary["freeze_events"]["temperature"]) == 1


def test_18_possible_freeze_remains_ml_eligible():
    status, eligible = classify_quality_status(False, False, False, False, True)
    assert status == POSSIBLE_FREEZE
    assert eligible is True


# ==============================================================================
# 19-21. ML eligibility + priority
# ==============================================================================

def test_19_communication_gap_not_ml_eligible():
    status, eligible = classify_quality_status(False, True, False, False, False)
    assert status == COMMUNICATION_GAP
    assert eligible is False


def test_20_physical_sanity_fault_not_ml_eligible():
    status, eligible = classify_quality_status(False, False, False, True, False)
    assert status == PHYSICAL_SANITY_FAULT
    assert eligible is False


def test_21_status_priority_deterministic():
    # Integrity beats everything.
    assert classify_quality_status(True, True, True, True, True)[0] == DATA_INTEGRITY_FAULT
    # Gap beats availability/sanity/freeze.
    assert classify_quality_status(False, True, True, True, True)[0] == COMMUNICATION_GAP
    # Availability beats sanity/freeze.
    assert classify_quality_status(False, False, True, True, True)[0] == DATA_AVAILABILITY_EVENT
    # Sanity beats freeze.
    assert classify_quality_status(False, False, False, True, True)[0] == PHYSICAL_SANITY_FAULT
    # Freeze beats pass.
    assert classify_quality_status(False, False, False, False, True)[0] == POSSIBLE_FREEZE
    assert classify_quality_status(False, False, False, False, False)[0] == PASS
    # Engine-level: missing + bad RH -> availability (priority 3 over 4).
    res = _run_engine("delhi", [_reading("2024-01-01 00:00", t=None, rh=150.0)])
    assert res[0]["quality_status"] == DATA_AVAILABILITY_EVENT


# ==============================================================================
# 22-24. Determinism + protection of previous phases
# ==============================================================================

def test_22_quality_output_deterministic():
    rows = _clean_frame(fixture_normal_delhi(), "delhi")
    q1, _ = validate_dataframe(rows, "delhi")
    q2, _ = validate_dataframe(rows, "delhi")
    pd.testing.assert_frame_equal(q1, q2)
    seq = fixture_normal_jenna()
    assert _run_engine("jena", seq) == _run_engine("jena", seq)


def test_23_previous_project_datasets_unchanged():
    root = Path(".").resolve()
    jena_clean = pd.read_csv(root / "data" / "processed" / "jena_clean.csv", nrows=5)
    assert len(pd.read_csv(root / "data" / "processed" / "jena_clean.csv", usecols=["timestamp"])) == 420224
    assert len(pd.read_csv(root / "data" / "processed" / "delhi_clean.csv", usecols=["timestamp"])) == 289728
    assert len(pd.read_csv(root / "data" / "features" / "jena_features.csv", nrows=0).columns) == 106
    assert len(pd.read_csv(root / "data" / "features" / "delhi_features.csv", nrows=0).columns) == 106
    assert list(jena_clean.columns) == ["timestamp", "temperature_c", "pressure_hpa",
                                        "relative_humidity_pct", "source_dataset"]


def test_24_phase3_feature_code_still_works():
    from src.features.feature_builder import build_features_for_dataset

    root = Path(".").resolve()
    sample = pd.read_csv(root / "data" / "processed" / "jena_clean.csv", nrows=200)
    feat = build_features_for_dataset(sample, "jena")
    assert len(feat) == len(sample)
    assert len(feat.columns) == 106

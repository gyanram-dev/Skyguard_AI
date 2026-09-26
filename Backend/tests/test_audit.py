"""Unit test suite for Phase 1 AWS Data Audit Pipeline.

Covers:
1. Timestamp parsing.
2. Duplicate timestamp detection.
3. Exact duplicate row detection.
4. Missing-value counting.
5. Missing-run detection.
6. Timestamp-gap detection.
7. Out-of-order detection.
8. Raw-file integrity / hash verification.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.audit import (
    audit_duplicates,
    audit_general_value_quality,
    audit_missing_data,
    audit_out_of_order,
    audit_sampling_intervals,
    audit_timestamp_gaps,
    calculate_missing_runs_for_series,
    compute_sha256,
    verify_file_integrity,
)


@pytest.fixture
def sample_timestamps() -> pd.Series:
    """Fixture providing clean 5-minute interval timestamps."""
    dates = pd.date_range("2024-01-01 00:00", periods=10, freq="5min")
    return pd.Series(dates)


def test_compute_sha256_and_verify_file_integrity():
    """Test SHA-256 calculation and file integrity verification."""
    with tempfile.NamedTemporaryFile("w+", delete=False) as tmp:
        tmp.write("Date,Temp,Pres\n2024-01-01,25.0,1013.25\n")
        tmp_path = Path(tmp.name)

    try:
        hash_1 = compute_sha256(tmp_path)
        assert len(hash_1) == 64
        # Verify idempotence
        hash_2 = compute_sha256(tmp_path)
        assert hash_1 == hash_2

        integrity = verify_file_integrity(tmp_path, expected_hash=hash_1)
        assert integrity["exists"] is True
        assert integrity["hash_matches"] is True
        assert integrity["size_bytes"] > 0

        # Wrong hash check
        bad_integrity = verify_file_integrity(tmp_path, expected_hash="0000000000000000000000000000000000000000000000000000000000000000")
        assert bad_integrity["hash_matches"] is False
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_sampling_interval_detection(sample_timestamps):
    """Test standard cadence and unexpected intervals calculation."""
    res = audit_sampling_intervals(sample_timestamps, expected_interval_minutes=5)
    assert res["expected_interval_minutes"] == 5
    assert res["total_intervals"] == 9
    assert "0 days 00:05:00" in res["most_common_interval"]
    assert res["unexpected_intervals_count"] == 0

    # Inject an unexpected 15 min jump
    ts_with_gap = pd.concat([
        sample_timestamps.iloc[:5],
        pd.Series([pd.Timestamp("2024-01-01 00:35:00")]),  # Jump of 15 min from 00:20
    ]).reset_index(drop=True)
    res_gap = audit_sampling_intervals(ts_with_gap, expected_interval_minutes=5)
    assert res_gap["unexpected_intervals_count"] == 1


def test_duplicate_detection():
    """Test exact row duplicate detection and duplicate timestamp classification."""
    data = {
        "Date": ["2024-01-01 00:00", "2024-01-01 00:05", "2024-01-01 00:05", "2024-01-01 00:10", "2024-01-01 00:10"],
        "Temp": [20.0, 21.0, 21.0, 22.0, 25.0],  # 00:05 is exact duplicate; 00:10 has different values
        "Pres": [1000.0, 1001.0, 1001.0, 1002.0, 1002.0],
    }
    df = pd.DataFrame(data)
    summary, dup_df = audit_duplicates(df, date_col="Date")

    assert summary["completely_duplicated_rows_total"] == 2  # rows 1 and 2
    assert summary["unique_exact_duplicate_rows"] == 1
    assert summary["unique_duplicate_timestamps"] == 2  # 00:05 and 00:10
    assert summary["duplicate_timestamps_total_rows"] == 4

    # 00:05 should be identical, 00:10 should differ
    row_05 = dup_df[dup_df["duplicate_timestamp"] == "2024-01-01 00:05"].iloc[0]
    row_10 = dup_df[dup_df["duplicate_timestamp"] == "2024-01-01 00:10"].iloc[0]

    assert bool(row_05["identical_values"]) is True
    assert bool(row_05["values_differ"]) is False

    assert bool(row_10["identical_values"]) is False
    assert bool(row_10["values_differ"]) is True


def test_out_of_order_detection():
    """Test identification of negative timestamp transitions."""
    ts_list = [
        pd.Timestamp("2024-01-01 00:00"),
        pd.Timestamp("2024-01-01 00:10"),
        pd.Timestamp("2024-01-01 00:05"),  # Out of order!
        pd.Timestamp("2024-01-01 00:15"),
    ]
    df = pd.DataFrame({"Date": [str(t) for t in ts_list]})
    dt_series = pd.Series(ts_list)

    summary, ooo_df = audit_out_of_order(df, dt_series, date_col="Date")
    assert summary["out_of_order_transitions_count"] == 1
    assert summary["out_of_order_indices"] == [2]
    assert len(ooo_df) == 1
    assert ooo_df.iloc[0]["row_index"] == 2
    assert ooo_df.iloc[0]["previous_timestamp"] == "2024-01-01 00:10:00"
    assert ooo_df.iloc[0]["current_timestamp"] == "2024-01-01 00:05:00"


def test_timestamp_gaps():
    """Test calculation of timestamp gaps greater than expected cadence."""
    ts_list = [
        pd.Timestamp("2024-01-01 00:00"),
        pd.Timestamp("2024-01-01 00:10"),
        pd.Timestamp("2024-01-01 00:40"),  # 30-min gap (2 missing 10-min intervals)
        pd.Timestamp("2024-01-01 00:50"),
    ]
    dt_series = pd.Series(ts_list)
    summary, gap_df = audit_timestamp_gaps(dt_series, expected_interval_minutes=10)

    assert summary["total_gaps"] == 1
    assert summary["total_missing_gap_observations"] == 2
    assert len(gap_df) == 1
    assert gap_df.iloc[0]["start_timestamp"] == "2024-01-01 00:10:00"
    assert gap_df.iloc[0]["end_timestamp"] == "2024-01-01 00:40:00"
    assert gap_df.iloc[0]["missing_observations_count"] == 2


def test_missing_data_and_run_detection():
    """Test per-column missing counts, joint missingness, and run-length encoding."""
    dates = pd.date_range("2024-01-01 00:00", periods=6, freq="10min")
    dt_series = pd.Series(dates)
    data = {
        "Date": dates,
        "Temp": [20.0, np.nan, np.nan, 23.0, np.nan, 25.0],  # runs: length 2, length 1
        "Pres": [1000.0, np.nan, np.nan, 1002.0, 1003.0, 1004.0],  # run: length 2
        "RH": [50.0, np.nan, np.nan, 52.0, 53.0, 54.0],  # run: length 2
    }
    df = pd.DataFrame(data)

    summary, runs_df = audit_missing_data(df, core_cols=["Temp", "Pres", "RH"], dt_series=dt_series)

    # Per column check
    assert summary["per_column_missingness"]["Temp"]["missing_count"] == 3
    assert summary["per_column_missingness"]["Pres"]["missing_count"] == 2

    # Joint missingness
    # Rows 1 and 2: all 3 missing (count=2)
    # Row 4: only Temp is missing (count=1)
    # Rows 0, 3, 5: 0 missing (count=3)
    assert summary["joint_core_missingness"]["all_three_missing"] == 2
    assert summary["joint_core_missingness"]["exactly_one_missing"] == 1
    assert summary["joint_core_missingness"]["exactly_two_missing"] == 0
    assert summary["joint_core_missingness"]["zero_missing"] == 3

    # Temp runs check
    temp_run_sum = summary["missing_runs_summary"]["Temp"]
    assert temp_run_sum["number_of_missing_runs"] == 2
    assert temp_run_sum["shortest_missing_run"] == 1
    assert temp_run_sum["longest_missing_run"] == 2
    assert temp_run_sum["longest_run_start"] == "2024-01-01 00:10:00"
    assert temp_run_sum["longest_run_end"] == "2024-01-01 00:20:00"


def test_general_value_quality():
    """Test detection of inf, -inf, and corrupted strings."""
    data = {
        "T": [20.0, np.inf, 22.0, -np.inf, 24.0],
        "P": [1000.0, 1001.0, "bad_val", 1003.0, 1004.0],
    }
    df = pd.DataFrame(data)
    quality = audit_general_value_quality(df, core_cols=["T", "P"])

    assert quality["T"]["positive_infinity_count"] == 1
    assert quality["T"]["negative_infinity_count"] == 1
    assert quality["T"]["has_value_corruption"] is True

    assert quality["P"]["unparseable_non_numeric_count"] == 1
    assert quality["P"]["has_value_corruption"] is True

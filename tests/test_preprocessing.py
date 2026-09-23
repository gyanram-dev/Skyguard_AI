"""Comprehensive unit and integration test suite for Phase 2 data preprocessing.

Validates all 11 Jena checks, 14 Delhi checks, and Global invariant guarantees.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.preprocessing.preprocess_delhi import preprocess_delhi
from src.preprocessing.preprocess_jena import preprocess_jena
from src.preprocessing.run import compute_sha256, find_raw_file
from src.preprocessing.validation import (
    validate_delhi_preprocessing,
    validate_global_invariants,
    validate_jena_preprocessing,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


@pytest.fixture(scope="module")
def raw_jena_df(project_root) -> pd.DataFrame:
    raw_file = find_raw_file("jena_climate_2009_2016.csv", [project_root, project_root / "data" / "raw"])
    return pd.read_csv(raw_file)


@pytest.fixture(scope="module")
def raw_delhi_df(project_root) -> pd.DataFrame:
    raw_file = find_raw_file("AWS_20220401_20241231.csv", [project_root, project_root / "data" / "raw"])
    return pd.read_csv(raw_file)


@pytest.fixture(scope="module")
def processed_jena(raw_jena_df):
    clean_df, report = preprocess_jena(raw_jena_df)
    return clean_df, report


@pytest.fixture(scope="module")
def processed_delhi(raw_delhi_df):
    clean_df, report = preprocess_delhi(raw_delhi_df)
    return clean_df, report


# ==============================================================================
# JENA VALIDATION TESTS
# ==============================================================================

def test_jena_row_counts_and_duplicates(raw_jena_df, processed_jena):
    clean_df, report = processed_jena
    assert len(raw_jena_df) == 420551
    assert len(clean_df) == 420224
    assert report["duplicates_removed"] == 327
    assert len(raw_jena_df) - len(clean_df) == 327


def test_jena_timestamps_unique_and_sorted(processed_jena):
    clean_df, report = processed_jena
    dt_series = pd.to_datetime(clean_df["timestamp"], format="%Y-%m-%d %H:%M:%S")
    assert dt_series.is_unique
    assert dt_series.is_monotonic_increasing


def test_jena_genuine_gaps_preserved(processed_jena):
    clean_df, report = processed_jena
    dt_series = pd.to_datetime(clean_df["timestamp"], format="%Y-%m-%d %H:%M:%S")
    diffs = dt_series.diff()
    gaps_gt_10min = (diffs > pd.Timedelta(minutes=10)).sum()
    assert gaps_gt_10min == 5
    assert diffs.max() == pd.Timedelta(days=3, hours=2, minutes=20)


def test_jena_no_artificial_missing_values(processed_jena):
    clean_df, report = processed_jena
    core_cols = ["temperature_c", "pressure_hpa", "relative_humidity_pct"]
    assert clean_df[core_cols].isna().sum().sum() == 0


def test_jena_values_not_clipped(raw_jena_df, processed_jena):
    clean_df, report = processed_jena
    assert np.isclose(clean_df["temperature_c"].min(), raw_jena_df["T (degC)"].min())
    assert np.isclose(clean_df["temperature_c"].max(), raw_jena_df["T (degC)"].max())
    assert np.isclose(clean_df["pressure_hpa"].min(), raw_jena_df["p (mbar)"].min())
    assert np.isclose(clean_df["pressure_hpa"].max(), raw_jena_df["p (mbar)"].max())
    assert np.isclose(clean_df["relative_humidity_pct"].min(), raw_jena_df["rh (%)"].min())
    assert np.isclose(clean_df["relative_humidity_pct"].max(), raw_jena_df["rh (%)"].max())


def test_jena_comprehensive_validation_function(raw_jena_df, processed_jena):
    clean_df, report = processed_jena
    val_res = validate_jena_preprocessing(raw_jena_df, clean_df)
    assert val_res["all_passed"] is True
    assert all(val_res["checks"].values())


# ==============================================================================
# DELHI VALIDATION TESTS
# ==============================================================================

def test_delhi_row_count_preserved(raw_delhi_df, processed_delhi):
    clean_df, report = processed_delhi
    assert len(raw_delhi_df) == 289728
    assert len(clean_df) == 289728


def test_delhi_timestamps_cadence(processed_delhi):
    clean_df, report = processed_delhi
    dt_series = pd.to_datetime(clean_df["timestamp"], format="%Y-%m-%d %H:%M:%S")
    assert dt_series.is_unique
    assert dt_series.is_monotonic_increasing
    diffs = dt_series.diff().dropna()
    assert (diffs == pd.Timedelta(minutes=5)).all()


def test_delhi_missing_counts_and_quality_flags(raw_delhi_df, processed_delhi):
    clean_df, report = processed_delhi
    assert clean_df["temperature_c"].isna().sum() == 807
    assert clean_df["relative_humidity_pct"].isna().sum() == 807
    assert clean_df["pressure_hpa"].isna().sum() == 811

    # Quality flags correctness
    assert (clean_df["temperature_missing"] == clean_df["temperature_c"].isna().astype(int)).all()
    assert (clean_df["humidity_missing"] == clean_df["relative_humidity_pct"].isna().astype(int)).all()
    assert (clean_df["pressure_missing"] == clean_df["pressure_hpa"].isna().astype(int)).all()

    # Any missing flag
    expected_any = (
        (clean_df["temperature_missing"] == 1)
        | (clean_df["humidity_missing"] == 1)
        | (clean_df["pressure_missing"] == 1)
    ).astype(int)
    assert (clean_df["any_core_missing"] == expected_any).all()
    assert clean_df["any_core_missing"].sum() == 813

    # Missing core count
    expected_count = clean_df["temperature_missing"] + clean_df["humidity_missing"] + clean_df["pressure_missing"]
    assert (clean_df["missing_core_count"] == expected_count).all()


def test_delhi_42h_outage_preserved(processed_delhi):
    clean_df, report = processed_delhi
    outage_mask = (clean_df["timestamp"] >= "2022-04-05 17:45:00") & (clean_df["timestamp"] <= "2022-04-07 11:40:00")
    outage_sub = clean_df.loc[outage_mask, ["temperature_c", "pressure_hpa", "relative_humidity_pct"]]
    assert len(outage_sub) == 504
    assert outage_sub.isna().all().all()


def test_delhi_candidate_anomalies_preserved(raw_delhi_df, processed_delhi):
    clean_df, report = processed_delhi
    # 4 sub-zero temperatures
    neg_sub = clean_df[clean_df["temperature_c"] < 0]
    assert len(neg_sub) == 4
    assert list(neg_sub.index) == [1162, 1171, 1173, 1262]
    assert np.isclose(neg_sub.loc[1162, "temperature_c"], -37.88226)

    # Pressure values untouched
    clean_p_valid = clean_df["pressure_hpa"].dropna()
    raw_p_valid = pd.to_numeric(raw_delhi_df["Atm_Pres"], errors="coerce").dropna()
    assert np.allclose(clean_p_valid, raw_p_valid)
    assert (clean_df["pressure_hpa"] < 950).sum() == 170313
    assert (clean_df["pressure_hpa"] > 1030).sum() == 1284


def test_delhi_comprehensive_validation_function(raw_delhi_df, processed_delhi):
    clean_df, report = processed_delhi
    val_res = validate_delhi_preprocessing(raw_delhi_df, clean_df)
    assert val_res["all_passed"] is True
    assert all(val_res["checks"].values())


# ==============================================================================
# GLOBAL INVARIANTS TEST
# ==============================================================================

def test_raw_files_immutability(project_root):
    candidate_dirs = [project_root, project_root / "data" / "raw"]
    jena_raw = find_raw_file("jena_climate_2009_2016.csv", candidate_dirs)
    delhi_raw = find_raw_file("AWS_20220401_20241231.csv", candidate_dirs)

    expected_jena = "9626d3964f7afb3fa94b6f3d3a0e92fe96e4a4477c31ed9875cc64d6717c129f"
    expected_delhi = "f22119b81268cd010366a868c021fadb70487e766bff86a43434021d320d864e"

    assert compute_sha256(jena_raw) == expected_jena
    assert compute_sha256(delhi_raw) == expected_delhi

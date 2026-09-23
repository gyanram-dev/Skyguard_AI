"""Phase 4 Traditional Statistical QC Baseline tests.

No ground-truth anomaly labels exist, so no accuracy/precision/recall
is asserted anywhere. Tests cover causality, determinism, schema,
data-quality integration, segment safety, and the absence of hard
physical thresholds (950/1030 hPa, 55 C).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.baseline.iqr_baseline import IQR_FACTOR, causal_rolling_quartiles, compute_iqr_flags
from src.baseline.statistical_baseline import (
    BASELINE_COLUMNS,
    baseline_window_rows,
    build_statistical_baseline,
)
from src.baseline.zscore_baseline import (
    Z_THRESHOLD,
    compute_zscore_flags,
    compute_zscores,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


@pytest.fixture(scope="module")
def jena_sample(project_root) -> tuple[pd.DataFrame, pd.DataFrame]:
    feat = pd.read_csv(project_root / "data" / "features" / "jena_features.csv", nrows=200)
    qual = pd.read_csv(project_root / "data" / "quality" / "jena_quality.csv", nrows=200)
    return feat, qual


@pytest.fixture(scope="module")
def delhi_sample(project_root) -> tuple[pd.DataFrame, pd.DataFrame]:
    feat = pd.read_csv(project_root / "data" / "features" / "delhi_features.csv", nrows=300)
    qual = pd.read_csv(project_root / "data" / "quality" / "delhi_quality.csv", nrows=300)
    return feat, qual


def _pass_quality(n: int) -> pd.DataFrame:
    return pd.DataFrame({"ml_eligible": [1] * n, "quality_status": ["PASS"] * n})


# ==============================================================================
# Windows / configuration
# ==============================================================================

def test_window_rows_match_cadence():
    assert baseline_window_rows("jena") == 12
    assert baseline_window_rows("delhi") == 24
    assert Z_THRESHOLD == 3.0
    assert IQR_FACTOR == 1.5


# ==============================================================================
# Z-score correctness
# ==============================================================================

def test_zscore_matches_phase3_rolling_stats(jena_sample):
    feat, _ = jena_sample
    z = compute_zscores(feat)
    row = feat["temperature_prev_mean_2h"].notna() & feat["temperature_prev_std_2h"].notna()
    idx = feat.index[row][0]
    expected = ((feat.loc[idx, "temperature_c"] - feat.loc[idx, "temperature_prev_mean_2h"])
                / feat.loc[idx, "temperature_prev_std_2h"])
    assert np.isclose(z.loc[idx, "temperature_zscore_baseline"], expected)


def test_zscore_nan_without_history_or_variance(jena_sample):
    feat, _ = jena_sample
    z = compute_zscores(feat)
    # First rows lack 2h history -> NaN.
    assert z["temperature_zscore_baseline"].iloc[:12].isna().all()
    # Zero-variance context -> NaN, never a forced anomaly.
    flat = feat.iloc[:30].copy()
    flat["temperature_c"] = 20.0
    flat["temperature_prev_mean_2h"] = 20.0
    flat["temperature_prev_std_2h"] = 0.0
    zf = compute_zscores(flat)
    assert zf["temperature_zscore_baseline"].iloc[29:].isna().all()
    flags = compute_zscore_flags(zf)
    assert flags["temperature_zscore_flag"].iloc[29:].isna().all()


def test_zscore_flag_threshold():
    z = pd.DataFrame({
        "temperature_zscore_baseline": [3.5, -3.5, 2.9, 0.0, np.nan],
        "pressure_zscore_baseline": [0.0, 0.0, 0.0, 0.0, 0.0],
        "humidity_zscore_baseline": [0.0, 0.0, 0.0, 0.0, 0.0],
    })
    flags = compute_zscore_flags(z, z_threshold=3.0)
    assert flags["temperature_zscore_flag"].tolist()[:4] == [1.0, 1.0, 0.0, 0.0]
    assert np.isnan(flags["temperature_zscore_flag"].iloc[4])


# ==============================================================================
# IQR correctness
# ==============================================================================

def test_iqr_quartiles_known_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    seg = pd.Series([0] * 8)
    q1, q3 = causal_rolling_quartiles(s, seg, 4)
    assert q1.iloc[:4].isna().all()
    # Row 4 uses prior window [1,2,3,4]: Q1=1.75, Q3=3.25.
    assert np.isclose(q1.iloc[4], 1.75)
    assert np.isclose(q3.iloc[4], 3.25)


def test_iqr_does_not_cross_segments():
    s = pd.Series([1.0] * 6 + [100.0] * 6)
    seg = pd.Series([0] * 6 + [1] * 6)
    q1, q3 = causal_rolling_quartiles(s, seg, 4)
    # Segment-1 rows use only segment-1 history: Q1 == Q3 == 100.
    assert np.isclose(q1.iloc[10], 100.0)
    assert np.isclose(q3.iloc[10], 100.0)
    # First rows of the new segment lack full in-segment history.
    assert q1.iloc[6:9].isna().all()


def test_iqr_flags_outside_bounds():
    n = 10
    feat = pd.DataFrame({
        "timestamp": [f"2024-01-01 00:{i:02d}:00" for i in range(n)],
        "source_dataset": ["jena"] * n,
        "temperature_c": [20.0] * 9 + [40.0],
        "pressure_hpa": [1000.0] * n,
        "relative_humidity_pct": [50.0] * n,
        "segment_id": [0] * n,
    })
    flags = compute_iqr_flags(feat, window_rows=4)
    assert flags["temperature_iqr_flag"].iloc[4] == 0.0  # inside flat context
    assert flags["temperature_iqr_flag"].iloc[9] == 1.0  # spike outside
    assert flags["temperature_iqr_flag"].iloc[:4].isna().all()


# ==============================================================================
# Combined baseline on real samples
# ==============================================================================

def test_output_schema_and_row_counts(jena_sample, delhi_sample):
    for (feat, qual), ds in ((jena_sample, "jena"), (delhi_sample, "delhi")):
        out, _ = build_statistical_baseline(feat, qual, ds)
        assert list(out.columns) == BASELINE_COLUMNS
        assert len(out) == len(feat)


def test_observations_pass_through_unchanged(jena_sample):
    feat, qual = jena_sample
    out, _ = build_statistical_baseline(feat, qual, "jena")
    for col in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
        assert (out[col].isna() == feat[col].isna()).all()
        assert np.allclose(out.loc[out[col].notna(), col],
                           feat.loc[feat[col].notna(), col])


def test_excluded_rows_carry_no_decision(delhi_sample):
    feat, qual = delhi_sample
    out, _ = build_statistical_baseline(feat, qual, "delhi")
    # Sample rows 0-299 are all valid; force exclusions instead.
    qual2 = qual.copy()
    qual2.loc[10:12, "ml_eligible"] = 0
    qual2.loc[10:12, "quality_status"] = "DATA_AVAILABILITY_EVENT"
    out2, _ = build_statistical_baseline(feat, qual2, "delhi")
    sub = out2.iloc[10:13]
    assert (sub["baseline_status"] == "DATA_QUALITY_EXCLUDED").all()
    assert sub["statistical_baseline_flag"].isna().all()
    score_cols = [c for c in BASELINE_COLUMNS if "zscore_baseline" in c or c.endswith(("_zscore_flag", "_iqr_flag"))]
    assert sub[score_cols].isna().all().all()


def test_possible_freeze_processed_normally(delhi_sample):
    feat, qual = delhi_sample
    out, _ = build_statistical_baseline(feat, qual, "delhi")
    frozen = qual["quality_status"] == "POSSIBLE_FREEZE"
    assert (out.loc[frozen, "baseline_status"] != "DATA_QUALITY_EXCLUDED").all()


def test_combined_flag_logic_and_reasons(jena_sample):
    feat, qual = jena_sample
    out, _ = build_statistical_baseline(feat, qual, "jena")
    avail = out["statistical_flags_available"].to_numpy()
    count = out["statistical_anomaly_count"].to_numpy()
    flag = out["statistical_baseline_flag"].to_numpy(dtype=float)
    assert ((flag[avail == 0] != flag[avail == 0])).all()  # all NaN
    assert (flag[(avail > 0) & (count > 0)] == 1.0).all()
    assert (flag[(avail > 0) & (count == 0)] == 0.0).all()
    assert (count <= avail).all()
    vocab = {"within_baseline_bounds", "insufficient_history", "missing_input"}
    for r in out["statistical_baseline_reason"].unique():
        assert (r in vocab or "_zscore" in r or "_iqr" in r
                or r.startswith(("multi_variable_statistical", "data_quality_excluded")))


# ==============================================================================
# Threshold-absence + 55 C checks
# ==============================================================================

def test_no_hardcoded_pressure_thresholds_in_baseline(project_root):
    import re

    # Fail only on threshold *usage* (comparisons), not on prose that
    # explicitly disclaims the 950-1030 rule.
    threshold_use = re.compile(r"[<>]=?\s*(950|1030)|(950|1030)\s*[<>]=?")
    for name in ("zscore_baseline.py", "iqr_baseline.py", "statistical_baseline.py",
                 "validation.py", "run.py"):
        text = (project_root / "src" / "baseline" / name).read_text(encoding="utf-8")
        assert not threshold_use.search(text), f"pressure threshold usage in {name}"


def test_unusual_pressure_not_auto_rejected(project_root):
    out = pd.read_csv(project_root / "data" / "baseline" / "delhi_statistical_baseline.csv",
                      usecols=["pressure_hpa", "statistical_baseline_flag"])
    low_pass = ((out["pressure_hpa"] < 950) & (out["statistical_baseline_flag"] == 0.0)).sum()
    assert low_pass > 0  # sub-950 pressures routinely pass on statistical context


def test_55c_preserved_and_not_auto_rejected():
    n = 80
    base = pd.Timestamp("2024-01-01 00:00")
    stamps = [(base + pd.Timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]
    feat = pd.DataFrame({
        "timestamp": stamps, "source_dataset": ["delhi"] * n,
        "temperature_c": [55.0] * n,  # stable extreme context
        "pressure_hpa": [1000.0 + (i % 5) * 0.1 for i in range(n)],
        "relative_humidity_pct": [50.0 + (i % 7) * 0.1 for i in range(n)],
        "temperature_prev_mean_2h": [55.0] * n,
        "temperature_prev_std_2h": [0.0] * n,  # zero variance -> NaN, not anomaly
        "pressure_prev_mean_2h": [1000.2] * n,
        "pressure_prev_std_2h": [0.2] * n,
        "humidity_prev_mean_2h": [50.3] * n,
        "humidity_prev_std_2h": [0.2] * n,
        "segment_id": [0] * n,
    })
    out, _ = build_statistical_baseline(feat, _pass_quality(n), "delhi")
    assert (out["temperature_c"] == 55.0).all()  # unchanged
    assert (out["baseline_status"] == "COMPUTED").all()  # not excluded
    assert (out["temperature_zscore_flag"].isna()).all()  # NaN, not forced


# ==============================================================================
# Causality, determinism, immutability
# ==============================================================================

def test_anti_future_leakage(jena_sample):
    feat, qual = jena_sample
    sample = feat.iloc[:100].copy().reset_index(drop=True)
    qsample = qual.iloc[:100].copy().reset_index(drop=True)
    out_orig, _ = build_statistical_baseline(sample, qsample, "jena")
    # Shock a full future 12-row window (rows 80-91); the shocked rows'
    # own passthrough echoes are expected to differ.
    perturbed = sample.copy()
    perturbed.loc[80:91, "temperature_c"] = perturbed.loc[80:91, "temperature_c"] + 50.0
    out_pert, _ = build_statistical_baseline(perturbed, qsample, "jena")
    pd.testing.assert_frame_equal(out_orig.iloc[:80], out_pert.iloc[:80])
    # Row 92's IQR window is entirely shocked (+50): bounds collapse far
    # from the normal current value, so the flag must be 1 (sensitivity).
    assert out_pert.loc[92, "temperature_iqr_flag"] == 1.0


def test_baseline_deterministic(delhi_sample):
    feat, qual = delhi_sample
    out1, _ = build_statistical_baseline(feat, qual, "delhi")
    out2, _ = build_statistical_baseline(feat, qual, "delhi")
    pd.testing.assert_frame_equal(out1, out2)


def test_upstream_datasets_unchanged(project_root):
    assert len(pd.read_csv(project_root / "data" / "features" / "jena_features.csv",
                           usecols=["timestamp"])) == 420224
    assert len(pd.read_csv(project_root / "data" / "features" / "delhi_features.csv",
                           usecols=["timestamp"])) == 289728
    assert len(pd.read_csv(project_root / "data" / "features" / "jena_features.csv",
                           nrows=0).columns) == 106
    assert len(pd.read_csv(project_root / "data" / "quality" / "delhi_quality.csv",
                           usecols=["timestamp"])) == 289728

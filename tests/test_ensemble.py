"""Phase 10 ensemble tests: clean-only calibration, aggregation, guards."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ensemble import aggregation as G
from src.ensemble import calibration as C
from src.ensemble.threshold import THRESHOLD_QUANTILE, fit_threshold

DATASETS = ("jena", "delhi")


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


# 1-4. Clean-only ECDF calibration; train-only percentile transforms.
def test_1_4_ecdf_clean_only():
    train = np.array([0.1, 0.2, 0.2, 0.5, 0.9])
    frozen = C.fit_ecdf(train)
    assert (frozen == np.sort(train)).all()
    cal = C.calibrate(np.array([0.05, 0.2, 0.9, 5.0]), frozen)
    assert cal[0] == pytest.approx(0.0)       # below minimum
    assert cal[1] == pytest.approx(3 / 5)     # ties share one rank
    assert cal[2] == pytest.approx(1.0)       # maximum
    assert cal[3] == pytest.approx(1.0)       # above maximum
    assert np.isnan(C.calibrate(np.array([np.nan]), frozen)[0])
    with pytest.raises(ValueError):
        C.fit_ecdf(np.array([np.nan, np.nan]))


# 2+3. Calibration/threshold code paths never touch labels or bench files.
def test_2_3_no_label_or_bench_inputs():
    import inspect

    from src.ensemble import evaluator as E

    fit_src = inspect.getsource(E.fit_calibration) + inspect.getsource(E.fit_thresholds)
    lowered = fit_src.lower()
    assert "ground_truth" not in lowered and "injection" not in lowered
    assert "benchmark" not in lowered and "manifest" not in lowered
    assert "test_in_distribution" not in lowered and "test_generalization" not in lowered


# 5. Score direction: higher raw -> higher calibrated evidence.
def test_5_score_direction():
    frozen = C.fit_ecdf(np.linspace(0, 10, 101))
    cal = C.calibrate(np.array([1.0, 9.0]), frozen)
    assert cal[1] > cal[0]


# 6+7. Equal-weight mean and median aggregation.
def test_6_7_aggregation():
    mat = np.array([[0.2, 0.4, 0.6], [0.1, 0.9, np.nan]])
    mean, median, avail = G.combine(mat)
    assert mean[0] == pytest.approx(0.4) and median[0] == pytest.approx(0.4)
    assert avail[0] == G.FULL_EVIDENCE
    assert mean[1] == pytest.approx(0.5) and median[1] == pytest.approx(0.5)
    assert avail[1] == G.PARTIAL_EVIDENCE
    stat, n = G.statistical_component(np.array([0.3, np.nan]), np.array([0.5, 0.7]))
    assert stat[0] == pytest.approx(0.4) and stat[1] == pytest.approx(0.7)
    assert (n == np.array([2, 1])).all()


# 8. Missing evidence: <2 components -> NaN, never zero-filled.
def test_8_missing_evidence():
    mean, median, avail = G.combine(np.array([[0.8, np.nan, np.nan], [np.nan] * 3]))
    assert np.isnan(mean).all() and np.isnan(median).all()
    assert (avail == G.INSUFFICIENT_EVIDENCE).all()


# 9+10. Threshold from clean scores; frozen reuse in predictions.
def test_9_10_threshold_frozen(project_root):
    scores = np.linspace(0.0, 2.0, 2001)
    thr, diag = fit_threshold(scores, 0.99)
    assert abs(thr - np.quantile(scores, 0.99)) < 1e-12
    assert THRESHOLD_QUANTILE == 0.99
    cfg = json.load(open(project_root / "reports" / "ensemble" / "calibration_config.json"))
    for ds in DATASETS:
        for method, flag in (("ens_mean", "ens_mean_flag"), ("ens_median", "ens_median_flag")):
            pred = pd.read_csv(project_root / "data" / "ensemble" / f"{ds}_ensemble_predictions.csv",
                               usecols=["ens_mean", "ens_median", flag, "availability"])
            sc = pred[pred["availability"] != "INSUFFICIENT_EVIDENCE"]
            assert ((sc[method] >= cfg[ds]["thresholds"][method]).astype(int)
                    == sc[flag]).all()


# 11+12. ID/OOD separation; combos only in OOD.
def test_11_12_split_and_combo_separation(project_root):
    for ds in DATASETS:
        pred = pd.read_csv(project_root / "data" / "ensemble" / f"{ds}_ensemble_predictions.csv",
                           usecols=["timestamp", "split"])
        id_ts = set(pd.read_csv(project_root / "data" / "benchmark" / ds
                                / "test_in_distribution.csv", usecols=["timestamp"])["timestamp"])
        ood_ts = set(pd.read_csv(project_root / "data" / "benchmark" / ds
                                 / "test_generalization.csv", usecols=["timestamp"])["timestamp"])
        assert set(pred[pred["split"] == "test_in_distribution"]["timestamp"]) == id_ts
        assert set(pred[pred["split"] == "test_generalization"]["timestamp"]) == ood_ts
        assert not (id_ts & ood_ts)
        ev = pd.read_csv(project_root / "reports" / "ensemble" / f"{ds}_event_results.csv")
        combo = ev[ev["fault_type"] == "SPIKE_PLUS_DRIFT"]
        assert (combo["split"] == "test_generalization").all() and len(combo) > 0


# 13+14. Event detection and latency on fixtures.
def test_13_14_events_latency():
    from src.ensemble.evaluator import build_event_frame

    rows = pd.DataFrame({
        "timestamp": ["2024-01-01 00:00:00", "2024-01-01 00:05:00", "2024-01-01 00:10:00"],
        "ens_mean_flag": [0, 1, 0],
        "injection_id": ["E1", "E1", "E1"],
    })
    ev = pd.DataFrame([{"injection_id": "E1", "fault_type": "SPIKE",
                        "target_variable": "temperature_c", "split": "test_in_distribution",
                        "start_timestamp": "2024-01-01 00:00:00",
                        "end_timestamp": "2024-01-01 00:10:00", "duration_minutes": 10.0}])
    out = build_event_frame(rows, "ens_mean_flag", ev, "delhi", "test_in_distribution")
    assert int(out.loc[0, "detected"]) == 1
    assert float(out.loc[0, "latency_minutes"]) == 5.0
    assert float(out.loc[0, "row_coverage"]) == pytest.approx(1 / 3)


# 15. Deterministic calibration: same inputs, same outputs.
def test_15_deterministic_calibration():
    train = np.array([0.3, 0.1, 0.9, 0.5])
    assert (C.calibrate(np.array([0.4]), C.fit_ecdf(train))
            == C.calibrate(np.array([0.4]), C.fit_ecdf(train))).all()
    m1 = G.combine(np.array([[0.2, 0.8, 0.5]]))
    m2 = G.combine(np.array([[0.2, 0.8, 0.5]]))
    assert m1[0] == m2[0] and m1[1] == m2[1] and (m1[2] == m2[2]).all()


# 16. Artifacts exist with provenance metadata.
def test_16_artifacts_exist(project_root):
    for ds in DATASETS:
        assert (project_root / "models" / "ensemble" / f"{ds}_calibration.joblib").is_file()
        assert (project_root / "data" / "ensemble" / f"{ds}_ensemble_predictions.csv").is_file()
    rep = project_root / "reports" / "ensemble"
    for name in ("ensemble_evaluation.md", "ensemble_metrics.csv", "event_metrics.csv",
                 "jena_event_results.csv", "delhi_event_results.csv",
                 "ood_metrics.csv", "false_positive_analysis.csv",
                 "calibration_config.json", "phase6_phase7_phase9_comparison.csv"):
        assert (rep / name).is_file(), name
    cfg = json.load(open(rep / "calibration_config.json"))
    for ds in DATASETS:
        assert cfg[ds]["benchmark_labels_used_for_calibration"] is False
        assert cfg[ds]["benchmark_labels_used_for_threshold"] is False
        assert cfg[ds]["benchmark_train_used_for_calibration"] is False
        assert cfg[ds]["synthetic_training_contamination"] == 0
        assert set(cfg[ds]["thresholds"]) == {"ens_mean", "ens_median"}


# 17-21. Frozen-phase invariants: nothing retrained or modified.
def test_17_21_frozen_invariants(project_root):
    assert len(pd.read_csv(project_root / "data" / "features" / "jena_features.csv",
                           usecols=["timestamp"])) == 420224
    assert len(pd.read_csv(project_root / "data" / "evaluation" / "statistical_baseline"
                           / "summary_metrics.csv")) > 0
    assert len(pd.read_csv(project_root / "data" / "benchmark" / "jena" / "train.csv",
                           usecols=["timestamp"])) == 251969
    if_cfg = json.load(open(project_root / "reports" / "isolation_forest" / "model_config.json"))
    assert if_cfg["jena"]["threshold_raw"] == pytest.approx(0.026259994424697897)
    assert if_cfg["delhi"]["threshold_raw"] == pytest.approx(0.035639253732814624)
    lstm_cfg = json.load(open(project_root / "reports" / "lstm_autoencoder" / "model_config.json"))
    assert lstm_cfg["jena"]["threshold_value"] == pytest.approx(1.301953, abs=1e-3)
    assert lstm_cfg["delhi"]["threshold_value"] == pytest.approx(1.557834, abs=1e-3)
    assert (project_root / "data" / "noaa" / "metadata" / "station_manifest.json").is_file()
    assert (project_root / "data" / "noaa" / "metadata" / "neighbor_graph.csv").is_file()
    from src.baseline.zscore_baseline import Z_THRESHOLD
    from src.baseline.iqr_baseline import IQR_FACTOR

    assert Z_THRESHOLD == 3.0 and IQR_FACTOR == 1.5

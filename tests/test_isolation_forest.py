"""Phase 7 Isolation Forest tests.

Training uses CLEAN pre-benchmark observations (data/processed/) only.
No benchmark labels, files, or mutated values enter fitting/thresholding
(asserted structurally). Threshold frozen on clean train scores;
evaluation reuses it unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.isolation_forest import features as F
from src.isolation_forest import scoring as S
from src.isolation_forest.evaluator import (
    EXPECTED_TRAIN_PERIODS,
    TRAINING_SOURCE_TEMPLATE,
    load_clean_train_frame,
)
from src.isolation_forest.model import IF_PARAMS, MODEL_SEED, build_model
from src.isolation_forest.threshold import THRESHOLD_QUANTILE, fit_threshold

DATASETS = ("jena", "delhi")


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


@pytest.fixture(scope="module")
def feature_columns(project_root) -> list[str]:
    return list(pd.read_csv(project_root / "data" / "features" / "jena_features.csv",
                            nrows=0).columns)


# 1+2. Deterministic configuration + documented allowlist.
def test_1_2_config_and_allowlist(feature_columns):
    assert IF_PARAMS == {"n_estimators": 200, "max_samples": "auto", "contamination": "auto",
                         "max_features": 1.0, "bootstrap": False, "random_state": 26073, "n_jobs": -1}
    assert MODEL_SEED == 26073
    allowlist = F.build_allowlist(feature_columns)
    assert len(allowlist) == 94
    assert "timestamp" not in allowlist and "source_dataset" not in allowlist
    assert not any("missing" in c for c in allowlist)
    assert not any(c in allowlist for c in ("segment_id", "gap_before", "elapsed_minutes_since_prev"))
    assert F.build_allowlist(feature_columns) == allowlist  # deterministic


# 3. Forbidden label/evaluation columns rejected loudly.
def test_3_forbidden_columns_rejected():
    bad = pd.DataFrame({"temperature_c": [1.0],
                        "ground_truth_anomaly": [0],
                        "injection_id": ["x"],
                        "target_variable": ["temperature_c"]})
    with pytest.raises(ValueError, match="[Ff]orbidden"):
        F.assert_no_forbidden_columns(bad)


# 4. No future-feature leakage: perturbing row k+1 leaves rows <=k flags unchanged.
def test_4_no_future_leakage(project_root):
    from src.isolation_forest.evaluator import predict_split, train_dataset

    clean = load_clean_train_frame("delhi", project_root).iloc[:400]
    bundle = train_dataset(clean, "delhi")
    bench = pd.read_csv(project_root / "data" / "benchmark" / "delhi" / "test_in_distribution.csv",
                        nrows=400)
    out_orig = predict_split(bundle, bench, "delhi", "test_in_distribution")
    perturbed = bench.copy()
    perturbed.loc[300, "temperature_c"] = perturbed.loc[300, "temperature_c"] + 50.0
    out_pert = predict_split(bundle, perturbed, "delhi", "train")
    # Past rows' flags identical (the shocked row's own echo may differ).
    assert (out_orig["if_anomaly_flag"].iloc[:300].to_numpy()
            == out_pert["if_anomaly_flag"].iloc[:300].to_numpy()).all()
    # Past raw scores identical too (no future information flows backward).
    assert np.allclose(out_orig["if_raw_score"].iloc[:300].fillna(0).to_numpy(),
                       out_pert["if_raw_score"].iloc[:300].fillna(0).to_numpy(),
                       equal_nan=True)


# 5. ML eligibility filtering: ineligible rows never fitted.
def test_5_eligibility_filtering(project_root):
    from src.isolation_forest.evaluator import prepare_split

    clean = load_clean_train_frame("delhi", project_root).iloc[:2000]
    features, quality = prepare_split(clean, "delhi")
    # Bundle records fitted < total whenever exclusions/scorability bite.
    from src.isolation_forest.evaluator import train_dataset

    bundle = train_dataset(clean, "delhi")
    assert bundle["n_train_fitted"] <= bundle["n_train_eligible"] <= bundle["n_train_rows"]
    assert bundle["n_train_fitted"] > 0


# 6+7. Score direction: higher raw = more anomalous; ECDF in [0,1].
def test_6_7_score_direction():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 4))
    model = build_model()
    model.fit(X)
    normal_raw = S.raw_scores(model, X[:5])
    outlier_raw = S.raw_scores(model, np.full((5, 4), 25.0))
    assert (outlier_raw > normal_raw).all()
    norm = S.normalize_scores(np.concatenate([normal_raw, outlier_raw]),
                              np.sort(S.raw_scores(model, X)))
    assert ((norm >= 0.0) & (norm <= 1.0)).all()
    assert norm[5:].mean() > norm[:5].mean()


# 8+9. Threshold from train only; frozen value reused at evaluation.
def test_8_9_threshold_frozen(project_root):
    scores = np.linspace(-2.0, 2.0, 1001)
    thr, diag = fit_threshold(scores, 0.99)
    assert abs(thr - np.quantile(scores, 0.99)) < 1e-12
    assert diag["method"].startswith("99%")
    for ds in DATASETS:
        artifact = __import__("joblib").load(
            project_root / "models" / "isolation_forest" / f"{ds}_isolation_forest.joblib")
        stored = np.asarray(artifact["train_raw_sorted"], dtype=float)
        assert artifact["threshold_raw"] == pytest.approx(float(np.quantile(stored, 0.99)))
        assert artifact["threshold_diag"]["quantile"] == THRESHOLD_QUANTILE == 0.99
        pred = pd.read_csv(project_root / "data" / "isolation_forest" / f"{ds}_isolation_forest_predictions.csv",
                           usecols=["if_raw_score", "if_anomaly_flag", "scorable"])
        sc = pred[pred["scorable"] == 1]
        assert ((sc["if_raw_score"] >= artifact["threshold_raw"]).astype(int)
                == sc["if_anomaly_flag"]).all()


# 10+11. Split separation; combos only in OOD.
def test_10_11_split_and_combo_separation(project_root):
    for ds in DATASETS:
        pred = pd.read_csv(project_root / "data" / "isolation_forest" / f"{ds}_isolation_forest_predictions.csv",
                           usecols=["timestamp", "split"])
        tr = pd.read_csv(project_root / "data" / "benchmark" / ds / "train.csv", usecols=["timestamp"])
        te = pd.read_csv(project_root / "data" / "benchmark" / ds / "test_generalization.csv",
                         usecols=["timestamp"])
        assert set(pred[pred["split"] == "train"]["timestamp"]) == set(tr["timestamp"])
        assert len(set(pred[pred["split"] == "train"]["timestamp"]) & set(te["timestamp"])) == 0
        ev = pd.read_csv(project_root / "reports" / "isolation_forest" / f"{ds}_event_results.csv")
        assert (ev[(ev["fault_type"] == "SPIKE_PLUS_DRIFT")]["split"] == "test_generalization").all()
        assert (ev[ev["split"] != "test_generalization"]["fault_type"] != "SPIKE_PLUS_DRIFT").all()


# 12+13+14. Event detection, latency, metric equations on fixtures.
def test_12_13_14_events_latency_metrics():
    from src.isolation_forest.evaluator import build_event_frame

    rows = pd.DataFrame({
        "timestamp": ["2024-01-01 00:00:00", "2024-01-01 00:05:00", "2024-01-01 00:10:00"],
        "if_anomaly_flag": [0, 1, 0],
        "injection_id": ["E1", "E1", "E1"],
    })
    ev = pd.DataFrame([{"injection_id": "E1", "fault_type": "SPIKE",
                        "target_variable": "temperature_c", "split": "test_in_distribution",
                        "start_timestamp": "2024-01-01 00:00:00",
                        "end_timestamp": "2024-01-01 00:10:00", "duration_minutes": 10.0}])
    out = build_event_frame(rows, ev, "delhi", "test_in_distribution")
    assert int(out.loc[0, "detected"]) == 1
    assert float(out.loc[0, "latency_minutes"]) == 5.0
    assert float(out.loc[0, "row_coverage"]) == pytest.approx(1 / 3)

    from src.evaluation.statistical_baseline.metrics import confusion_counts, prf_metrics

    cc = confusion_counts([1, 1, 0, 0], [1, 0, 0, 0])
    assert cc == {"tp": 1, "fp": 0, "tn": 2, "fn": 1, "n": 4}
    m = prf_metrics(cc["tp"], cc["fp"], cc["tn"], cc["fn"])
    assert m["recall"] == 0.5 and m["precision"] == 1.0


# 15. Model + prediction + report artifacts exist.
def test_15_artifacts_exist(project_root):
    for ds in DATASETS:
        assert (project_root / "models" / "isolation_forest" / f"{ds}_isolation_forest.joblib").is_file()
        assert (project_root / "data" / "isolation_forest" / f"{ds}_isolation_forest_predictions.csv").is_file()
    rep = project_root / "reports" / "isolation_forest"
    for name in ("isolation_forest_evaluation.md", "isolation_forest_metrics.csv", "event_metrics.csv",
                 "jena_event_results.csv", "delhi_event_results.csv",
                 "ood_metrics.csv", "false_positive_analysis.csv", "feature_manifest.json",
                 "model_config.json", "phase6_comparison.csv"):
        assert (rep / name).is_file(), name
    manifest = json.load(open(rep / "feature_manifest.json"))
    assert manifest["n_allowlisted"] == 94 and len(manifest["allowlisted_features"]) == 94
    cfg = json.load(open(rep / "model_config.json"))
    assert cfg["jena"]["random_seed"] == 26073


# 16. Reproducibility: refit with fixed seed gives identical predictions.
def test_16_reproducible(project_root):
    from src.isolation_forest.evaluator import predict_split, train_dataset

    clean = load_clean_train_frame("jena", project_root)
    sample = clean.iloc[:600].copy()
    eval_sample = pd.read_csv(project_root / "data" / "benchmark" / "jena" / "test_in_distribution.csv",
                              nrows=200)
    b1 = train_dataset(sample, "jena")
    b2 = train_dataset(sample, "jena")
    o1 = predict_split(b1, eval_sample, "jena", "test_in_distribution")
    o2 = predict_split(b2, eval_sample, "jena", "test_in_distribution")
    pd.testing.assert_frame_equal(o1, o2)


# 17. Phase 6 files unchanged (row counts + frozen constants).
def test_17_phase6_unchanged(project_root):
    assert len(pd.read_csv(project_root / "data" / "evaluation" / "statistical_baseline"
                           / "summary_metrics.csv")) > 0
    n = len(pd.read_csv(project_root / "data" / "evaluation" / "statistical_baseline"
                        / "jena_test_in_distribution_results.csv", usecols=["timestamp"]))
    assert n == 83895
    from src.baseline.zscore_baseline import Z_THRESHOLD
    from src.baseline.iqr_baseline import IQR_FACTOR

    assert Z_THRESHOLD == 3.0 and IQR_FACTOR == 1.5


# 18. Clean training source: loader reads data/processed only, exact boundaries.
@pytest.mark.parametrize("ds", DATASETS)
def test_18_clean_training_source(project_root, ds):
    from src.isolation_forest.evaluator import train_period_bounds

    expected_path = project_root / TRAINING_SOURCE_TEMPLATE.format(dataset=ds)
    assert expected_path.is_file()
    frame = load_clean_train_frame(ds, project_root)
    assert len(frame) > 0
    exp_start, exp_end = EXPECTED_TRAIN_PERIODS[ds]
    assert str(frame["timestamp"].iloc[0]) == exp_start
    assert str(frame["timestamp"].iloc[-1]) == exp_end
    assert train_period_bounds(project_root, ds) == (exp_start, exp_end)
    # No label/injection column may exist in the fitting input.
    F.assert_no_forbidden_columns(frame)


# 19. Benchmark train frames can never be fitted: the train path rejects them.
@pytest.mark.parametrize("ds", DATASETS)
def test_19_benchmark_train_rejected_for_fit(project_root, ds):
    from src.isolation_forest.evaluator import train_dataset

    bench = pd.read_csv(project_root / "data" / "benchmark" / ds / "train.csv", nrows=500)
    assert "ground_truth_anomaly" in bench.columns  # guard is meaningful
    with pytest.raises(ValueError, match="[Ff]orbidden"):
        train_dataset(bench, ds)


# 20. Zero benchmark-injected values in fit: for every train-split record
# whose sensor value was actually mutated (clean_value != injected_value),
# the fitting input holds the clean value, never the mutated one.
# (Ramp-start drift rows / already-constant frozen rows can be bit-identical
# in both files, so the assertion is made on truly mutated records only.)
@pytest.mark.parametrize("ds", DATASETS)
def test_20_zero_injected_values_in_fit(project_root, ds):
    core = ["temperature_c", "pressure_hpa", "relative_humidity_pct"]
    frame = load_clean_train_frame(ds, project_root).set_index("timestamp")
    gt = pd.read_csv(project_root / "data" / "benchmark" / "ground_truth"
                     / f"{ds}_injected_values.csv")
    recs = gt[gt["injection_id"].str.contains("-train-", na=False)]
    recs = recs[recs["clean_value"] != recs["injected_value"]]
    assert len(recs) > 0  # test is vacuous otherwise
    for var in core:
        sub = recs[recs["target_variable"] == var]
        if len(sub) == 0:
            continue
        fitted_vals = frame.loc[sub["timestamp"].tolist(), var].to_numpy(float)
        assert np.isclose(fitted_vals, sub["clean_value"].to_numpy(float)).all()
        assert not np.isclose(fitted_vals, sub["injected_value"].to_numpy(float),
                              equal_nan=True).all()


# 21. Artifacts declare clean provenance with zero contamination.
def test_21_artifact_provenance(project_root):
    cfg = json.load(open(project_root / "reports" / "isolation_forest" / "model_config.json"))
    manifest = json.load(open(project_root / "reports" / "isolation_forest" / "feature_manifest.json"))
    for ds in DATASETS:
        assert cfg[ds]["training_source"] == TRAINING_SOURCE_TEMPLATE.format(dataset=ds)
        assert cfg[ds]["training_data"] == "clean pre-benchmark observations"
        assert cfg[ds]["benchmark_train_used_for_fit"] is False
        assert cfg[ds]["synthetic_training_contamination"] == 0
    assert manifest["benchmark_train_used_for_fit"] is False
    assert manifest["synthetic_training_contamination"] == 0
    assert manifest["training_data"] == "clean pre-benchmark observations"

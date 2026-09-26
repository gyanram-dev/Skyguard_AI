"""Phase 11 root-cause tests: provenance, rules, SHAP, end-to-end, guards."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.root_cause import confidence as CF
from src.root_cause import explain as EX
from src.root_cause import unknown_mixed as UM
from src.root_cause.classifier import MODEL_SEED, RF_PARAMS, build_classifier
from src.root_cause.features import (
    DIAGNOSTIC_FEATURES,
    TRAIN_CLASS_MAP,
    build_evidence_frame,
    map_training_class,
)

DATASETS = ("jena", "delhi")


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


# 1+2. Training labels: TRAIN fault rows only; ID/OOD excluded structurally.
def test_1_2_training_label_provenance(project_root):
    from src.root_cause import evaluator as E

    import inspect

    src = inspect.getsource(E.fit_dataset)
    assert "test_in_distribution" not in src and "test_generalization" not in src
    assert '"train"' in src or "'train'" in src
    for ds in DATASETS:
        train = pd.read_csv(project_root / "data" / "benchmark" / ds / "train.csv",
                            usecols=["ground_truth_fault_type"])
        assert set(train["ground_truth_fault_type"].unique()) <= {
            "NONE", "SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE"}
    cfg = json.load(open(project_root / "reports" / "root_cause" / "model_config.json"))
    for ds in DATASETS:
        assert cfg[ds]["id_labels_used_for_training"] is False
        assert cfg[ds]["ood_labels_used_for_training"] is False
        assert "train.csv" in cfg[ds]["training_source"]


# 3. Communication gaps and normals never map to a training class.
def test_3_gap_exclusion():
    assert map_training_class("COMMUNICATION_GAP") is None
    assert map_training_class("NONE") is None
    assert map_training_class("UNKNOWN_CLASS") is None


# 4. SPIKE_PLUS_DRIFT maps to MIXED, never forced into SPIKE/DRIFT.
def test_4_mixed_mapping():
    assert map_training_class("SPIKE_PLUS_DRIFT") == "MIXED"
    assert TRAIN_CLASS_MAP["CROSS_VARIABLE"] == "CROSS"
    assert TRAIN_CLASS_MAP["SPIKE"] == "SPIKE"


# 5+6. Feature allowlist membership; forbidden label leakage rejected.
def test_5_6_allowlist_and_leakage():
    assert len(DIAGNOSTIC_FEATURES) == 38
    keep = {"z_maxabs", "if_raw", "lstm_target_mse", "ens_mean", "temperature_delta",
            "temperature_trend_2h", "multivariate_max_abs_robust_deviation_2h"}
    assert keep <= set(DIAGNOSTIC_FEATURES)
    bad = pd.DataFrame({c: [1.0] for c in DIAGNOSTIC_FEATURES})
    bad["ground_truth_anomaly"] = [1]
    with pytest.raises(ValueError, match="[Ff]orbidden"):
        build_evidence_frame(bad)
    good = pd.DataFrame({c: [1.0] * 3 for c in DIAGNOSTIC_FEATURES})
    X, complete = build_evidence_frame(good)
    assert complete.all() and list(X.columns) == list(DIAGNOSTIC_FEATURES)
    good.loc[0, "if_raw"] = np.nan
    _, complete2 = build_evidence_frame(good)
    assert not complete2[0] and complete2[1:].all()


# 7+16. Deterministic classifier config; refit reproducibility on fixtures.
def test_7_16_deterministic_and_reproducible():
    assert RF_PARAMS == {"n_estimators": 300, "max_features": "sqrt", "min_samples_leaf": 3,
                         "class_weight": "balanced_subsample", "random_state": 26073, "n_jobs": -1}
    assert MODEL_SEED == 26073
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(60, len(DIAGNOSTIC_FEATURES))), columns=DIAGNOSTIC_FEATURES)
    y = pd.Series(["SPIKE", "DRIFT"] * 30)
    m1 = build_classifier().fit(X, y)
    m2 = build_classifier().fit(X, y)
    np.testing.assert_array_equal(m1.predict(X), m2.predict(X))
    np.testing.assert_allclose(m1.predict_proba(X), m2.predict_proba(X))


# 8+9+10. Confidence, UNKNOWN, and MIXED rules.
def test_8_9_10_confidence_unknown_mixed():
    assert CF.UNKNOWN_PROBA == 0.60
    assert CF.MIXED_SECOND_PROBA == 0.35 and CF.MIXED_GAP == 0.25
    classes = ["SPIKE", "DRIFT", "FROZEN", "CROSS"]
    labels, conf, _ = UM.decide(np.array([[0.50, 0.30, 0.10, 0.10]]), classes)
    assert labels[0] == "UNKNOWN" and conf[0] == pytest.approx(0.50)
    labels, _, _ = UM.decide(np.array([[0.62, 0.30, 0.05, 0.03]]), classes)
    assert labels[0] == "SPIKE"  # confident, runner-up too weak for MIXED
    labels, _, runner = UM.decide(np.array([[0.60, 0.35, 0.05, 0.00]]), classes)
    assert labels[0] == "MIXED" and runner[0] == "DRIFT"
    labels, _, _ = UM.decide(np.array([[0.90, 0.05, 0.03, 0.02]]), classes)
    assert labels[0] == "SPIKE"


# 11+12. SHAP generation and top-k ordering.
def test_11_12_shap_topk():
    rng = np.random.default_rng(2)
    X = pd.DataFrame(rng.normal(size=(40, len(DIAGNOSTIC_FEATURES))), columns=DIAGNOSTIC_FEATURES)
    y = pd.Series(["SPIKE", "DRIFT"] * 20)
    model = build_classifier().fit(X, y)
    import shap

    explainer = shap.TreeExplainer(model)
    vals = explainer.shap_values(X.iloc[:3])
    vals = np.stack(vals, axis=-1) if isinstance(vals, list) else np.asarray(vals)
    assert vals.shape[1] == len(DIAGNOSTIC_FEATURES)
    row = pd.Series({c: 1.0 for c in DIAGNOSTIC_FEATURES} |
                    {"z_maxabs": 8.0, "lstm_target_mse": 5.0,
                     "temperature_zero_delta_ratio_2h": 0.0,
                     "pressure_zero_delta_ratio_2h": 0.0,
                     "humidity_zero_delta_ratio_2h": 0.0,
                     "temperature_trend_2h": 0.0, "pressure_trend_2h": 0.0,
                     "humidity_trend_2h": 0.0,
                     "multivariate_max_abs_robust_deviation_2h": 1.0})
    top = EX.shap_top_features(vals[0, :, 0], list(DIAGNOSTIC_FEATURES),
                               X.iloc[0].to_numpy(dtype=float), k=5)
    assert len(top) == 5
    assert [abs(t["shap_value"]) for t in top] == sorted(
        [abs(t["shap_value"]) for t in top], reverse=True)
    text = EX.compose_explanation("SPIKE", row, top)
    assert "8.00" in text and "contributing to the classifier's prediction" in text
    assert "caused" not in text.lower()


# 13. No future leakage: evidence features are causal Phase 3/detector outputs.
def test_13_no_future_leakage():
    from src.lstm_autoencoder.features import LSTM_FEATURES

    from src.isolation_forest.features import build_allowlist
    import pandas as pd

    cols = list(pd.read_csv(Path(".").resolve() / "data" / "features" / "jena_features.csv",
                            nrows=0).columns)
    allow = set(build_allowlist(cols)) | {"z_maxabs", "iqr_combined", "if_raw", "if_cal",
                                          "lstm_target_mse", "lstm_full_mse", "ens_mean",
                                          "ens_median", "n_components_available", "ml_eligible"}
    temporal = [c for c in DIAGNOSTIC_FEATURES if c not in
                ("z_maxabs", "iqr_combined", "if_raw", "if_cal", "lstm_target_mse",
                 "lstm_full_mse", "ens_mean", "ens_median", "n_components_available",
                 "ml_eligible")]
    assert set(temporal) <= allow
    assert set(LSTM_FEATURES) <= allow  # shared causal provenience


# 14. End-to-end accounting: misses can never be correct diagnoses.
def test_14_end_to_end_accounting(project_root):
    ee = pd.read_csv(project_root / "reports" / "root_cause" / "end_to_end_diagnosis.csv")
    missed = ee[ee["detected"] == 0]
    assert (missed["correct"] == 0).all()
    assert set(ee["predicted_class"].unique()) <= {
        "SPIKE", "FROZEN", "DRIFT", "CROSS", "MIXED", "UNKNOWN", "MISSED", "UNDIAGNOSED"}
    for (ds, split), sub in ee.groupby(["dataset", "split"]):
        assert len(sub) > 0
        assert sub["correct"].sum() <= sub["detected"].sum()


# 15. Artifacts exist with required metadata and SHAP examples.
def test_15_artifacts_exist(project_root):
    for ds in DATASETS:
        assert (project_root / "models" / "root_cause" / f"{ds}_root_cause.joblib").is_file()
        assert (project_root / "models" / "root_cause" / f"{ds}_root_cause_explainer.joblib").is_file()
        assert (project_root / "data" / "root_cause" / f"{ds}_root_cause_predictions.csv").is_file()
    rep = project_root / "reports" / "root_cause"
    for name in ("root_cause_evaluation.md", "root_cause_metrics.csv", "confusion_matrices.csv",
                 "unknown_metrics.csv", "mixed_metrics.csv", "end_to_end_diagnosis.csv",
                 "feature_manifest.json", "model_config.json"):
        assert (rep / name).is_file(), name
    assert len(list((rep / "shap_examples").glob("*.json"))) > 0
    cfg = json.load(open(rep / "model_config.json"))
    for ds in DATASETS:
        assert cfg[ds]["classifier_params"]["random_state"] == 26073
        assert cfg[ds]["seed"] == 26073
        assert "TreeExplainer" in cfg[ds]["shap_method"]


# 17. Previous phases unchanged (counts, thresholds, frozen files).
def test_17_previous_phases_unchanged(project_root):
    assert len(pd.read_csv(project_root / "data" / "features" / "jena_features.csv",
                           usecols=["timestamp"])) == 420224
    assert len(pd.read_csv(project_root / "data" / "evaluation" / "statistical_baseline"
                           / "summary_metrics.csv")) > 0
    assert len(pd.read_csv(project_root / "data" / "benchmark" / "jena" / "train.csv",
                           usecols=["timestamp"])) == 251969
    if_cfg = json.load(open(project_root / "reports" / "isolation_forest" / "model_config.json"))
    assert if_cfg["jena"]["threshold_raw"] == pytest.approx(0.026259994424697897)
    ens_cfg = json.load(open(project_root / "reports" / "ensemble" / "calibration_config.json"))
    assert set(ens_cfg["jena"]["thresholds"]) == {"ens_mean", "ens_median"}
    assert (project_root / "data" / "noaa" / "metadata" / "neighbor_graph.csv").is_file()
    assert (project_root / "models" / "lstm_autoencoder" / "jena_scaler.joblib").is_file()
    from src.baseline.zscore_baseline import Z_THRESHOLD
    from src.baseline.iqr_baseline import IQR_FACTOR

    assert Z_THRESHOLD == 3.0 and IQR_FACTOR == 1.5

"""Phase 9 LSTM autoencoder tests: provenance, causality, scoring, artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.isolation_forest.evaluator import (
    EXPECTED_TRAIN_PERIODS,
    TRAINING_SOURCE_TEMPLATE,
    load_clean_train_frame,
)
from src.lstm_autoencoder import model as M
from src.lstm_autoencoder import scoring as S
from src.lstm_autoencoder.features import LSTM_FEATURES, validate_feature_schema
from src.lstm_autoencoder.sequences import (
    LOOKBACK,
    build_sequences,
    valid_sequence_mask,
)
from src.lstm_autoencoder.threshold import THRESHOLD_QUANTILE, fit_threshold
from src.lstm_autoencoder.training import chronological_split, fit_scaler

DATASETS = ("jena", "delhi")


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


# 1+4. Clean source provenance + exact training boundaries.
def test_1_4_clean_source_and_boundaries(project_root):
    for ds in DATASETS:
        assert TRAINING_SOURCE_TEMPLATE.format(dataset=ds) == f"data/processed/{ds}_clean.csv"
        assert (project_root / "data" / "processed" / f"{ds}_clean.csv").is_file()
    assert EXPECTED_TRAIN_PERIODS["jena"] == ("2009-01-01 00:10:00", "2013-10-17 22:50:00")
    assert EXPECTED_TRAIN_PERIODS["delhi"] == ("2022-04-01 00:00:00", "2023-11-25 14:15:00")
    from src.isolation_forest.evaluator import train_period_bounds

    for ds in DATASETS:
        assert train_period_bounds(project_root, ds) == EXPECTED_TRAIN_PERIODS[ds]


# 2. Benchmark-train frames are rejected before any fitting work.
def test_2_benchmark_train_rejected(project_root):
    from src.lstm_autoencoder.evaluator import train_pipeline

    bench = pd.read_csv(project_root / "data" / "benchmark" / "delhi" / "train.csv", nrows=200)
    assert "ground_truth_anomaly" in bench.columns
    with pytest.raises(ValueError, match="[Ff]orbidden"):
        train_pipeline(bench, "delhi")


# 3. Zero synthetic contamination: mutated values never in the fit input.
@pytest.mark.parametrize("ds", DATASETS)
def test_3_zero_contamination(project_root, ds):
    frame = load_clean_train_frame(ds, project_root).set_index("timestamp")
    gt = pd.read_csv(project_root / "data" / "benchmark" / "ground_truth"
                     / f"{ds}_injected_values.csv")
    recs = gt[gt["injection_id"].str.contains("-train-", na=False)]
    recs = recs[recs["clean_value"] != recs["injected_value"]]
    assert len(recs) > 0
    for var in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
        sub = recs[recs["target_variable"] == var]
        if len(sub) == 0:
            continue
        fitted = frame.loc[sub["timestamp"].tolist(), var].to_numpy(float)
        assert np.isclose(fitted, sub["clean_value"].to_numpy(float)).all()


# 5+6. Lookback windows [t-11..t] in chronological order.
def test_5_6_lookback_and_order():
    assert LOOKBACK == 12
    mat = np.arange(20 * 2, dtype=float).reshape(20, 2)
    valid = np.zeros(20, dtype=bool)
    valid[11:] = True
    X, pos = build_sequences(mat, valid)
    assert X.shape[1] == 12 and (pos == np.arange(11, 20)).all()
    np.testing.assert_array_equal(X[0], mat[0:12])
    np.testing.assert_array_equal(X[-1], mat[8:20])


# 7. No sequence crosses a segment boundary.
def test_7_no_cross_gap_sequences():
    segs = np.array([1] * 10 + [2] * 10)
    elig = np.ones(20, dtype=bool)
    fin = np.ones(20, dtype=bool)
    valid = valid_sequence_mask(segs, elig, fin)
    # Every 12-window here straddles index 10, so nothing is scorable.
    assert not valid.any()
    # Same-segment fixture: only the warm-up prefix is unscorable.
    valid2 = valid_sequence_mask(np.ones(20, dtype=int), elig, fin)
    assert not valid2[:11].any() and valid2[11:].all()
    for p in np.flatnonzero(valid2):
        assert (np.ones(20, dtype=int)[p - 11: p + 1] == 1).all()


# 8. NaN features and ineligible rows poison their whole window.
def test_8_scorable_mask():
    n = 30
    segs = np.ones(n, dtype=int)
    elig = np.ones(n, dtype=bool)
    fin = np.ones(n, dtype=bool)
    fin[15] = False
    elig[25] = False
    valid = valid_sequence_mask(segs, elig, fin)
    assert not valid[15:27].any()  # windows covering row 15
    assert not valid[25:30].any()  # windows covering row 25
    assert valid[14] and not valid[15]


# 9. Scaler fits on train rows only; frozen at evaluation.
def test_9_scaler_train_only():
    rng = np.random.default_rng(0)
    train = rng.normal(0, 1, size=(100, 4))
    mask = np.ones(100, dtype=bool)
    mask[::10] = False
    scaler = fit_scaler(train, mask)
    assert np.allclose(scaler.mean_, train[mask].mean(axis=0))
    shifted = rng.normal(50, 1, size=(10, 4))
    out = scaler.transform(shifted)
    assert out.mean() > 10  # test distribution does not move the scaler


# 10. Allowlist membership + forbidden columns rejected.
def test_10_allowlist_and_forbidden(project_root):
    assert len(LSTM_FEATURES) == 30
    cols = list(pd.read_csv(project_root / "data" / "features" / "jena_features.csv",
                            nrows=0).columns)
    assert validate_feature_schema(cols) == list(LSTM_FEATURES)
    bad = pd.DataFrame({"temperature_c": [1.0], "ground_truth_anomaly": [0]})
    with pytest.raises(ValueError, match="[Ff]orbidden"):
        validate_feature_schema(list(bad.columns))


# 11. Deterministic model configuration.
def test_11_deterministic_config():
    assert (M.MODEL_SEED, M.EPOCHS, M.BATCH_SIZE, M.LEARNING_RATE) == (26073, 30, 256, 0.001)
    assert M.ENCODER_UNITS == 64 and M.LATENT_DIM == 32
    M.set_global_seeds(26073)
    a = M.build_model(4).get_weights()
    M.set_global_seeds(26073)
    b = M.build_model(4).get_weights()
    for wa, wb in zip(a, b):
        np.testing.assert_array_equal(wa, wb)


# 12+13. Error direction (outlier > normal) and final-timestep scoring.
def test_12_13_error_direction_and_target_step():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(8, 12, 3))
    X_hat = X.copy()
    normal, _ = S.reconstruction_errors(X, X_hat)
    assert (normal == 0).all()
    X_bad = X.copy()
    X_bad[:, -1, :] += 10.0
    bad_target, bad_full = S.reconstruction_errors(X_bad, X_hat)
    assert (bad_target > normal).all() and (bad_full > 0).all()
    X_early = X.copy()
    X_early[:, 0, :] += 10.0
    early_target, early_full = S.reconstruction_errors(X_early, X_hat)
    # Early-step corruption barely moves the official target-step score...
    assert (early_target < bad_target).all()
    # ...but still appears in the full-sequence diagnostic.
    assert (early_full > 0).all()
    assert (S.flag_scores(np.array([0.1, 0.5]), 0.5) == np.array([0, 1])).all()


# 14+15. Train-only threshold; frozen reuse in predictions.
def test_14_15_threshold_frozen(project_root):
    scores = np.linspace(0.0, 1.0, 1001)
    thr, diag = fit_threshold(scores, 0.99)
    assert abs(thr - np.quantile(scores, 0.99)) < 1e-12
    assert THRESHOLD_QUANTILE == 0.99
    cfg = json.load(open(project_root / "reports" / "lstm_autoencoder" / "model_config.json"))
    for ds in DATASETS:
        assert cfg[ds]["threshold_method"].startswith("99%")
        pred = pd.read_csv(project_root / "data" / "lstm_autoencoder" / f"{ds}_lstm_predictions.csv",
                           usecols=["lstm_target_mse", "lstm_anomaly_flag", "scorable"])
        sc = pred[pred["scorable"] == 1]
        assert ((sc["lstm_target_mse"] >= cfg[ds]["threshold_value"]).astype(int)
                == sc["lstm_anomaly_flag"]).all()


# 16+17. ID/OOD separation; combos only in OOD.
def test_16_17_split_and_combo_separation(project_root):
    for ds in DATASETS:
        pred = pd.read_csv(project_root / "data" / "lstm_autoencoder" / f"{ds}_lstm_predictions.csv",
                           usecols=["timestamp", "split"])
        id_ts = set(pd.read_csv(project_root / "data" / "benchmark" / ds
                                / "test_in_distribution.csv", usecols=["timestamp"])["timestamp"])
        ood_ts = set(pd.read_csv(project_root / "data" / "benchmark" / ds
                                 / "test_generalization.csv", usecols=["timestamp"])["timestamp"])
        assert set(pred[pred["split"] == "test_in_distribution"]["timestamp"]) == id_ts
        assert set(pred[pred["split"] == "test_generalization"]["timestamp"]) == ood_ts
        assert not (id_ts & ood_ts)
        ev = pd.read_csv(project_root / "reports" / "lstm_autoencoder" / f"{ds}_event_results.csv")
        assert (ev[ev["fault_type"] == "SPIKE_PLUS_DRIFT"]["split"] == "test_generalization").all()
        assert (ev[ev["split"] != "test_generalization"]["fault_type"] != "SPIKE_PLUS_DRIFT").all()


# 18+19+20. Event detection, latency, metric equations on fixtures.
def test_18_19_20_events_latency_metrics():
    from src.lstm_autoencoder.evaluator import build_event_frame

    rows = pd.DataFrame({
        "timestamp": ["2024-01-01 00:00:00", "2024-01-01 00:05:00", "2024-01-01 00:10:00"],
        "lstm_anomaly_flag": [0, 1, 0],
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


# 21. Artifacts exist with required metadata.
def test_21_artifacts_exist(project_root):
    for ds in DATASETS:
        assert (project_root / "models" / "lstm_autoencoder" / f"{ds}_lstm_autoencoder.keras").is_dir() \
            or (project_root / "models" / "lstm_autoencoder" / f"{ds}_lstm_autoencoder.keras").is_file()
        assert (project_root / "models" / "lstm_autoencoder" / f"{ds}_scaler.joblib").is_file()
        assert (project_root / "data" / "lstm_autoencoder" / f"{ds}_lstm_predictions.csv").is_file()
    rep = project_root / "reports" / "lstm_autoencoder"
    for name in ("lstm_autoencoder_evaluation.md", "lstm_autoencoder_metrics.csv", "event_metrics.csv",
                 "jena_event_results.csv", "delhi_event_results.csv",
                 "ood_metrics.csv", "false_positive_analysis.csv", "feature_manifest.json",
                 "model_config.json", "phase6_phase7_comparison.csv"):
        assert (rep / name).is_file(), name
    manifest = json.load(open(rep / "feature_manifest.json"))
    assert manifest["n_features"] == 30 and len(manifest["features"]) == 30
    assert manifest["synthetic_training_contamination"] == 0
    cfg = json.load(open(rep / "model_config.json"))
    required = ("dataset", "train_range", "validation_range", "lookback", "feature_list",
                "scaler_type", "architecture", "epochs_requested", "batch_size", "optimizer",
                "learning_rate", "loss", "random_seed", "threshold_method", "threshold_value",
                "training_sequence_count", "validation_sequence_count", "scored_sequence_counts",
                "software_versions")
    for ds in DATASETS:
        for key in required:
            assert key in cfg[ds], (ds, key)
        assert cfg[ds]["benchmark_train_used_for_fit"] is False


# 22. Reproducibility: chronological split + threshold are pure functions.
def test_22_reproducible():
    idx = np.arange(100)
    assert (chronological_split(100)[0] == idx[:90]).all()
    assert (chronological_split(100)[1] == idx[90:]).all()
    s = np.arange(50, dtype=float)
    assert fit_threshold(s, 0.99)[0] == fit_threshold(s, 0.99)[0]


# 23. Previous phases unchanged (row counts + frozen constants + thresholds).
def test_23_previous_phases_unchanged(project_root):
    assert len(pd.read_csv(project_root / "data" / "features" / "jena_features.csv",
                           usecols=["timestamp"])) == 420224
    assert len(pd.read_csv(project_root / "data" / "evaluation" / "statistical_baseline"
                           / "summary_metrics.csv")) > 0
    assert len(pd.read_csv(project_root / "data" / "benchmark" / "jena" / "train.csv",
                           usecols=["timestamp"])) == 251969
    if_cfg = json.load(open(project_root / "reports" / "isolation_forest" / "model_config.json"))
    assert if_cfg["jena"]["threshold_raw"] == pytest.approx(0.026259994424697897)
    assert if_cfg["delhi"]["threshold_raw"] == pytest.approx(0.035639253732814624)
    from src.baseline.zscore_baseline import Z_THRESHOLD
    from src.baseline.iqr_baseline import IQR_FACTOR

    assert Z_THRESHOLD == 3.0 and IQR_FACTOR == 1.5
    assert (project_root / "data" / "noaa" / "metadata" / "station_manifest.json").is_file()
    assert (project_root / "data" / "noaa" / "metadata" / "neighbor_graph.csv").is_file()

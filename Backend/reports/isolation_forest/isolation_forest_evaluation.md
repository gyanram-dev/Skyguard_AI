# Isolation Forest Anomaly Detector — Evaluation: Phase 7

**Scope**: first ML detector (server-side Isolation Forest). No LSTM, NOAA/spatial, ensemble, root-cause, SHAP, API, or frontend.
Fitted ONLY on clean pre-benchmark observations (`data/processed/{jena,delhi}_clean.csv`, Phase 5 train period); synthetic_training_contamination = 0. Threshold frozen on clean train scores (99th percentile); injected benchmark splits used for evaluation only. Scores are NOT probabilities.

## Training configuration (per dataset)

- `jena`: params `{'n_estimators': 200, 'max_samples': 'auto', 'contamination': 'auto', 'max_features': 1.0, 'bootstrap': False, 'random_state': 26073, 'n_jobs': -1}`, seed 26073, CLEAN source `data/processed/jena_clean.csv`, train 2009-01-01 00:10:00 → 2013-10-17 22:50:00, fitted 252,026/252,134 rows (eligible 252,132), threshold_raw 0.0263 (99% percentile of eligible training raw scores), train above threshold 2,521 (0.0100), sklearn 1.9.1, synthetic_training_contamination=0.
- `delhi`: params `{'n_estimators': 200, 'max_samples': 'auto', 'contamination': 'auto', 'max_features': 1.0, 'bootstrap': False, 'random_state': 26073, 'n_jobs': -1}`, seed 26073, CLEAN source `data/processed/delhi_clean.csv`, train 2022-04-01 00:00:00 → 2023-11-25 14:15:00, fitted 172,824/173,836 rows (eligible 173,206), threshold_raw 0.0356 (99% percentile of eligible training raw scores), train above threshold 1,729 (0.0100), sklearn 1.9.1, synthetic_training_contamination=0.

## Feature allowlist (94 of 106)

Kept: current observations (3), cyclical encodings (4), first-order dynamics (9), frozen/stability (9), causal rolling baselines (36), local deviations (18), trends (9), multivariate consistency (6). Excluded: timestamp/source_dataset (provenance), 7 quality flags (constant on eligible rows), elapsed/gap_before/segment_id (gap machinery). Full 94-name list in `feature_manifest.json`; labels rejected loudly, never imputed (NaN → unscorable).

## Score transformation

`if_raw_score = -decision_function(X)` (higher = more anomalous); `if_anomaly_score = ECDF_train(raw)` in [0,1]; flag = raw ≥ frozen threshold.

## Row metrics (frozen threshold)

| Dataset | Split | Precision | Recall | F1 | FPR | FNR |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | 0.1642 | 0.0863 | 0.1131 | 0.0108 | 0.9137 |
| jena | test_generalization | 0.4875 | 0.3267 | 0.3912 | 0.0130 | 0.6733 |
| delhi | test_in_distribution | 0.1313 | 0.0690 | 0.0905 | 0.0301 | 0.9310 |
| delhi | test_generalization | 0.3308 | 0.1431 | 0.1998 | 0.0277 | 0.8569 |

Train-split flag counts are diagnostic only (threshold construction set), not generalization; see training configuration above.

## Event metrics

| Dataset | Split | Events | Detected | Recall | Lat med | Lat mean |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | 120 | 20 | 0.1667 | 40.0000 | 78.5000 |
| jena | test_generalization | 140 | 79 | 0.5643 | 30.0000 | 78.6076 |
| delhi | test_in_distribution | 120 | 31 | 0.2583 | 5.0000 | 79.5161 |
| delhi | test_generalization | 140 | 63 | 0.4500 | 20.0000 | 62.3810 |

## Per-fault and per-variable recall

- jena/test_in_distribution: SPIKE=0.0926, FROZEN=0.0000, DRIFT=0.0870, CROSS_VARIABLE=0.1574, SPIKE_PLUS_DRIFT=absent
- jena/test_generalization: SPIKE=0.2667, FROZEN=0.0132, DRIFT=0.2222, CROSS_VARIABLE=0.9108, SPIKE_PLUS_DRIFT=0.3066
- delhi/test_in_distribution: SPIKE=0.3103, FROZEN=0.0278, DRIFT=0.0647, CROSS_VARIABLE=0.1070, SPIKE_PLUS_DRIFT=absent
- delhi/test_generalization: SPIKE=0.3134, FROZEN=0.0015, DRIFT=0.0420, CROSS_VARIABLE=0.8425, SPIKE_PLUS_DRIFT=0.0609

## SPIKE_PLUS_DRIFT (OOD unseen combinations)

- jena: 19/20 events (recall 0.9500), row recall 0.3066.
- delhi: 14/20 events (recall 0.7000), row recall 0.0609.

## False positives + latency + comparison

- jena/test_in_distribution: 886/81,856 background flagged (rate 0.0108, 108.2389/10k). No root-cause inference.
- jena/test_generalization: 1,049/80,455 background flagged (rate 0.0130, 130.3834/10k). No root-cause inference.
- delhi/test_in_distribution: 1,628/54,059 background flagged (rate 0.0301, 301.1524/10k). No root-cause inference.
- delhi/test_generalization: 1,436/51,825 background flagged (rate 0.0277, 277.0863/10k). No root-cause inference.

## Phase 6 comparison (descriptive; no winner declared)

| Dataset | Split | Scope | Baseline | Base_P | Base_R | Base_F1 | IF_P | IF_R | IF_F1 |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | row | zscore | 0.0324 | 0.1701 | 0.0544 | 0.1642 | 0.0863 | 0.1131 |
| jena | test_in_distribution | row | iqr | 0.0261 | 0.3639 | 0.0487 | 0.1642 | 0.0863 | 0.1131 |
| jena | test_generalization | row | zscore | 0.0515 | 0.1827 | 0.0804 | 0.4875 | 0.3267 | 0.3912 |
| jena | test_generalization | row | iqr | 0.0389 | 0.3614 | 0.0703 | 0.4875 | 0.3267 | 0.3912 |
| delhi | test_in_distribution | row | zscore | 0.0915 | 0.1395 | 0.1105 | 0.1313 | 0.0690 | 0.0905 |
| delhi | test_in_distribution | row | iqr | 0.0746 | 0.2972 | 0.1192 | 0.1313 | 0.0690 | 0.0905 |
| delhi | test_generalization | row | zscore | 0.1131 | 0.1431 | 0.1264 | 0.3308 | 0.1431 | 0.1998 |
| delhi | test_generalization | row | iqr | 0.0985 | 0.2913 | 0.1473 | 0.3308 | 0.1431 | 0.1998 |

Full side-by-side (incl. event recall/latency) in `phase6_comparison.csv`.
Command: `python -m src.isolation_forest.run` (~51s). No tuning on ID/OOD.

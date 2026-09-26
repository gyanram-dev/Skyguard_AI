# LSTM Autoencoder Anomaly Detector — Evaluation: Phase 9

**Scope**: sequence-aware detector only. No NOAA/spatial, ensemble, root-cause, SHAP, API, or frontend work.
Fitted ONLY on clean pre-benchmark observations; synthetic_training_contamination = 0. Threshold frozen on clean train reconstruction errors (99th percentile); injected benchmark splits used for evaluation only. Scores are NOT probabilities.

## Training configuration (per dataset)

- `jena`: CLEAN source `data/processed/jena_clean.csv`, train 2009-01-01 00:10:00 → 2013-10-17 22:50:00, 252,062 valid 12-step sequences (fit 226,855, val 25,207), epochs 23/30 (early_stopped=True), best val_loss 0.176511, threshold 1.301953 (99% percentile of eligible clean-training target MSE), TF 2.22.0-rc0.
- `delhi`: CLEAN source `data/processed/delhi_clean.csv`, train 2022-04-01 00:00:00 → 2023-11-25 14:15:00, 173,004 valid 12-step sequences (fit 155,703, val 17,301), epochs 30/30 (early_stopped=False), best val_loss 0.139882, threshold 1.557834 (99% percentile of eligible clean-training target MSE), TF 2.22.0-rc0.

## Architecture and features

LSTM autoencoder: `Input(12, F) -> LSTM(64, return_sequences=False) -> Dense(32, relu) [latent 32] -> RepeatVector(12) -> LSTM(64, return_sequences=True) -> TimeDistributed(Dense(F)); loss=MSE, optimizer=Adam(lr=0.001)`. 30 temporal features (documented subset of the Phase 7 94-feature allowlist; full list in `feature_manifest.json`). Scaler: StandardScaler fit on eligible finite clean rows, frozen for evaluation. Official score: final-timestep MSE (HIGHER = MORE anomalous); full-sequence MSE diagnostic.

## Row metrics (frozen threshold)

| Dataset | Split | Precision | Recall | F1 | FPR | FNR |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | 0.0525 | 0.0392 | 0.0449 | 0.0174 | 0.9608 |
| jena | test_generalization | 0.3748 | 0.4481 | 0.4082 | 0.0284 | 0.5519 |
| delhi | test_in_distribution | 0.1213 | 0.0609 | 0.0811 | 0.0291 | 0.9391 |
| delhi | test_generalization | 0.3063 | 0.2495 | 0.2750 | 0.0541 | 0.7505 |

## Event metrics

| Dataset | Split | Events | Detected | Recall | Lat med | Lat mean |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | 120 | 46 | 0.3833 | 0.0000 | 45.0000 |
| jena | test_generalization | 140 | 107 | 0.7643 | 0.0000 | 43.1776 |
| delhi | test_in_distribution | 120 | 78 | 0.6500 | 10.0000 | 65.6410 |
| delhi | test_generalization | 140 | 110 | 0.7857 | 0.0000 | 44.7727 |

## Per-fault row recall

- jena/test_in_distribution: SPIKE=0.9259, FROZEN=0.0111, DRIFT=0.0107, CROSS_VARIABLE=0.0508, SPIKE_PLUS_DRIFT=absent
- jena/test_generalization: SPIKE=0.9667, FROZEN=0.0278, DRIFT=0.3324, CROSS_VARIABLE=0.9331, SPIKE_PLUS_DRIFT=0.5854
- delhi/test_in_distribution: SPIKE=0.8103, FROZEN=0.3500, DRIFT=0.0242, CROSS_VARIABLE=0.1658, SPIKE_PLUS_DRIFT=absent
- delhi/test_generalization: SPIKE=0.8507, FROZEN=0.5746, DRIFT=0.0167, CROSS_VARIABLE=0.9900, SPIKE_PLUS_DRIFT=0.1032

## SPIKE_PLUS_DRIFT (OOD unseen combinations)

- jena: 20/20 events (recall 1.0000), row recall 0.5854.
- delhi: 20/20 events (recall 1.0000), row recall 0.1032.

## False positives

- jena/test_in_distribution: 1,426/81,856 background flagged (rate 0.0174, 174.2084/10k). No root-cause inference.
- jena/test_generalization: 2,284/80,455 background flagged (rate 0.0284, 283.8854/10k). No root-cause inference.
- delhi/test_in_distribution: 1,572/54,059 background flagged (rate 0.0291, 290.7934/10k). No root-cause inference.
- delhi/test_generalization: 2,804/51,825 background flagged (rate 0.0541, 541.0516/10k). No root-cause inference.

## Phase 6 / Phase 7 comparison (descriptive; no winner declared)

- jena/test_in_distribution row vs zscore: P 0.0324 → LSTM 0.0525; R 0.1701 → LSTM 0.0392; F1 0.0544 → LSTM 0.0449.
- jena/test_in_distribution row vs iqr: P 0.0261 → LSTM 0.0525; R 0.3639 → LSTM 0.0392; F1 0.0487 → LSTM 0.0449.
- jena/test_in_distribution row vs iforest: P 0.1642 → LSTM 0.0525; R 0.0863 → LSTM 0.0392; F1 0.1131 → LSTM 0.0449.
- jena/test_generalization row vs zscore: P 0.0515 → LSTM 0.3748; R 0.1827 → LSTM 0.4481; F1 0.0804 → LSTM 0.4082.
- jena/test_generalization row vs iqr: P 0.0389 → LSTM 0.3748; R 0.3614 → LSTM 0.4481; F1 0.0703 → LSTM 0.4082.
- jena/test_generalization row vs iforest: P 0.4875 → LSTM 0.3748; R 0.3267 → LSTM 0.4481; F1 0.3912 → LSTM 0.4082.
- delhi/test_in_distribution row vs zscore: P 0.0915 → LSTM 0.1213; R 0.1395 → LSTM 0.0609; F1 0.1105 → LSTM 0.0811.
- delhi/test_in_distribution row vs iqr: P 0.0746 → LSTM 0.1213; R 0.2972 → LSTM 0.0609; F1 0.1192 → LSTM 0.0811.
- delhi/test_in_distribution row vs iforest: P 0.1313 → LSTM 0.1213; R 0.0690 → LSTM 0.0609; F1 0.0905 → LSTM 0.0811.
- delhi/test_generalization row vs zscore: P 0.1131 → LSTM 0.3063; R 0.1431 → LSTM 0.2495; F1 0.1264 → LSTM 0.2750.
- delhi/test_generalization row vs iqr: P 0.0985 → LSTM 0.3063; R 0.2913 → LSTM 0.2495; F1 0.1473 → LSTM 0.2750.
- delhi/test_generalization row vs iforest: P 0.3308 → LSTM 0.3063; R 0.1431 → LSTM 0.2495; F1 0.1998 → LSTM 0.2750.

Full side-by-side (incl. event recall/latency) in `phase6_phase7_comparison.csv`.
Command: `python -m src.lstm_autoencoder.run` (~1044s). No tuning on ID/OOD.

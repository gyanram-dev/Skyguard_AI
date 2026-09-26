# Calibrated Multi-Detector Ensemble — Evaluation: Phase 10

**Scope**: calibrated combination of statistical, Isolation Forest, and LSTM evidence. No retraining/retuning; NOAA contextual only; no root-cause, SHAP, API, or frontend work.
Calibration (ECDF) and thresholds from clean-training scores only; benchmark labels used for measurement only. Scores are NOT probabilities.

## Calibration and configuration (per dataset)

- `jena`: train 2009-01-01 00:10:00 → 2013-10-17 22:50:00 (252,134 rows); thresholds mean 0.9540 / median 0.9777 (99% percentile of clean-training ensemble scores); contamination 0.
- `delhi`: train 2022-04-01 00:00:00 → 2023-11-25 14:15:00 (173,836 rows); thresholds mean 0.9510 / median 0.9783 (99% percentile of clean-training ensemble scores); contamination 0.

Final ensemble: 3 components {statistical(z,iqr), IF, LSTM} with equal-weight mean (`ens_mean`) and median (`ens_median`); diagnostic 4-input variants (`diag_mean`, `diag_median`) keep z/iqr separate. Availability: FULL=3, PARTIAL=2, INSUFFICIENT<2 → NaN (never zero-filled).

## Row metrics (frozen thresholds)

| Dataset | Split | Method | Precision | Recall | F1 | FPR | FNR |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | ens_mean | 0.1049 | 0.0570 | 0.0739 | 0.0120 | 0.9430 |
| jena | test_in_distribution | ens_median | 0.1086 | 0.0640 | 0.0805 | 0.0129 | 0.9360 |
| jena | test_generalization | ens_mean | 0.3615 | 0.1666 | 0.2281 | 0.0112 | 0.8334 |
| jena | test_generalization | ens_median | 0.4822 | 0.4131 | 0.4450 | 0.0168 | 0.5869 |
| delhi | test_in_distribution | ens_mean | 0.1388 | 0.0575 | 0.0813 | 0.0235 | 0.9425 |
| delhi | test_in_distribution | ens_median | 0.1356 | 0.0570 | 0.0802 | 0.0239 | 0.9430 |
| delhi | test_generalization | ens_mean | 0.2642 | 0.1127 | 0.1580 | 0.0300 | 0.8873 |
| delhi | test_generalization | ens_median | 0.3120 | 0.1657 | 0.2164 | 0.0350 | 0.8343 |

## Event metrics

| Dataset | Split | Method | Events | Detected | Recall | Lat med | Lat mean |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | ens_mean | 120 | 55 | 0.4583 | 0.0000 | 54.3636 |
| jena | test_in_distribution | ens_median | 120 | 55 | 0.4583 | 0.0000 | 42.5455 |
| jena | test_generalization | ens_mean | 140 | 107 | 0.7643 | 0.0000 | 42.4299 |
| jena | test_generalization | ens_median | 140 | 107 | 0.7643 | 0.0000 | 40.8411 |
| delhi | test_in_distribution | ens_mean | 120 | 60 | 0.5000 | 7.5000 | 54.9167 |
| delhi | test_in_distribution | ens_median | 120 | 62 | 0.5167 | 0.0000 | 52.6613 |
| delhi | test_generalization | ens_mean | 140 | 95 | 0.6786 | 5.0000 | 56.0526 |
| delhi | test_generalization | ens_median | 140 | 94 | 0.6714 | 5.0000 | 53.1915 |

## Per-fault row recall (official methods)

- jena/test_in_distribution/ens_mean: SPIKE=0.6852, FROZEN=0.0222, DRIFT=0.0259, CROSS_VARIABLE=0.1675, SPIKE_PLUS_DRIFT=absent
- jena/test_in_distribution/ens_median: SPIKE=0.6852, FROZEN=0.0222, DRIFT=0.0315, CROSS_VARIABLE=0.1929, SPIKE_PLUS_DRIFT=absent
- jena/test_generalization/ens_mean: SPIKE=0.8333, FROZEN=0.0351, DRIFT=0.1073, CROSS_VARIABLE=0.3448, SPIKE_PLUS_DRIFT=0.1781
- jena/test_generalization/ens_median: SPIKE=0.7833, FROZEN=0.0381, DRIFT=0.3017, CROSS_VARIABLE=0.9777, SPIKE_PLUS_DRIFT=0.4438
- delhi/test_in_distribution/ens_mean: SPIKE=0.7241, FROZEN=0.0167, DRIFT=0.0303, CROSS_VARIABLE=0.3476, SPIKE_PLUS_DRIFT=absent
- delhi/test_in_distribution/ens_median: SPIKE=0.7759, FROZEN=0.0111, DRIFT=0.0344, CROSS_VARIABLE=0.2567, SPIKE_PLUS_DRIFT=absent
- delhi/test_generalization/ens_mean: SPIKE=0.8955, FROZEN=0.0219, DRIFT=0.0267, CROSS_VARIABLE=0.5672, SPIKE_PLUS_DRIFT=0.0569
- delhi/test_generalization/ens_median: SPIKE=0.8507, FROZEN=0.0365, DRIFT=0.0234, CROSS_VARIABLE=0.9652, SPIKE_PLUS_DRIFT=0.0721

## SPIKE_PLUS_DRIFT (OOD unseen combinations)

- jena/ens_mean: 20/20 events (recall 1.0000), row recall 0.1781.
- jena/ens_median: 20/20 events (recall 1.0000), row recall 0.4438.
- delhi/ens_mean: 20/20 events (recall 1.0000), row recall 0.0569.
- delhi/ens_median: 20/20 events (recall 1.0000), row recall 0.0721.

## False positives

- jena/test_in_distribution/ens_mean: 981/81,856 background flagged (rate 0.0120, 119.8446/10k). No root-cause inference.
- jena/test_in_distribution/ens_median: 1,059/81,856 background flagged (rate 0.0129, 129.3735/10k). No root-cause inference.
- jena/test_generalization/ens_mean: 899/80,455 background flagged (rate 0.0112, 111.7395/10k). No root-cause inference.
- jena/test_generalization/ens_median: 1,355/80,455 background flagged (rate 0.0168, 168.4171/10k). No root-cause inference.
- delhi/test_in_distribution/ens_mean: 1,272/54,059 background flagged (rate 0.0235, 235.2985/10k). No root-cause inference.
- delhi/test_in_distribution/ens_median: 1,294/54,059 background flagged (rate 0.0239, 239.3681/10k). No root-cause inference.
- delhi/test_generalization/ens_mean: 1,557/51,825 background flagged (rate 0.0300, 300.4342/10k). No root-cause inference.
- delhi/test_generalization/ens_median: 1,813/51,825 background flagged (rate 0.0350, 349.8312/10k). No root-cause inference.

## Comparison with Phase 6/7/9 (descriptive; no winner declared)

- jena/test_in_distribution/ens_mean vs zscore: P 0.0324 → 0.1049; R 0.1701 → 0.0570; F1 0.0544 → 0.0739.
- jena/test_in_distribution/ens_mean vs iqr: P 0.0261 → 0.1049; R 0.3639 → 0.0570; F1 0.0487 → 0.0739.
- jena/test_in_distribution/ens_mean vs iforest: P 0.1642 → 0.1049; R 0.0863 → 0.0570; F1 0.1131 → 0.0739.
- jena/test_in_distribution/ens_mean vs lstm_ae: P 0.0525 → 0.1049; R 0.0392 → 0.0570; F1 0.0449 → 0.0739.
- jena/test_in_distribution/ens_median vs zscore: P 0.0324 → 0.1086; R 0.1701 → 0.0640; F1 0.0544 → 0.0805.
- jena/test_in_distribution/ens_median vs iqr: P 0.0261 → 0.1086; R 0.3639 → 0.0640; F1 0.0487 → 0.0805.
- jena/test_in_distribution/ens_median vs iforest: P 0.1642 → 0.1086; R 0.0863 → 0.0640; F1 0.1131 → 0.0805.
- jena/test_in_distribution/ens_median vs lstm_ae: P 0.0525 → 0.1086; R 0.0392 → 0.0640; F1 0.0449 → 0.0805.
- jena/test_generalization/ens_mean vs zscore: P 0.0515 → 0.3615; R 0.1827 → 0.1666; F1 0.0804 → 0.2281.
- jena/test_generalization/ens_mean vs iqr: P 0.0389 → 0.3615; R 0.3614 → 0.1666; F1 0.0703 → 0.2281.
- jena/test_generalization/ens_mean vs iforest: P 0.4875 → 0.3615; R 0.3267 → 0.1666; F1 0.3912 → 0.2281.
- jena/test_generalization/ens_mean vs lstm_ae: P 0.3748 → 0.3615; R 0.4481 → 0.1666; F1 0.4082 → 0.2281.
- jena/test_generalization/ens_median vs zscore: P 0.0515 → 0.4822; R 0.1827 → 0.4131; F1 0.0804 → 0.4450.
- jena/test_generalization/ens_median vs iqr: P 0.0389 → 0.4822; R 0.3614 → 0.4131; F1 0.0703 → 0.4450.
- jena/test_generalization/ens_median vs iforest: P 0.4875 → 0.4822; R 0.3267 → 0.4131; F1 0.3912 → 0.4450.
- jena/test_generalization/ens_median vs lstm_ae: P 0.3748 → 0.4822; R 0.4481 → 0.4131; F1 0.4082 → 0.4450.
- delhi/test_in_distribution/ens_mean vs zscore: P 0.0915 → 0.1388; R 0.1395 → 0.0575; F1 0.1105 → 0.0813.
- delhi/test_in_distribution/ens_mean vs iqr: P 0.0746 → 0.1388; R 0.2972 → 0.0575; F1 0.1192 → 0.0813.
- delhi/test_in_distribution/ens_mean vs iforest: P 0.1313 → 0.1388; R 0.0690 → 0.0575; F1 0.0905 → 0.0813.
- delhi/test_in_distribution/ens_mean vs lstm_ae: P 0.1213 → 0.1388; R 0.0609 → 0.0575; F1 0.0811 → 0.0813.
- delhi/test_in_distribution/ens_median vs zscore: P 0.0915 → 0.1356; R 0.1395 → 0.0570; F1 0.1105 → 0.0802.
- delhi/test_in_distribution/ens_median vs iqr: P 0.0746 → 0.1356; R 0.2972 → 0.0570; F1 0.1192 → 0.0802.
- delhi/test_in_distribution/ens_median vs iforest: P 0.1313 → 0.1356; R 0.0690 → 0.0570; F1 0.0905 → 0.0802.
- delhi/test_in_distribution/ens_median vs lstm_ae: P 0.1213 → 0.1356; R 0.0609 → 0.0570; F1 0.0811 → 0.0802.
- delhi/test_generalization/ens_mean vs zscore: P 0.1131 → 0.2642; R 0.1431 → 0.1127; F1 0.1264 → 0.1580.
- delhi/test_generalization/ens_mean vs iqr: P 0.0985 → 0.2642; R 0.2913 → 0.1127; F1 0.1473 → 0.1580.
- delhi/test_generalization/ens_mean vs iforest: P 0.3308 → 0.2642; R 0.1431 → 0.1127; F1 0.1998 → 0.1580.
- delhi/test_generalization/ens_mean vs lstm_ae: P 0.3063 → 0.2642; R 0.2495 → 0.1127; F1 0.2750 → 0.1580.
- delhi/test_generalization/ens_median vs zscore: P 0.1131 → 0.3120; R 0.1431 → 0.1657; F1 0.1264 → 0.2164.
- delhi/test_generalization/ens_median vs iqr: P 0.0985 → 0.3120; R 0.2913 → 0.1657; F1 0.1473 → 0.2164.
- delhi/test_generalization/ens_median vs iforest: P 0.3308 → 0.3120; R 0.1431 → 0.1657; F1 0.1998 → 0.2164.
- delhi/test_generalization/ens_median vs lstm_ae: P 0.3063 → 0.3120; R 0.2495 → 0.1657; F1 0.2750 → 0.2164.

Full side-by-side (incl. event recall/latency) in `phase6_phase7_phase9_comparison.csv`.
## NOAA contextual treatment

- jena: {'join': 'none (geographic/temporal disjointness)', 'benchmark_rows_with_context': 0, 'note': 'Jena predates and is outside NOAA coverage'}
- delhi: {'test_in_distribution': {'benchmark_rows': 57649, 'joined_rows': 57649, 'rows_with_context': 57607, 'fraction': 0.9993}, 'test_generalization': {'benchmark_rows': 56982, 'joined_rows': 56982, 'rows_with_context': 56518, 'fraction': 0.9919}, 'join': 'timestamp join benchmark -> Phase 8B aws_context_validation', 'usage': 'availability reporting only; excluded from official ensemble score'}

NOAA excluded from the official ensemble score; availability only.
Command: `python -m src.ensemble.run` (~255s). No tuning on ID/OOD.

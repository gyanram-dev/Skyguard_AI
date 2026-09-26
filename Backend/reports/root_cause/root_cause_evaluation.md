# Root-Cause Classification + Explainability — Evaluation: Phase 11

**Scope**: post-detection diagnosis only. Supervised on benchmark TRAIN fault rows (explicitly allowed); ID/OOD labels measurement-only. No detector retraining, no threshold changes, no SHAP causality claims.

## Training and rules (per dataset)

- `jena`: train 2009-01-01 00:10:00 → 2013-10-17 22:50:00, 1,932 complete fault rows (0 excluded incomplete), classes {'n_estimators': 300, 'max_features': 'sqrt', 'min_samples_leaf': 3, 'class_weight': 'balanced_subsample', 'random_state': 26073, 'n_jobs': -1}; internal validation accuracy 0.8966 (correct median confidence 0.8419, wrong 0.6081); max proba < 0.6 -> UNKNOWN (frozen on train-validation); top >= 0.6 and second >= 0.35 and gap <= 0.25 -> MIXED (frozen on train-validation).
- `delhi`: train 2022-04-01 00:00:00 → 2023-11-25 14:15:00, 3,594 complete fault rows (0 excluded incomplete), classes {'n_estimators': 300, 'max_features': 'sqrt', 'min_samples_leaf': 3, 'class_weight': 'balanced_subsample', 'random_state': 26073, 'n_jobs': -1}; internal validation accuracy 0.9513 (correct median confidence 0.9273, wrong 0.6673); max proba < 0.6 -> UNKNOWN (frozen on train-validation); top >= 0.6 and second >= 0.35 and gap <= 0.25 -> MIXED (frozen on train-validation).

## Classifier metrics on detected anomalies (operating set)

| Dataset | Split | Diagnosed | Acc | Acc excl UNKNOWN | Macro F1 | UNKNOWN rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | 129 | 0.6744 | 0.9775 | 0.7802 | 0.3101 |
| jena | test_generalization | 1,262 | 0.1965 | 0.3238 | 0.2346 | 0.3930 |
| delhi | test_in_distribution | 203 | 0.4532 | 0.8142 | 0.6167 | 0.4433 |
| delhi | test_generalization | 822 | 0.6168 | 0.9168 | 0.6580 | 0.3273 |

UNKNOWN rates and excl-UNKNOWN accuracy live in `unknown_metrics.csv`; MIXED combo behavior in `mixed_metrics.csv`.

## End-to-end anomaly → diagnosis (per event)

| Dataset | Split | Events | Detected | Correct diagnosis | End-to-end rate | Conditional accuracy |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| jena | test_in_distribution | 120 | 55 | 41 | 0.3417 | 0.7455 |
| jena | test_generalization | 140 | 107 | 42 | 0.3000 | 0.3925 |
| delhi | test_in_distribution | 120 | 62 | 35 | 0.2917 | 0.5645 |
| delhi | test_generalization | 140 | 94 | 53 | 0.3786 | 0.5638 |

Confusion matrices in `confusion_matrices.csv`; worked SHAP examples in `shap_examples/` (wording: features contributing to the prediction, not causes).
Command: `python -m src.root_cause.run` (~127s). No tuning on ID/OOD.
